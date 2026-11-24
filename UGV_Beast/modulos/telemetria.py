"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres.
MÓDULO: Monitorización de Constantes Vitales 
ARCHIVO: telemetria.py
DESCRIPCIÓN: Subsistema de auditoría interna. Monitoriza el rendimiento 
             del Single Board Computer (SBC) a nivel de sistema operativo (Linux), 
             extrayendo métricas de carga de CPU, consumo de memoria, estrés térmico 
             y calidad de la capa física del enlace de radio Wi-Fi.
"""

import os
import psutil
import time
import subprocess
import re

class ModuloTelemetria:
    """
    Agente de recolección de métricas del sistema.
    Actualiza el estado global de forma segura, inyectando los datos de hardware
    que posteriormente se retransmitirán por la red.
    """
    def __init__(self, state_dict):
        # Enlace por referencia al estado global (Single Source of Truth)
        self.state = state_dict
        
        # Temporizador de estrangulamiento
        # Almacena la marca de tiempo de la última lectura completada.
        self.ultima_actualizacion = 0  

    def update_telemetry(self):
        """
        Lee el hardware utilizando un patrón de 'Debouncing' temporal.
        Garantiza que las operaciones de E/S del sistema operativo no saturen 
        el hilo principal del programa.
        """
        ahora = time.time()
        
        # RATE LIMITER: Restricción de muestreo a un máximo de 2 Hz.
        # Si la última lectura fue hace menos de 500 ms, se aborta la ejecución
        # devolviendo el control al hilo principal inmediatamente (Cero Lag).
        if ahora - self.ultima_actualizacion < 0.5:
            return 
            
        self.ultima_actualizacion = ahora
        
        try:
            #  MÉTRICAS DE CÓMPUTO (CPU / RAM) 
            # Lecturas no bloqueantes del rendimiento del procesador y memoria volátil
            self.state['telemetry']['cpu'] = psutil.cpu_percent()
            self.state['telemetry']['ram'] = psutil.virtual_memory().percent
            
            # MÉTRICAS TÉRMICAS (Sensores internos)
            # Acceso directo al subsistema sysfs de Linux (Válido para arquitecturas ARM como Raspberry Pi)
            # Evita el uso de librerías pesadas externas leyendo el archivo nativo del kernel.
            if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    # El kernel reporta la temperatura en miligrados Celsius. Se normaliza a 1 decimal.
                    self.state['telemetry']['temp'] = round(int(f.read())/1000.0, 1)
            
            # LECTURA DEL ENLACE DE RADIO  
            wifi = 100 
            try:
                # Ejecución de sub-shell para interrogar al driver de red inalámbrica
                salida = subprocess.getoutput("iwconfig")
                
                # Extracción mediante Expresiones Regulares de la métrica 'Link Quality'
                match = re.search(r"Link Quality=(\d+)/(\d+)", salida)
                if match:
                    calidad = float(match.group(1))
                    maximo = float(match.group(2))
                    # Normalización a porcentaje (0-100%)
                    wifi = int((calidad / maximo) * 100)
            except Exception: 
                # Failsafe: Si el adaptador Wi-Fi se desconecta físicamente o el comando falla,
                # se absorbe el error para no colapsar el UGV.
                pass
            
            # Inyección en el estado global
            self.state['telemetry']['wifi'] = wifi
            
            # DISPARADOR DE ALARMA (Watchdog de Comunicaciones):
            # Si la calidad del enlace cae por debajo del 50%, se activa la bandera crítica.
            # Esta bandera es leída por la IA de navegación para abortar la misión preventivamente.
            self.state['wifi_critico'] = (wifi < 50)
            
        except Exception as e:
            # Los errores esporádicos de I/O en la recolección de telemetría no 
            # deben interrumpir jamás el funcionamiento del dron. Se ignoran silenciosamente.
            pass