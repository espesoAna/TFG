"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres
MÓDULO: Arranque y Agregador de Hardware UGV Beast 
ARCHIVO: app_ugv.py
DESCRIPCIÓN: Punto de entrada  del nodo UGV Beast. 
             Se encarga de la instanciación de todos los subsistemas (sensores, 
             cámara, navegación), levanta los hilos de comunicaciones de la red
             y vincula el hardware físico con la capa de control.
"""

import threading
import time
import sys

from modulos.logger import log
from config import NAV_PARAMS

# Controlador físico de bajo nivel (Comunicación Serial con el microcontrolador)
from base_ctrl import BaseController

# SUBSISTEMAS DE PERCEPCIÓN Y ESTADO 
from modulos.telemetria import ModuloTelemetria
from modulos.gps_imu import ModuloGPS_IMU
from modulos.hardware import ModuloHardware
from modulos.entorno import ModuloEntorno      
from modulos.lidar import ModuloLidar          


# SUBSISTEMAS DE ALTO NIVEL Y C2 (Command & Control)
from modulos.camera_stream import ModuloCamara
from modulos.navigator import ModuloNavegacion
import modulos.robot_ctrl as rc
from modulos.tx_node import nodo_tx
from modulos.rx_node import nodo_rx

class UGVBeast:
    """
    Clase Agregadora.
    Encapsula la complejidad del hardware del chasis y expone una interfaz unificada
    para que la capa de red y la inteligencia artificial puedan operar el robot.
    """
    def __init__(self):
        # Referencia al Single Source of Truth (Diccionario central de estado)
        self.state = rc.estado_global
        
        try:
            # Establecimiento del bus Serial (UART) con la placa base (ESP32/Arduino)
            self.base = BaseController('/dev/serial0', 115200)
        except Exception as e:
            log.error(f"Error conectando con placa base ESP32: {e}")
            self.base = None # Fallback seguro: permite arrancar el software sin hardware físico para depuración

        # Instanciación de los módulos periféricos pasándole el estado compartido
        self.camara = ModuloCamara(self.state)
        self.telemetria = ModuloTelemetria(self.state)
        self.sensores = ModuloGPS_IMU(self.state)
        self.navegacion = ModuloNavegacion(self.state, NAV_PARAMS, self.base)
        self.hw = ModuloHardware(self.state, self.base)
        self.entorno = ModuloEntorno(self.state) 
        
        # Nota: Aunque se instancia el objeto software para mantener la simetría 
        # de la API (evitando excepciones de dependencias cruzadas en el enjambre), 
        # la plataforma UGV Beast no cuenta con un sensor LiDAR físico por defecto en su hardware.
        self.lidar = ModuloLidar(self.state, self.base)

def main():
    """
    Rutina principal de la secuencia de arranque.
    """

    # 1. Instanciamos la plataforma física
    robot = UGVBeast()
    if robot.base: 
        robot.hw.init_beast() # Calibración inicial de motores y actuadores

    # 2. Despliegue de la Capa de Red 
    # Levanta los demonios UDP en background para emitir/escuchar la red
    nodo_tx.start()
    nodo_rx.start()

    # 3. Inyección de Dependencias (Vinculación con el HAL)
    # Acopla el hardware real con el controlador lógico para que procese los comandos encolados
    rc.instancia_robot = robot

    # 4. Arranque de los Subsistemas Asíncronos (Sensor Fusion)
    log.info("Encendiendo sensores periféricos...")
    robot.sensores.iniciar_hilo_gps()
    robot.entorno.iniciar_hilo()
    robot.lidar.iniciar_hilo()
    
    # Vinculamos la IA de navegación al controlador central y la arrancamos
    rc.vincular_navegador(robot.navegacion)
    robot.navegacion.start()

    # Vinculamos el módulo de vídeo al controlador central
    rc.cam_streamer = robot.camara

    # 5. Despliegue del Subsistema de Inercia y Bloqueo de Hilo Principal
    log.info("OPERATIVO.")
    if robot.base: 
        robot.sensores.iniciar_hilo_imu(robot.base)
        
    try:
        # El hilo principal se queda durmiendo para no consumir CPU, 
        # cediendo el procesamiento a los múltiples threads en background.
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        # Protocolo de apagado seguro (Graceful Shutdown)
        log.warning("Interrupción de usuario (Ctrl+C). Iniciando apagado...")
        robot.navegacion.stop_nav()
        if robot.camara: 
            robot.camara._apagar_camara() # Corta la tubería FFmpeg de forma limpia
        sys.exit(0)

if __name__ == '__main__':
    import math
    main()