"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres
MÓDULO: Streamer de Cámara 
ARCHIVO:camera_stream.py
DESCRIPCIÓN: Controlador de visión artificial con arquitectura de Doble Flujo.
             Realiza capturas en Alta Definición (720p) para persistencia pericial en local (SD),
             al mismo tiempo que realiza un 'downsampling' (480p) para inyectar vídeo de 
             baja latencia sobre la red vía FFmpeg/UDP. 
             Implementa gestión energética apagando el sensor si no hay clientes activos.
"""

import cv2
import time
import os
import threading
import subprocess
import datetime
from modulos.logger import log

class ModuloCamara:
    def __init__(self, state_dict):
        # Referencia al Single Source of Truth del UGV
        self.state = state_dict 
        
        # Lock de concurrencia para evitar condiciones de carrera (Race Conditions)
        # al modificar el contador de clientes desde múltiples hilos de red.
        self.frame_lock = threading.Lock()
        self.camera = None
        
        # Configuración del túnel multimedia (UDP)
        # Nota: La IP_PORTATIL se actualiza dinámicamente desde rx_node.py cuando la GCS solicita el vídeo
        self.IP_PORTATIL = "127.0.0.1" 
        self.PUERTO_UDP = 5000
        self.ffmpeg_process = None

        # Creación del árbol de directorios para evidencias periciales (Edge Storage)
        self.base_dir = "media"
        os.makedirs(os.path.join(self.base_dir, "fotos"), exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "videos"), exist_ok=True)
        
        # Banderas de estado asíncrono
        self.take_photo_flag = False
        self.is_recording = False
        self.video_writer = None
        
        self.is_running = False
        self.capture_thread = None
        
        # Sistema de gestión energética por suscripción (On-Demand)
        self.clientes_activos = 0
        
        log.info("[CÁMARA] Módulo cargado en modo reposo (UDP-MPEG).")

    # GESTIÓN DEL CICLO DE VIDA 
    def conectar_cliente(self):
        """
        Registra una suscripción al flujo de vídeo (Web o Grabación Local).
        Si el sensor estaba dormido para ahorrar batería, despierta el hilo de E/S.
        """
        with self.frame_lock:
            self.clientes_activos += 1
            if not self.is_running:
                self.is_running = True
                self.capture_thread = threading.Thread(target=self._bucle_captura, daemon=True)
                self.capture_thread.start()

    def desconectar_cliente(self):
        """
        Anula una suscripción. Si no quedan clientes ni grabaciones activas, 
        señaliza al hilo de captura para que proceda al apagado ordenado del hardware.
        """
        with self.frame_lock:
            self.clientes_activos -= 1
            if self.clientes_activos <= 0:
                self.clientes_activos = 0
                if not self.is_recording:
                    self.is_running = False

    def start_stream(self):
        """Interfaz pública llamada por el parser de comandos de red"""
        self.conectar_cliente()
        
    def stop_stream(self):
        """
        Freno de emergencia directo. 
        Sobrescribe el sistema de clientes y fuerza la detención inmediata del servicio.
        """
        with self.frame_lock:
            self.clientes_activos = 0
            self.is_running = False
        # El hilo _bucle_captura detectará self.is_running == False y llamará a _apagar_camara()

    # CONTROLADORES FÍSICOS DEL HARDWARE
    def _encender_camara(self):
        """
        Inicializa el sensor de visión.
        Implementa un sistema de tolerancia a fallos de enumeración USB en Linux.
        """
        # BUCLE DE REINTENTO: 
        # Si el robot se acaba de reiniciar, el kernel de Linux puede tardar unos
        # segundos en soltar el bloqueo del archivo /dev/video0.
        intentos = 0
        while (self.camera is None or not self.camera.isOpened()) and intentos < 5:
            self.camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
            if not self.camera.isOpened(): 
                self.camera = cv2.VideoCapture(-1, cv2.CAP_V4L2) # Escaneo genérico
            if not self.camera.isOpened():
                time.sleep(0.5)
                intentos += 1
                
        if self.camera and self.camera.isOpened():
            # 720p HD MJPEG: Reduce la carga del bus USB I/O solicitando 
            # al sensor que comprima los fotogramas físicamente en silicio.
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.camera.set(cv2.CAP_PROP_FPS, 30)
            
            # Anti-Lag: Minimiza la cola de fotogramas viejos en la RAM de OpenCV
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            log.info("[CÁMARA] Sensor ENCENDIDO.")
            self._iniciar_tuberia_udp()
        else:
            log.error("[CÁMARA] Fallo crítico: Hardware inaccesible tras 5 intentos.")
            self.is_running = False

    def _iniciar_tuberia_udp(self):
        """
        Levanta el subproceso de transcodificación FFmpeg.
        Recibe fotogramas matemáticamente redimensionados (480p) vía pipe (stdin) 
        y los encapsula en MPEG-TS sobre UDP para máxima penetración táctica de red.
        """
        import subprocess
        try:
            # Purga drástica del kernel: Asesina cualquier instancia zombi previa (SIGKILL -9)
            subprocess.run(["pkill", "-9", "ffmpeg"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass
            
        comando = [
            'ffmpeg', '-y',
            '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', '640x480', '-pix_fmt', 'bgr24', '-r', '30',
            '-i', '-', 
            '-f', 'mpegts', '-codec:v', 'mpeg1video', '-pix_fmt', 'yuv420p', '-s', '640x480', '-b:v', '1500k',
            '-bf', '0', f'udp://{self.IP_PORTATIL}:{self.PUERTO_UDP}'
        ]
        
        # stdin=PIPE: Habilita la inyección binaria directa desde el bucle de Python
        self.ffmpeg_process = subprocess.Popen(comando, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        log.info(f"[CÁMARA] Tubería hacia {self.IP_PORTATIL} (Re)abierta.")

    def _apagar_camara(self):
        """
        Secuencia de apagado seguro (Teardown). 
        Garantiza que no se corrompan los archivos de vídeo pericial (cerrando el Writer)
        y evita fugas de memoria al liberar explícitamente los recursos V4L2.
        """
        self.is_running = False
        
        if self.is_recording and self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            self.is_recording = False
            
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.kill()
            except Exception:
                pass
            self.ffmpeg_process = None
            
        try:
            subprocess.run(["pkill", "-9", "ffmpeg"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        except Exception:
            pass

        if self.camera and self.camera.isOpened():
            self.camera.release()
            self.camera = None
            log.info("[CÁMARA] 💤 Sensor y tubería FFmpeg APAGADOS.")

    # INTERFACES DE ACCIÓN (COMMAND HANDLERS)
    def take_photo(self): 
        """Señaliza al hilo de captura que intercepte el próximo frame en alta resolución"""
        self.take_photo_flag = True
    
    def cambiar_zoom(self, incremento):
        z = self.state.get('zoom_level', 1.0)
        z = max(1.0, min(3.0, z + incremento))
        self.state['zoom_level'] = z
        return round(z, 1)

    def toggle_grabacion(self):
        """
        Alterna el volcado a disco de evidencia pericial. 
        Se asocia como un cliente más para forzar el encendido de la cámara si estaba dormida.
        """
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.conectar_cliente()
        else:
            self.desconectar_cliente()
        return self.is_recording

    # BUCLE PRINCIPAL 
    def _bucle_captura(self):
        """
        Núcleo asíncrono. Lee el hardware, aplica matemáticas de interpolación 
        (Zoom/Redimensionado) y despacha la información a disco y red.
        """
        self._encender_camara()
        if not self.camera or not self.camera.isOpened():
            self.is_running = False
            return

        while self.is_running:
            ret, frame = self.camera.read()
            if not ret: 
                # Freno de mano si hay latencia I/O en el bus USB
                time.sleep(0.1)
                continue
            
            # ZOOM DIGITAL MULTI-EJE (Centro Óptico) 
            z = self.state.get('zoom_level', 1.0)
            if z > 1.0:
                h, w = frame.shape[:2]
                cw, ch = int(w/z), int(h/z)
                x1, y1 = max(0, w//2 - cw//2), max(0, h//2 - ch//2)
                # Recorte y redimensionado algorítmico al vuelo
                frame = cv2.resize(frame[y1:y1+ch, x1:x1+cw], (w, h))

            # EVIDENCIA PERICIAL: FOTO (HD 720p) 
            if self.take_photo_flag:
                ruta = os.path.join(self.base_dir, "fotos", f"pic_{datetime.datetime.now().strftime('%H%M%S')}.jpg")
                cv2.imwrite(ruta, frame)
                log.info(f"[CÁMARA] Evidencia fotográfica persistida: {ruta}")
                self.take_photo_flag = False

            #  EVIDENCIA PERICIAL: VÍDEO (HD 720p @ 15fps)
            # Optimizado en framerate (15.0) para balancear tamaño de archivo en la MicroSD
            if self.is_recording:
                if self.video_writer is None:
                    ruta_v = os.path.join(self.base_dir, "videos", f"vid_{datetime.datetime.now().strftime('%H%M%S')}.avi")
                    self.video_writer = cv2.VideoWriter(ruta_v, cv2.VideoWriter_fourcc(*'XVID'), 15.0, (1280, 720))
                self.video_writer.write(cv2.resize(frame, (1280, 720))) # Seguridad dimensional por si cambia el input
            elif self.video_writer is not None:
                self.video_writer.release()
                self.video_writer = None

           # TRANSMISIÓN TÁCTICA (DOWNSAMPLING A 480p)
            if self.ffmpeg_process:
                # 1. WATCHDOG FFMPEG: Comprobamos si el subproceso hijo ha muerto en silencio 
                # por un colapso en la tabla de enrutamiento o latencia extrema de red.
                if self.ffmpeg_process.poll() is not None:
                    log.warning("[CÁMARA] Tubería asfixiada por red. Auto-resucitando FFmpeg...")
                    self._iniciar_tuberia_udp()
                else:
                    # Estrategia Dual-Stream: Se baja drásticamente la resolución del fotograma 
                    # antes de empaquetarlo para garantizar baja latencia sobre enlaces Wi-Fi débiles.
                    frame_web = cv2.resize(frame, (640, 480))
                    try:
                        self.ffmpeg_process.stdin.write(frame_web.tobytes())
                    except BrokenPipeError:
                        # 2. WATCHDOG FÍSICO: Si la tubería se rompe durante la inyección de bytes
                        log.warning("[CÁMARA] Tubería rota (BrokenPipeError). Reiniciando...")
                        self._iniciar_tuberia_udp()
                    except Exception: 
                        pass

            # Relajación del procesador. Limitador de velocidad del bucle ~100Hz
            time.sleep(0.01)
            
        # Cuando el bucle termina (por orden de desconexión), se asegura el apagado
        self._apagar_camara()

    def __del__(self): 
        """Seguro de vida en caso de caída (Crash) del intérprete Python"""
        self._apagar_camara()