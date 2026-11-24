"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres
MÓDULO: Nodo Transmisor 
Archivo: tx_node.py
DESCRIPCIÓN: Gestiona la capa de enlace saliente (TX) del robot. Utiliza sockets UDP 
             en modo difusión (Broadcast) para inyectar telemetría y comandos en la red 
             de forma asíncrona, tolerando pérdidas de paquetes sin bloquear el chasis.
"""

import socket
import threading
import queue
import json
import time
import config
import psutil
from modulos.logger import log
import modulos.robot_ctrl as robot_ctrl

def obtener_ip_broadcast():
    """
    Escanea las interfaces de red físicas a nivel de SO y detecta dinámicamente 
    la dirección de difusión (Broadcast) de la subred activa.
    Esto permite que el enjambre opere de forma rapida y facil sin internet 
    ni IPs estáticas previas.
    """
    for interfaz, direcciones in psutil.net_if_addrs().items():
        for addr in direcciones:
            # Filtramos interfaces IPv4 que soporten broadcast, ignorando localhost
            if addr.family == socket.AF_INET and addr.broadcast and addr.address != '127.0.0.1':
                return addr.broadcast
    # Fallback global si falla el escaneo de interfaces
    return '255.255.255.255'

# Resolución en tiempo de carga: Se calcula una sola vez al arrancar el módulo
# para no sobrecargar la CPU escaneando las tarjetas de red en cada iteración.
IP_BROADCAST = obtener_ip_broadcast()

class Transmisor(threading.Thread):
    """
    Clase principal del nodo transmisor. 
    Hereda de threading.Thread para ejecutarse en segundo plano (daemon) y no bloquear 
    el bucle principal de control de motores u otros sensores.
    """
    def __init__(self, mi_id: str):
        super().__init__(daemon=True)
        self.puerto = config.PUERTO_COMANDOS
        
        # Uso de una cola Thread-Safe para desacoplar el hilo que genera los comandos
        # del hilo que los inyecta en la tarjeta de red. Evita cuellos de botella I/O.
        self.cola_mensajes = queue.Queue()
        self.mi_id = mi_id
        
        # Configuración del socket de bajo nivel:
        # AF_INET = IPv4 | SOCK_DGRAM = Protocolo UDP (Sin estado, latencia mínima)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Habilitación explícita en el kernel de Linux para permitir envío Broadcast
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def enviar_comando(self, destino: str, comando_str: str):
        """
        Punto de entrada público. Empaqueta directivas en JSON y las
        encola para su transmisión asíncrona.
        """
        sobre = {
            "origen": self.mi_id,
            "destino": destino,
            "tipo": "COMANDO",
            "payload": comando_str
        }
        self.cola_mensajes.put(sobre)

    def _hilo_latido(self):
        """
        Cronograma de Telemetría.
        Hilo secundario interno dedicado exclusivamente a disparar la telemetría COMPLETA 
        (salud, sensores ambientales y cinemática) a la red para la Estación de Tierra.
        """
        while True:
            time.sleep(0.5) # Frecuencia de actualización: 2 Hz
            
            try:
                # Lectura integral de los sensores a través de la Capa de Abstracción (HAL)
                datos_completos = robot_ctrl.obtener_telemetria()
                
                latido = {
                    "origen": self.mi_id,
                    "destino": "ALL",
                    "tipo": "HEARTBEAT",
                    "payload": datos_completos
                }
                
                # Inyección del datagrama en el medio físico
                self.sock.sendto(json.dumps(latido).encode('utf-8'), (IP_BROADCAST, self.puerto))
                
            except Exception:
                # Fallo silencioso: En telemetría UDP, si un frame falla, se descarta. 
                # No se reintenta para evitar latencia acumulada (Head-of-Line Blocking).
                pass

    def run(self):
        """
        Bucle infinito del hilo transmisor. Ejerce de Consumidor en el patrón Productor-Consumidor.
        Extrae los comandos de la cola Thread-Safe y los despacha por la antena de radio.
        """
        log.info(f"Nodo TX activo. Emitiendo latido como '{self.mi_id}'")
        
        # Despliegue concurrente del subsistema de latidos
        threading.Thread(target=self._hilo_latido, daemon=True).start()
        
        while True:
            # Lectura bloqueante: El hilo duerme eficientemente aquí hasta que haya un elemento en la cola
            paquete = self.cola_mensajes.get()
            try:
                self.sock.sendto(json.dumps(paquete).encode('utf-8'), (IP_BROADCAST, self.puerto))
            except Exception as e:
                log.error(f"Error TX Broadcast: {e}")
            finally:
                # Confirmación a la estructura de datos de que el paquete ha sido procesado
                self.cola_mensajes.task_done()


# INSTANCIACIÓN GLOBAL DEL MÓDULO 
# Lee el nombre automáticamente de la configuración.
nodo_tx = Transmisor(config.ROBOT_ID)