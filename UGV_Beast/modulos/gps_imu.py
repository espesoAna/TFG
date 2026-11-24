"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres
MÓDULO: Adquisición y Fusión de Sensores GPS e IMU.
ARCHIVO: gps_imu.py

DESCRIPCIÓN:
    Gestiona los datos del bus I2C/UART para
    el sensor Inercial (IMU) y el demonio POSIX del GPS (gpsd).
    
    En este Script se implementa la adquisicion de los datos tanto del GPS como del IMU para porcesarlos añadiendo filtros y consiguiendo una lectura mas limpia de los datos.
"""

import math
import time
import json
import threading
from config import NAV_PARAMS 

try:
    import gps
except ImportError:
    print("❌ Falta la librería gps. Ejecuta: sudo apt-get install python3-gps")

class ModuloGPS_IMU:
    def __init__(self, state_dict):
        self.state = state_dict
        
        # Filtros Paso-Bajos (Low-Pass Filters) para suavizar ruido térmico y mecánico
        self.smooth_mx = None
        self.smooth_my = None
        self.smooth_gz = 0.0
        self.brujula_inicializada = False

    def procesar_giroscopio(self, gz_bruto):
        """
        Condiciona la señal en bruto del eje Z (Yaw) del giroscopio.
        Aplica un filtro agresivo para ignorar los picos mecánicos generados 
        por el dron.
        """
        # 1. Filtro Recortador para ruidos o impactos violentos
        if gz_bruto > 100.0: gz_bruto = 0.0
        if gz_bruto < -100.0: gz_bruto = 0.0
        
        # 2. Filtro Pasa-Bajo Exponencial (EMA - Exponential Moving Average)
        self.smooth_gz = (0.2 * gz_bruto) + (0.8 * self.smooth_gz)
        
        # 3. Banda Muerta mecánica. Ignora derivas minúsculas < 2.5 grados/s.
        self.state["current_gz"] = 0.0 if abs(self.smooth_gz) < 2.5 else self.smooth_gz

    def iniciar_hilo_imu(self, base_controller):
        threading.Thread(target=self._imu_loop, args=(base_controller,), daemon=True).start()

    def _imu_loop(self, base):
        """Bucle residente de alta frecuencia (50Hz teóricos) para capturar el IMU."""
        if base: self.calibrar_giroscopio(base)
        
        last_time = time.time()
        
        while True:
            data_imu = self.get_fresh_imu_data(base)
            
            if data_imu and all(k in data_imu for k in ('mx', 'my', 'gz')):
                # Restar el offset de calibración térmica calculado al arranque
                gz_crudo = math.degrees(data_imu["gz"]) - self.state["bias_gz"]
                
                # Aplicar inversión de hardware
                gz_bruto = gz_crudo * NAV_PARAMS.get('INVERTIR_SENSOR', -1)
                
                self.procesar_giroscopio(gz_bruto) 
                
                current_time = time.time()
                dt = current_time - last_time
                last_time = current_time
                
                # Fusión matemática de aceleración angular e intensidad magnética
                self.actualizar_orientacion(data_imu['mx'], data_imu['my'], self.state["current_gz"], dt)
                
            time.sleep(0.02)

    def iniciar_hilo_gps(self):
        threading.Thread(target=self._gpsd_loop, daemon=True).start()

    def _gpsd_loop(self):
        """Bucle cliente que escucha las tramas NMEA empaquetadas por el demonio gpsd."""
        last_fix_time = 0
        while True:
            try:
                session = gps.gps(mode=gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
                for report in session:
                    data = dict(report)
                    
                    # Coordenadas base
                    if data.get('class') == 'TPV':
                        if data.get('mode', 0) >= 2 and 'lat' in data and 'lon' in data:
                            lat, lon = float(data['lat']), float(data['lon'])
                            if not math.isnan(lat) and not math.isnan(lon) and lat != 0.0:
                                self.state['curr_lat'] = lat
                                self.state['curr_lon'] = lon
                                
                                last_fix_time = time.time()
                                self.state['fix'] = True
                        
                        # Timeout de enlace GNSS (Pérdida de señal bajo techos o árboles)
                        if time.time() - last_fix_time > 3.0:
                            self.state['fix'] = False
                            
                    # Análisis de constelaciones y fuerza de señal
                    elif data.get('class') == 'SKY':
                        if 'satellites' in data:
                            usados = sum(1 for s in data['satellites'] if s.get('used', False))
                            if usados > 0: self.state['sats'] = usados
                        elif 'uSat' in data:
                            self.state['sats'] = int(data['uSat'])
                            
            except Exception as e:
                print(f"\nRe-conectando antena GPSD... Error: {e}")
                time.sleep(2)

    def calibrar_giroscopio(self, base):
        """
        Rutina de arranque. Captura el sesgo térmico del chip IMU
        durante 2 segundos con los motores apagados para tener un cero verdadero.
        """
        if base: 
            base.ser.reset_input_buffer()
            time.sleep(0.5) 
        suma_bias, lecturas = 0.0, 0
        t_fin = time.time() + 2.0
        while time.time() < t_fin:
            data = self.get_fresh_imu_data(base)
            if data and 'gz' in data:
                suma_bias += math.degrees(data["gz"])
                lecturas += 1
        self.state["bias_gz"] = suma_bias / lecturas if lecturas > 0 else 0.0

    def get_fresh_imu_data(self, base):
        """Extracción no bloqueante de la última trama JSON disponible en el buffer serie UART."""
        if not base or base.ser.in_waiting == 0:
            return None  
        try:
            line = base.ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith('{'):
                return json.loads(line)
        except: pass
        return None

    def actualizar_orientacion(self, mx, my, gz, dt):
        """
        Filtro Complementario Dinámico. 
        Maneja la transición geométrica de los vectores magnéticos y la velocidad angular.
        """
        # 1. Integración temporal EMA para los vectores X e Y del magnetómetro
        if self.smooth_mx is None:
            self.smooth_mx = mx
            self.smooth_my = my
        else:
            self.smooth_mx = (0.05 * mx) + (0.95 * self.smooth_mx)
            self.smooth_my = (0.05 * my) + (0.95 * self.smooth_my)

        mx_corr = self.smooth_mx - self.state["bias_mx"]
        my_corr = self.smooth_my - self.state["bias_my"]
        
        # 2. Resolución del Arco Tangente para obtener el ángulo cardinal
        h = math.degrees(math.atan2(my_corr, mx_corr))
        h_invertido = (360 - h) % 360
        OFFSET_NORTE = 325 # Calibración para corregir campos de la batería
        rumbo_magnetico = (h_invertido + OFFSET_NORTE + 360) % 360

        if not self.brujula_inicializada:
            self.state["heading"] = round(rumbo_magnetico, 1)
            self.brujula_inicializada = True
            return

        # 3. Integración inercial clásica de grado 1 (Rumbo actual + velocidad angular * tiempo)
        rumbo_giroscopio = self.state["heading"] + (gz * dt)
        
        # =========================================================================
        # 4. PROTECCIÓN CONTRA INTERFERENCIAS
        # =========================================================================
        # is_moving = Motores moviendos
        # active    = Misión iniciada (Los vectores del Sprint mandan)
        if self.state.get("is_moving", False) or self.state.get("active", False):
            # Condición: Brújula silenciada (Peso 0.0)
            # El dron confía ciegamente en el giroscopio y en los recálculos de la linea recta.
            rumbo_fusionado = rumbo_giroscopio
        else:
            # Condición Reposo / Manual: El robot está quieto y sin misión autónoma activa.
            # Se permite que la brújula "arrastre" suavemente el rumbo hacia el Norte verdadero (Peso 2%)
            # para anular la deriva acumulada.
            diferencia = (rumbo_magnetico - rumbo_giroscopio + 180) % 360 - 180
            rumbo_fusionado = rumbo_giroscopio + (0.02 * diferencia)

        self.state["heading"] = round((rumbo_fusionado + 360) % 360, 1)