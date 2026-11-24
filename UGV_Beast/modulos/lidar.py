"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres 
MÓDULO: Subsistema de Percepción Espacial y Evasión Reactiva 
ARCHIVO:lidar.py
DESCRIPCIÓN: Driver de bajo nivel para el sensor LiDAR D500. Procesa el flujo binario
             UART, publica la nube de puntos del ultimo barrido y mantiene el radar
             segmentado en tres zonas frontales para la activacion del freno de emergencia.
"""

import threading
import time
import glob
import serial
from modulos.logger import log

class ModuloLidar:
    def __init__(self, state_dict, base_controller):
        # Enlace por referencia al Single Source of Truth y controlador base
        self.state = state_dict
        self.base = base_controller 
        self.state['obstaculo_critico'] = False
        
        #PARÁMETROS TÁCTICOS DE EVASIÓN 
        self.DISTANCIA_FRENO = 300  # Umbral de frenado en milímetros (30 cm)
        self.PUNTOS_PELIGRO = 3     # Histéresis de ruido: número mínimo de impactos para activar el freno
        self.DESFASE_GRADOS = 270   # Matriz de rotación/calibración geométrica respecto al eje del chasis
        
        #VARIABLES INTERNAS DE ENLACE Y POOLING 
        self.lidar_ser = None
        self.last_start_angle = 0
        self.lidar_angles = []
        self.lidar_distances = []
        self.last_scan = []
        self._scan_lock = threading.Lock()

    def iniciar_hilo(self):
        """Punto de entrada: Despliega el hilo de E/S dedicado a la ingesta del puerto serie"""
        threading.Thread(target=self._bucle_escaneo, daemon=True).start()

    def parse_lidar_frame(self, data):
        """
        Decodifica los paquetes binarios crudos del protocolo del LiDAR D500.
        Extrae el ángulo inicial del paquete y calcula la distancia de los 12 puntos muestreados.
        """
        # Reconstrucción de 16 bits para el ángulo inicial del paquete de datos
        start_angle = (data[5] << 8 | data[4]) * 0.01
        
        # Cada frame contiene una ráfaga de 12 muestras de espacio (3 bytes por muestra: 2 de distancia + 1 de señal)
        for i in range(12):
            offset = 6 + i * 3
            # Reconstrucción de 16 bits para la distancia de la muestra física
            dist = data[offset+1] << 8 | data[offset]
            
            # Se descartan errores de saturación (<180mm) y lecturas fuera de rango (>5000mm)
            if 180 < dist < 5000:
                # Interpolación lineal del ángulo para cada una de las 12 muestras intermedias + offset de calibración
                angulo = (start_angle + i * 0.83333 + self.DESFASE_GRADOS) % 360
                
                # FILTRADO ESPACIAL (ESTRICTO 180º) 
                # Se descarta el hemisferio trasero del UGV. Solo se procesa el arco frontal:
                # Desde 270º (Flanco Izquierdo) pasando por 0º/360º (Frente) hasta 90º (Flanco Derecho).
                if angulo <= 90 or angulo >= 270:
                    self.lidar_angles.append(angulo)
                    self.lidar_distances.append(dist)
                
        return start_angle

    def get_last_scan(self):
        """Devuelve una copia de los puntos (distancia_mm, angulo_grados) del ultimo barrido."""
        with self._scan_lock:
            return self.last_scan.copy()

    def _evaluar_radar(self):
        """
        Algoritmo de segmentación espacial y análisis de colisiones.
        Divide el arco frontal de 180º en 3 sectores tácticos para telemetría y seguridad.
        """
        impactos = 0
        dist_frente = 99999
        dist_izq = 99999
        dist_der = 99999
        
        # Publica una copia antes de purgar los buffers de la revolucion completada.
        with self._scan_lock:
            self.last_scan = [
                (d, a) for a, d in zip(self.lidar_angles, self.lidar_distances)
            ]

        # Análisis de la nube de puntos bidimensional capturada en la revolución
        for a, d in zip(self.lidar_angles, self.lidar_distances):
            
            # FILTRO DE INTERRUPCIÓN CRÍTICA:
            # Evalúa si existe un obstáculo en el cono colineal de avance directo (Eje central +/- 70º)
            if d < self.DISTANCIA_FRENO and (a >= 290 or a <= 70):
                impactos += 1

            # SEGMENTACIÓN GEOMÉTRICA POR SECTORES:
            # 1. Sector Izquierdo (Arco ciego lateral izquierdo: 270º a 290º)
            if 270 <= a < 290:
                dist_izq = min(dist_izq, d)
                
            # 2. Sector Frontal (Cono de avance principal: 290º a 70º)
            elif a >= 290 or a <= 70:
                dist_frente = min(dist_frente, d)
                    
            # 3. Sector Derecho (Arco ciego lateral derecho: 70º a 90º)
            elif 70 < a <= 90:
                dist_der = min(dist_der, d)
                
        # Evaluación del Failsafe: Si los impactos simultáneos superan la histéresis,
        # se activa la bandera de interrupción de hardware que congelará la cinemática.
        self.state['obstaculo_critico'] = (impactos >= self.PUNTOS_PELIGRO)
        
        # Normalización dimensional: Conversión a centímetros para visualización en la BS
        self.state['lidar_frontal_cm'] = round(dist_frente / 10, 1) if dist_frente != 99999 else "--"
        self.state['lidar_derecha_cm'] = round(dist_der / 10, 1) if dist_der != 99999 else "--"
        self.state['lidar_izquierda_cm'] = round(dist_izq / 10, 1) if dist_izq != 99999 else "--"
        
        # Purga de estructuras para el siguiente ciclo de barrido magnético
        self.lidar_angles.clear()
        self.lidar_distances.clear()

    def _bucle_escaneo(self):
        """
        Bucle de persistencia y parsing.
        Implementa escaneo en caliente de los puertos POSIX e ingesta del flujo serie a 230400 bps.
        """
        log.info("Buscando sensor Lidar...")
        
        # Orquestación de conexión en caliente (Hot-plugging scanner)
        while self.lidar_ser is None:
            puertos = glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*')
            
            for puerto in puertos:
                # Discriminación de hardware: El puerto ACM0 se reserva estáticamente para el GPS (Antena BN-808)
                if 'ACM0' in puerto: 
                    continue 
                try:
                    # Configuración UART del D500: Alta velocidad obligatoria a 230400 baudios
                    self.lidar_ser = serial.Serial(puerto, 230400, timeout=1)
                    log.info(f"[LIDAR] Vinculado en {puerto}")
                    break
                except Exception:
                    pass
            
            if self.lidar_ser is None:
                time.sleep(2) # Retardo de guarda antes del siguiente reintento de escaneo de buses
                
        #SUBSISTEMA DE INGESTA DE FLUJO CONTINUO
        while True:
            try:
                # Sincronización de trama: Busca el byte de cabecera mágico de inicio de paquete (0x54)
                header = self.lidar_ser.read(1)
                if header == b'\x54':
                    # Lectura por ráfaga del bloque restante fijo de la trama de telemetría (46 bytes)
                    data = header + self.lidar_ser.read(46)
                    if len(data) == 47:
                        # Evaluar antes de agregar el primer paquete de la vuelta nueva.
                        start_angle = (data[5] << 8 | data[4]) * 0.01
                        if self.last_start_angle > start_angle:
                            self._evaluar_radar()

                        start_angle = self.parse_lidar_frame(list(data))
                        self.last_start_angle = start_angle
                else:
                    # Si el flujo pierde la sincronía por ruido EMI en la UART, vacía el búfer del kernel 
                    # para evitar retrasos acumulados en la cola I/O.
                    self.lidar_ser.flushInput()
            except Exception:
                pass