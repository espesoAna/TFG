"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres.
MÓDULO: Nodo Receptor 
ARCHIVO: rx_node.py
DESCRIPCIÓN: Escucha de forma pasiva y asíncrona la subred (UDP).
             Desempaqueta los datagramas JSON y enruta las órdenes hacia los actuadores.
"""

import socket
import threading
import json
import config
from modulos.logger import log
import modulos.robot_ctrl as robot_ctrl

class Receptor(threading.Thread):
    """
    Hilo demonio dedicado a la ingesta pasiva de red. 
    Opera sin bloquear el hilo principal de ejecución.
    """
    def __init__(self, mi_id: str):
        super().__init__(daemon=True)
        self.puerto = config.PUERTO_COMANDOS
        self.mi_id = mi_id
        
        # Inicialización del socket UDP
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # SO_REUSEADDR y SO_REUSEPORT: Directivas a nivel de sistema operativo
        # Permiten reiniciar el proceso y volver a enlazar el puerto sin caer 
        # en estados de bloqueo TIME_WAIT del kernel de Linux.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, 'SO_REUSEPORT'):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        
        # Bind a '0.0.0.0': El dron escucha en todas sus interfaces físicas (Wi-Fi, Ad-Hoc, etc.)
        self.sock.bind(('0.0.0.0', self.puerto))

    def run(self):
        """
        Bucle infinito de escucha. Implementa el patrón 'Command' para decodificar
        y despachar las directivas tácticas entrantes.
        """
        log.info(f"Nodo RX activo. Escuchando como '{self.mi_id}'")
        while True:
            try:
                # Llamada bloqueante: El hilo duerme hasta recibir datagramas (Buffer: 2048 bytes)
                data, addr = self.sock.recvfrom(2048)
                paquete = json.loads(data.decode('utf-8'))
                
                origen = paquete.get("origen")
                destino = paquete.get("destino")
                tipo = paquete.get("tipo")
                payload = paquete.get("payload")
                
                #FILTRO LÓGICO DE CAPA 7
                # 1. Descarte de eco (Broadcast propio)
                if origen == self.mi_id: continue
                # 2. Descarte de tráfico ajeno, salvo comandos globales ("ALL")
                if destino != self.mi_id and destino != "ALL": continue
                
                #ENRUTAMIENTO DE DATOS
                # 1. TELEMETRÍA (Conciencia situacional del enjambre)
                if tipo == "HEARTBEAT":
                    robot_ctrl.actualizar_aliado(origen, payload)
                
                # 2. PROCESAR COMANDO 
                elif tipo == "COMANDO":
                    
                    # Interrupción Crítica: Freno incondicional de emergencia
                    if payload == "STOP":
                        log.warning(f"Orden EMERGENCIA (Freno Total) de {origen}")
                        robot_ctrl.parada_tactica_global() 
                        
                    elif isinstance(payload, dict):
                        # A. Misión Autónoma (Navegación por Waypoints GPS)
                        if "lat" in payload:
                            log.info(f"Misión recibida.")
                            robot_ctrl.ejecutar_mision(payload) 
                            
                        # B. Teleoperación Directa (Joystick y Periféricos)
                        elif "action" in payload:
                            accion = payload["action"]
                            
                            # Subsistema Cinemático
                            if accion == "chasis":
                                robot_ctrl.mover_chasis(payload["cmd"])
                                
                            # Subsistema Óptico (Gimbal)
                            elif accion == "camara_absoluto":
                                robot_ctrl.mover_camara_absoluto(payload.get("pan", 90), payload.get("tilt", 90))
                            elif accion == "camara_center":
                                # Adaptación Hardware: El offset central del servo en el Beast corresponde a (90, 90)
                                robot_ctrl.mover_camara_absoluto(90, 90) 
                                
                            # Subsistema de Tracción
                            elif accion == "velocidad":
                                # TRADUCTOR HARDWARE: Convierte el vector numérico del mando en 
                                # literales ('up'/'down') esperados por el controlador de este chasis.
                                direccion = "up" if payload["val"] > 0 else "down"
                                robot_ctrl.cambiar_velocidad(direccion)
                                
                            # Subsistema Eléctrico Auxiliar
                            elif accion == "luces":
                                robot_ctrl.toggle_luces()
                                
                            # Subsistema Multimedia L4 (UDP Streaming)
                            elif accion == "video_start":
                                if hasattr(robot_ctrl, 'cam_streamer') and robot_ctrl.cam_streamer is not None:
                                    # Atrapamos la IP real de origen en capa 3 para establecer el vídeo de vuelta
                                    robot_ctrl.cam_streamer.IP_PORTATIL = addr[0]
                                    robot_ctrl.cam_streamer.start_stream()
                            elif accion == "video_stop":
                                if hasattr(robot_ctrl, 'cam_streamer') and robot_ctrl.cam_streamer is not None:
                                    robot_ctrl.cam_streamer.stop_stream()
                                    
                            # Subsistema de Evasión
                            elif accion == "radar":
                                # PATRÓN NULL OBJECT: El UGV Beast carece de servo panorámico para el radar.
                                # Se absorbe el comando de red sin levantar excepciones para mantener
                                # la compatibilidad del protocolo dentro del enjambre heterogéneo.
                                pass 
                                
                            # Subsistema Pericial local (Tarjeta SD)
                            elif accion == "photo":
                                if hasattr(robot_ctrl, 'cam_streamer') and robot_ctrl.cam_streamer is not None:
                                    robot_ctrl.cam_streamer.take_photo()
                                    log.info("Orden de captura fotográfica recibida.")
                            elif accion == "record":
                                if hasattr(robot_ctrl, 'cam_streamer') and robot_ctrl.cam_streamer is not None:
                                    grabando = robot_ctrl.cam_streamer.toggle_grabacion()
                                    estado = "INICIADA" if grabando else "DETENIDA"
                                    log.info(f"Grabación de vídeo local {estado}.")
                            elif accion == "zoom":
                                try:
                                    valor = float(payload.get("val", 0))
                                    if hasattr(robot_ctrl, 'cam_streamer') and robot_ctrl.cam_streamer is not None:
                                        robot_ctrl.cam_streamer.cambiar_zoom(valor)
                                        log.info(f" Zoom digital ajustado: {valor}")
                                    else:
                                        log.error(" Error: Objeto cam_streamer no vinculado.")
                                except Exception as e:
                                    log.error(f"Error procesando zoom: {e}")
                        
                    # Lógica redundante de seguridad para ejecución de misión
                    elif isinstance(payload, dict) and "lat" in payload:
                        log.info(f"Misión de {origen} recibida.")
                        # Llama a la función puente del controlador central
                        robot_ctrl.ejecutar_mision(payload) 
                        
            except json.JSONDecodeError: 
                # Descarte silencioso de paquetes de radio corruptos o malformados
                pass
            except Exception as e: 
                log.error(f"Error RX irrecuperable en capa de enlace: {e}")


# INSTANCIACIÓN GLOBAL DEL MÓDULO 
nodo_rx = Receptor(config.ROBOT_ID)