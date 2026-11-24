"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres
MÓDULO: Abstracción de Comandos de Hardware (Beast)
ARCHIVO: hardware.py
DESCRIPCIÓN: Interfaz que traduce las órdenes del nivel superior (lógico) a las
             tramas de comando específicas que requiere el firmware nativo del 
             chasis UGV Beast. Gestiona la rutina de arranque y la cinemática PTZ.
"""

import time

class ModuloHardware:
    def __init__(self, state_dict, base_controller):
        self.state = state_dict
        self.base = base_controller

    def init_beast(self):
        """
        Secuencia de inicialización (Handshake) con el sub-controlador ESP32.
        Envía un bloque de tramas para configurar los parámetros de 
        comunicación interna y calibración del chasis por defecto.
        """
        print("Configurando sub-controlador...")
        time.sleep(1.5)
        # Vector de comandos de configuración extraídos de la API del fabricante
        boot_commands = [
            {"T": 900, "main": 3, "module": 2}, 
            {"T": 143, "cmd": 0},
            {"T": 131, "cmd": 1},
            {"T": 142, "cmd": 50},
            {"T": 136, "cmd": 2000},
            {"T": 138, "L": 1.0, "R": 0.805} # Calibración diferencial de motores
        ]
        
        if self.base:
            for cmd in boot_commands:
                self.base.send_command(cmd)
                time.sleep(0.1)
            # Limpieza del canal de comunicación para evitar lectura de acuses de recibo obsoletos
            self.base.ser.reset_input_buffer()

    def move_gimbal(self, pan, tilt):
        """Traduce las coordenadas absolutas de la interfaz web a rangos de hardware."""
        # Almacenamiento del estado para exposición a través de la API REST
        self.state['pan'], self.state['tilt'] = pan, tilt
        
        # TRADUCTOR: Interfaz Web (0 a 180, centro 90) -> ESP32 Beast (-90 a 90, centro 0)
        pan_beast = int(pan) - 90
        tilt_beast = int(tilt) - 90
        
        if self.base: 
            self.base.gimbal_ctrl(pan_beast, tilt_beast, 0, 0)
            
    def toggle_lights(self):
        """Conmutador de iluminación de apoyo."""
        self.state['lights'] = not self.state.get('lights', False)
        if self.base:
            pwm = 255 if self.state['lights'] else 0
            self.base.lights_ctrl(pwm, pwm)
            
    def set_speed(self, val):
        """Modificador incremental de la velocidad máxima acotado entre el 20% y el 100%."""
        s = self.state.get('speed', 0.7)
        s = min(1.0, round(s + 0.1, 1)) if val == 'up' else max(0.2, round(s - 0.1, 1))
        self.state['speed'] = s
        
    def set_zoom(self, val):
        """Gestor de ampliación óptica digital."""
        z = self.state.get('zoom_level', 1.0)
        z = min(4.0, z + 0.5) if val == 'in' else max(1.0, z - 0.5)
        self.state['zoom_level'] = z