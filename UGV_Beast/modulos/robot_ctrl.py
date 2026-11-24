"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres.
MÓDULO: Controlador Central de Hardware 
ARCHIVO: robot_ctrl.py
DESCRIPCIÓN: Capa de Abstracción de Hardware específica para la arquitectura Beast.
             Centraliza el estado del robot y aísla la ejecución de comandos físicos 
             mediante una cola Thread-Safe, evitando bloqueos y colisiones de I/O 
             en el puente serie (UART) de la placa base (ESP32).
"""

import time
import queue
import threading
from config import INITIAL_STATE
from modulos.logger import log


# VARIABLES DE ESTADO GLOBAL 
# Instanciación en memoria RAM del estado base extraído de config.py
estado_global = INITIAL_STATE.copy()

# Registro de conciencia situacional de la malla táctica (Swarm Awareness)
flota_aliada = {}

# Puntero a la clase agregadora del hardware.
# Se inyecta en tiempo de ejecución desde main.py
instancia_robot = None 

# Cola de tareas (Queue). 
# Actúa como buffer concurrente. Múltiples hilos de red (RX, Servidor Web)
# pueden encolar directivas simultáneas sin corromper el bus de comunicaciones serie.
cola_hw = queue.Queue()


# SUBSISTEMA DE PROCESAMIENTO HARDWARE (WORKER THREAD)
def procesador_hardware():
    """
    Worker Thread asíncrono.
    Es el ÚNICO hilo con permiso lógico para invocar los métodos del hardware físico,
    garantizando la serialización de comandos hacia el microcontrolador.
    """
    while True:
        # Llamada bloqueante: El hilo duerme eficientemente hasta recibir una directiva
        tarea = cola_hw.get()
        accion = tarea.get("accion")
        datos = tarea.get("datos")

        try:
            # Seguro de vida: Previene caídas si la red envía comandos antes de que
            # la placa base haya terminado su secuencia de arranque (Boot Sequence).
            if not instancia_robot or not instancia_robot.base: continue
            
            # --- RUTADO DE COMANDOS CINEMÁTICOS Y ACTUADORES ---
            if accion == "chasis_dinamico":
                # Control en lazo cerrado (Navegación Autónoma o Joystick Analógico)
                # Escala los vectores normalizados (0.0 - 1.0) por el limitador de velocidad global
                s = estado_global.get('speed', 0.6)
                instancia_robot.base.base_speed_ctrl(datos['L'] * s, datos['R'] * s)
                
            elif accion == "chasis_tecla":
                # Control Discreto / Lazo Abierto (Teleoperación de Emergencia con Teclado WASD)
                v = estado_global.get('speed', 0.6)
                if datos == 'W': instancia_robot.base.base_speed_ctrl(v, v)
                elif datos == 'S': instancia_robot.base.base_speed_ctrl(-v, -v)
                elif datos == 'A': instancia_robot.base.base_speed_ctrl(-v, v)
                elif datos == 'D': instancia_robot.base.base_speed_ctrl(v, -v)
                elif datos == 'STOP': instancia_robot.base.base_speed_ctrl(0, 0)
                
            elif accion == "camara_absoluto":
                # Control de Visión 
                instancia_robot.hw.move_gimbal(datos['pan'], datos['tilt'])
                
            elif accion == "velocidad":
                # Modificador del multiplicador escalar 
                instancia_robot.hw.set_speed(datos)
                
            elif accion == "luces":
                # Baliza táctica de señalización 
                instancia_robot.hw.toggle_lights()
                
        except Exception as e:
            log.error(f"[ROBOT_CTRL] Error en bus de hardware UART: {e}")
        finally:
            # Confirmación a la estructura concurrente de que el candado se libera
            cola_hw.task_done()

# Arranque del demonio de hardware de forma autónoma al importar el módulo
threading.Thread(target=procesador_hardware, daemon=True).start()


# FUNCIONES PUENTE (INTERFAZ DE PROGRAMACIÓN DE APLICACIONES - API)
def mover_chasis_dinamico(L: float, R: float): 
    cola_hw.put({"accion": "chasis_dinamico", "datos": {"L": L, "R": R}})
    
def mover_chasis(comando: str): 
    # KILL-SWITCH: Si es una orden de freno de emergencia, 
    # se borran agresivamente las tareas acumuladas en la memoria para garantizar 
    # que el microcontrolador aplique el freno en el siguiente ciclo de reloj.
    if comando == "STOP":
        with cola_hw.mutex:
            cola_hw.queue.clear()
            
    cola_hw.put({"accion": "chasis_tecla", "datos": comando})
    
def mover_camara_absoluto(pan: int, tilt: int): 
    cola_hw.put({"accion": "camara_absoluto", "datos": {"pan": pan, "tilt": tilt}})
    
def cambiar_velocidad(val: str): 
    cola_hw.put({"accion": "velocidad", "datos": val})
    
def toggle_luces(): 
    cola_hw.put({"accion": "luces", "datos": None})


# SUBSISTEMA DE COMUNICACIONES TÁCTICAS Y ESTADO GLOBAL
def ejecutar_mision(datos: dict):
    """Inyecta coordenadas (Waypoints) recibidas por radio en la IA de navegación local"""
    if instancia_robot and hasattr(instancia_robot, 'navegacion'):
        instancia_robot.navegacion.set_target(datos.get('lat'), datos.get('lon'), datos.get('zones', []))

def actualizar_aliado(id_aliado: str, datos_vitales: dict):
    """Actualiza la posición del nodo compañero y estampa la marca de tiempo (Timestamp) local"""
    datos_vitales['ultimo_visto'] = time.time()
    flota_aliada[id_aliado] = datos_vitales

# Puntero para la inyección del módulo de IA
nav_thread_ref = None

def vincular_navegador(nav):
    """Guarda la referencia del algoritmo de navegación"""
    global nav_thread_ref
    nav_thread_ref = nav

def parada_tactica_global():
    """Aborto de misión: Detiene la navegación y clava los frenos físicos del hardware"""
    if nav_thread_ref: 
        nav_thread_ref.stop_nav()
    mover_chasis("STOP")

def obtener_telemetria():
    """
    Empaquetador de Telemetría.
    Recopila el estado lógico, sensores medioambientales, cinemática y métricas 
    del sistema operativo para inyectarlo en los datagramas UDP.
    """
    # Polling bajo demanda de métricas del procesador (Sysstat)
    if instancia_robot: instancia_robot.telemetria.update_telemetry()

    return {
        # Odometría y Navegación Espacial
        "curr_lat": estado_global.get("curr_lat", 0.0),
        "curr_lon": estado_global.get("curr_lon", 0.0),
        "heading": estado_global.get("heading", 0.0),
        "sats": estado_global.get("sats", 0),
        "nav_state": estado_global.get("nav_state", "ESPERANDO"), 
        
        # Percepción de Entorno (LiDAR Segmentado)
        "lidar_frontal_cm": estado_global.get("lidar_frontal_cm", "--"),
        "lidar_derecha_cm": estado_global.get("lidar_derecha_cm", "--"),
        "lidar_izquierda_cm": estado_global.get("lidar_izquierda_cm", "--"),
        "obstaculo_critico": estado_global.get("obstaculo_critico", False),
        
        # Compatibilidad Retroactiva
        "distancia": estado_global.get("lidar_frontal_cm", "--"),
        
        # Telemetría Ambiental y Enlaces
        "telemetry": {
            "temp": estado_global.get("telemetry", {}).get("temp_ext", "--"),
            "pres": estado_global.get("telemetry", {}).get("presion", "--"),
            "wifi": estado_global.get("telemetry", {}).get("wifi", 100)
        },
        "wifi_critico": estado_global.get("wifi_critico", False),
        
        # Auditoría del Hardware Base (SBC)
        "sys": {
            "cpu": estado_global.get("telemetry", {}).get("cpu", 0),
            "ram": estado_global.get("telemetry", {}).get("ram", 0)
        }
    }