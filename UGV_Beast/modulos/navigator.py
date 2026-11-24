"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres 
MÓDULO: Sistema de Navegación Autónoma y Evasión (UGV Beast)
ARCHIVO: navigator.py

DESCRIPCIÓN:
    Implementa el cerebro de navegación del UGV. Al carecer de un magnetómetro fiable,
    este módulo utiliza una Máquina de Estados híbrida. 
    El robot avanza a ciegas 
    brevemente para deducir su rumbo real basándose en deltas del GPS. Posteriormente, 
    usa un giroscopio en lazo cerrado para mantener líneas rectas perfectas y 
    para giros precisos inmunes al ruido.

    Incluye Interrupciones para Evasión LiDAR (bordeo reactivo)
    y Zonas de exclusión virtuales.
"""

import math
import time
import threading
import modulos.math_utils as math_utils
import modulos.robot_ctrl as rc  
from modulos.logger import log

class ModuloNavegacion(threading.Thread):
    def __init__(self, state_dict, nav_params, base_controller):
        super().__init__(daemon=True)
        self.state = state_dict
        self.params = nav_params 
        self.zonas_prohibidas = []
        
        self.last_cmd_L = 0.0
        self.last_cmd_R = 0.0
        
        # MÁQUINA DE ESTADOS
        self.estado_tactico = "EVALUANDO"
        self.target_heading = 0.0
        self.dist_inicial_tramo = 0.0
        self.velocidad_actual = 0.70
        
        # Temporizadores no bloqueantes para asentar sensores físicos
        self.eval_ticks = 0

    def set_target(self, lat, lon, zonas=None):
        """Inicializa una nueva misión de navegación inyectando un Waypoint objetivo."""
        self.state["target_lat"], self.state["target_lon"] = lat, lon
        self.zonas_prohibidas = zonas if zonas else []
        self.state["active"] = True
        self.state["nav_state"] = "EN_RUTA"
        self.state["is_moving"] = False
        
        # Se fuerza el estado inicial para recalibrar el vector real antes de actuar
        self.estado_tactico = "INICIANDO_DESCUBRIMIENTO" 
        self.last_cmd_L, self.last_cmd_R = 999.0, 999.0 
        log.info(f"[NAV] Misión Vectorial Iniciada -> Destino: Lat {lat:.5f}, Lon {lon:.5f}")

    def stop_nav(self):
        """Aborto de la misión y limpieza de la misión actual."""
        self.state["active"] = False
        self.state["nav_state"] = "ESPERANDO"
        self.state["is_moving"] = False
        rc.mover_chasis("STOP") 
        self.last_cmd_L, self.last_cmd_R = 0.0, 0.0
        log.info("[NAV] Misión abortada.")

    def enviar_comando_seguro(self, L, R, force=False):
        """
        Capa de abstracción para el control de motores.
        Implementa un disparador para los cambios del magnetómetro:
        Si las orugas se mueven, se asume contaminación electromagnética y se avisa al IMU.
        """
        if force or abs(L - self.last_cmd_L) > 0.01 or abs(R - self.last_cmd_R) > 0.01:
            rc.mover_chasis_dinamico(round(L, 3), round(R, 3))
            self.last_cmd_L = L
            self.last_cmd_R = R
            
            # Bandera global de movimiento
            if abs(L) > 0.05 or abs(R) > 0.05:
                self.state["is_moving"] = True
            else:
                self.state["is_moving"] = False

    def calcular_distancia_y_rumbo(self):
        """Resuelve el problema entre la posición actual y el destino."""
        l1, o1 = self.state["curr_lat"], self.state["curr_lon"]
        l2, o2 = self.state["target_lat"], self.state["target_lon"]
        self.state["dist"] = math_utils.calc_distancia(l1, o1, l2, o2)
        target_bearing = math_utils.calc_rumbo_deseado(l1, o1, l2, o2)
        return target_bearing

    def run(self):
        """
        Bucle de control principal (Hilo a 10Hz).
        Respeta una jerarquía estricta:
        1. LiDAR
        2. Zonas Prohibidas
        3. Navegación
        """
        log.info("[NAV] Cerebro de Navegación LUT operativo.")
        
        while True:
            time.sleep(0.1) # Ciclo de reloj a 10Hz

            if not self.state.get("active", False):
                continue

            # Failsafe de conectividad
            if self.state.get('wifi_critico', False):
                self.stop_nav()
                continue 

            # ==============================================================
            # 1.  EVASIÓN LIDAR Y BORDEO REACTIVO 
            # ==============================================================
            # Si el LiDAR lee < 30cm, suspende inmediatamente la ruta.
            if self.state.get('obstaculo_critico', False):
                log.warning("[NAV] LiDAR: Obstáculo inminente detectado. Freno de emergencia.")
                self.enviar_comando_seguro(0.0, 0.0, force=True)
                time.sleep(0.3) # Disipación de inercia cinética
                
                # Evaluación de los flancos para buscar la vía de escape óptima
                izq_str = self.state.get('lidar_izquierda_cm', "--")
                der_str = self.state.get('lidar_derecha_cm', "--")
                dist_izq = 999.0 if izq_str == "--" else float(izq_str)
                dist_der = 999.0 if der_str == "--" else float(der_str)

                girar_izq = dist_izq > dist_der
                cmd_L, cmd_R = (-0.5, 0.5) if girar_izq else (0.5, -0.5)

                log.info(f"[NAV] Evadiendo hacia la {'IZQUIERDA' if girar_izq else 'DERECHA'}...")

                # FASE A: Rotación sobre el eje central hasta despejar el cono frontal
                while self.state.get('obstaculo_critico', False) and self.state.get("active", False):
                    self.enviar_comando_seguro(cmd_L, cmd_R, force=True)
                    time.sleep(0.1)

                if not self.state.get("active", False): continue

                # FASE B: Evita el roce de la parte trasera del chasis al avanzar
                for _ in range(4):
                    if not self.state.get("active", False): break
                    self.enviar_comando_seguro(cmd_L, cmd_R, force=True)
                    time.sleep(0.1)

                # FASE C: Bordeo asimétrico. Arco suave de 2 segundos.
                log.info("[NAV] Morro libre. Ejecutando Bypass lateral (2 seg)...")
                t_bordeo = time.time() + 2.0
                while time.time() < t_bordeo and self.state.get("active", False):
                    if self.state.get('obstaculo_critico', False):
                        break # Ruptura temprana si aparece una nueva pared (esquina interna)
                    
                    # Generación de cinemática diferencial divergente
                    if girar_izq:
                        self.enviar_comando_seguro(0.35, 0.50, force=True) 
                    else:
                        self.enviar_comando_seguro(0.50, 0.35, force=True)
                    time.sleep(0.1)

                self.enviar_comando_seguro(0.0, 0.0, force=True)
                
                # RESET DE LA MÁQUINA DE ESTADOS:
                # Tras la evasión, el dron ha perdido su consciencia espacial. 
                # Se fuerza un nuevo Sprint para recalibrar vectores.
                self.estado_tactico = "INICIANDO_DESCUBRIMIENTO"
                log.info("[NAV] Evasión completada. Reiniciando Sprint Vectorial...")
                continue

            # ==============================================================
            # 2. Evasión de Zonas Prohibidas
            # ==============================================================
            if not self.state.get("fix", False):
                continue

            target_brng = self.calcular_distancia_y_rumbo()
            
            # Condición de victoria (Llegada al destino)
            if self.state["dist"] < self.params['UMBRAL_LLEGADA']:
                self.state["nav_state"] = "LLEGADA"
                self.stop_nav()
                continue

            # Se proyecta la posición a 3.5 metros según el rumbo actual
            futura_lat, futura_lon = math_utils.proyectar_punto_gps(
                self.state["curr_lat"], self.state["curr_lon"], self.state["heading"], 3.5
            )
            # Si el rayo choca con el polígono, se aborta la trayectoria
            if math_utils.evaluar_zona_prohibida(futura_lat, futura_lon, self.zonas_prohibidas):
                log.warning("[NAV] GEOFENCE: Vector choca con Zona Prohibida. Recalculando...")
                
                # Evasión 
                self.enviar_comando_seguro(-0.4, -0.6, force=True) 
                time.sleep(0.8)
                self.enviar_comando_seguro(0.0, 0.0, force=True)
                
                # Reset de navegación
                self.estado_tactico = "INICIANDO_DESCUBRIMIENTO" 
                continue

            # ==============================================================
            # 3. MÁQUINA DE ESTADOS 
            # ==============================================================
            
            if self.estado_tactico == "INICIANDO_DESCUBRIMIENTO":
                # Estado Inicial: Guardar coordenadas exactas pre-movimiento
                self.enviar_comando_seguro(0.0, 0.0)
                self.lat_inicio_sprint = self.state["curr_lat"]
                self.lon_inicio_sprint = self.state["curr_lon"]
                
                self.tiempo_fin_sprint = time.time() + 1.8
                self.estado_tactico = "EN_SPRINT"
                log.info("[NAV] Fase 1: Sprint de descubrimiento iniciado (1.8 seg)...")

            elif self.estado_tactico == "EN_SPRINT":
                # Avance ciego en línea recta para generar un delta geográfico medible
                self.enviar_comando_seguro(self.params['VEL_RECTA'], self.params['VEL_RECTA'])
                
                if time.time() > self.tiempo_fin_sprint:
                    self.enviar_comando_seguro(0.0, 0.0, force=True)
                    self.estado_tactico = "CALCULANDO_VECTOR"
                    self.eval_ticks = 8 # Margen (0.8s) para compensar la latencia (Lag) del bus GPS NMEA
                    log.info("[NAV] Fase 2: Sprint finalizado. Leyendo latencia GPS...")

            elif self.estado_tactico == "CALCULANDO_VECTOR":
                if self.eval_ticks > 0:
                    self.eval_ticks -= 1
                    continue
                
                # Evaluación del vector de traslación resultante
                dist_sprint = math_utils.calc_distancia(
                    self.lat_inicio_sprint, self.lon_inicio_sprint, 
                    self.state["curr_lat"], self.state["curr_lon"]
                )
                
                if dist_sprint >= 0.4: 
                    # Si el desplazamiento es >= 40cm, la matemática supera el margen de error GNSS
                    vector_real = math_utils.calc_rumbo_deseado(
                        self.lat_inicio_sprint, self.lon_inicio_sprint, 
                        self.state["curr_lat"], self.state["curr_lon"]
                    )
                    
                    # Se sobreescribe la orientación con la realidad matemática
                    self.state["heading"] = vector_real
                    log.info(f"[NAV] Fase 3: ÉXITO. Rumbo real sobreescrito: {vector_real:.1f}º (Dist: {dist_sprint:.2f}m)")
                else:
                    log.warning(f"[NAV] Fase 3: Fallo. Sprint muy corto ({dist_sprint:.2f}m). ¿Orugas patinando?")
                
                self.estado_tactico = "EVALUANDO_GIRO"

            elif self.estado_tactico == "EVALUANDO_GIRO":
                # Con la orientación real limpia, se calcula el delta angular hacia el destino
                target_brng = self.calcular_distancia_y_rumbo()
                err_rumbo = (target_brng - self.state["heading"] + 180) % 360 - 180
                
                # Comprobación de histéresis (banda muerta) para evitar jitter
                if abs(err_rumbo) > self.params['TOLERANCIA_ANGULO']: 
                    self.estado_tactico = "ALINEANDO"
                else:
                    self.target_heading = target_brng
                    self.dist_inicial_tramo = self.state["dist"]
                    self.velocidad_actual = 0.65 
                    self.estado_tactico = "AVANZANDO"

            elif self.estado_tactico == "ALINEANDO":
                # Giro en bucle cerrado.
                # Usamos interpolación matemática sobre la LUT de tiempos empíricos.
                err_rumbo = (target_brng - self.state["heading"] + 180) % 360 - 180
                tiempo_giro = math_utils.interpolar_tiempo_giro(err_rumbo, self.params['TIEMPOS_GIRO'])
                
                v_giro = self.params['VEL_GIRO']
                L = v_giro if err_rumbo > 0 else -v_giro
                R = -L
                
                log.info(f"[NAV] Fase 4: LUT -> Girando {err_rumbo:.1f}º en {tiempo_giro:.2f}s")
                
                t_fin = time.time() + tiempo_giro
                while time.time() < t_fin:
                    # Micro-bucle seguro: Sensible al LiDAR incluso en mitad de un giro
                    if not self.state.get("active", False) or self.state.get('obstaculo_critico', False): break
                    self.enviar_comando_seguro(L, R, force=True)
                    time.sleep(0.05)
                    
                self.enviar_comando_seguro(0.0, 0.0, force=True)
                
                # Terminamos el giro y procedemos inmediatamente al avance guiado por giroscopio
                self.estado_tactico = "AVANZANDO" 
                self.target_heading = target_brng
                self.dist_inicial_tramo = self.state["dist"]
                self.velocidad_actual = 0.65

            elif self.estado_tactico == "AVANZANDO":
                # Actualización de rumbo dinámico solo si el punto está lejos (>3m) 
                # Evita giros extraños cuando el UGV está literalmente encima del Waypoint
                if self.state["dist"] > 3.0:
                    self.target_heading = target_brng

                error_hold = (self.target_heading - self.state["heading"] + 180) % 360 - 180
                gz = self.state.get("current_gz", 0.0)
                
                if abs(error_hold) < 4.0:
                    fuerza_rumbo = 0.0 
                else:
                    fuerza_rumbo = error_hold * self.params['KP_RUMBO']
                
                 
                # El Giroscopio (Z) amortigua la corrección para evitar el zig-zag oscilatorio.
                fuerza_gyro = -gz * self.params['KP_GIRO']
                correccion = max(-0.07, min(0.07, fuerza_rumbo + fuerza_gyro)) 
                
                # Rampa de aceleración progresiva para evitar tirones
                if self.velocidad_actual < self.params['VEL_RECTA']: 
                    self.velocidad_actual += 0.015 
                
                v_base = self.velocidad_actual
                
                # Perfil Terminal de Frenado Suave (< 3m)
                if self.state["dist"] < 3.0: 
                    v_base = max(0.40, v_base * (self.state["dist"] / 3.0)) 
                
                self.enviar_comando_seguro(v_base + correccion, v_base - correccion)
                
                # =====================================================
                # FILTROS DE SUPERVIVENCIA Y RE-CALIBRACIÓN VECTORIAL
                # =====================================================
                # 1. Filtro Anti-Salto: Si el GPS devuelve una lectura muy errónea (ej. rebote satelital)
                if abs(error_hold) > 35.0 and self.state["dist"] > 4.0:
                    log.warning(f"[NAV] Desvío grave en ruta ({error_hold:.1f}º). Re-calibrando vector...")
                    self.estado_tactico = "INICIANDO_DESCUBRIMIENTO"
                    
                # 2. Refresco por deriva: Cada 8 metros el giroscopio acumula cierto error.
                # Obligamos al sistema a repensar su vector.
                if (self.dist_inicial_tramo - self.state["dist"]) > 8.0:
                    log.info("[NAV] 8 metros superados. Refrescando vector...")
                    self.estado_tactico = "INICIANDO_DESCUBRIMIENTO"