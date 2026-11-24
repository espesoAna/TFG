"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres 
MÓDULO: Sensorización Ambiental Básica
ARCHIVO: entorno.py
DESCRIPCIÓN: Hilo paralelo que abstrae la lectura del puerto serie ttyUSB para 
             recolectar la telemetría meteorológica enviada por una placa de desarrollo.
"""

import serial
import threading
import time

class ModuloEntorno:
    def __init__(self, state_dict):
        self.state = state_dict
        # Inicialización de diccionario anidado para volcado de variables
        self.state['telemetry'].update({'temp_ext': 0.0, 'presion': 0.0})
        self.puerto = '/dev/ttyUSB0' # Ruta estática predefinida para este sensor

    def iniciar_hilo(self):
        """Lanza el demonio de muestreo ambiental en segundo plano."""
        threading.Thread(target=self._bucle_lectura, daemon=True).start()

    def _bucle_lectura(self):
        """Rutina de análisis léxico sobre protocolo ASCII."""
        arduino = None
        while True:
            try:
                # Intentos continuos de apertura de puerto serie a 115200 bps
                if not arduino:
                    arduino = serial.Serial(self.puerto, 115200, timeout=1)
                
                # Consumo de buffer si existe trama pendiente
                if arduino.in_waiting > 0:
                    linea = arduino.readline().decode('utf-8', errors='ignore').strip()
                    # Validación de cabecera de trama esperada (Prefijo T:)
                    if linea.startswith('T:'):
                        partes = linea.split(',')
                        self.state['telemetry']['temp_ext'] = round(float(partes[0].split(':')[1]), 2)
                        self.state['telemetry']['presion'] = round(float(partes[1].split(':')[1]), 2)
            except Exception:
                # Tolerancia a desconexión física de hardware
                arduino = None
                time.sleep(2)