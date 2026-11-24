"""
Codigo:calibracionBrujula.py
DESCRIPCIÓN: Script de servicio independiente (Standalone). 
             Calcula el sesgo magnético (Bias) del chasis induciendo un giro autónomo. 
             Es imperativo realizar esta calibración con los motores DC encendidos, 
             ya que las bobinas generan interferencia electromagnética (EMI) estática 
             que deforma la lectura del campo magnético terrestre local.
"""

import time
import json
from base_ctrl import BaseController

# =============================================================================
# 1. INICIALIZACIÓN Y CONFIGURACIÓN DEL BUS SERIE
# =============================================================================
try:
    # Conexión UART directa con la controladora de bajo nivel (ESP32/Arduino)
    base = BaseController('/dev/serial0', 115200)
    
    # Inyección de comandos nativos de hardware para configurar la IMU interna
    base.send_command({"T": 143, "cmd": 0})  # Despierta el sensor
    base.send_command({"T": 131, "cmd": 1})  # Habilita lectura continua
    base.send_command({"T": 142, "cmd": 50}) # Configura la tasa de refresco a 20 Hz
    
    # Limpieza del buffer de entrada para descartar lecturas corruptas residuales
    base.ser.reset_input_buffer()
except Exception as e:
    print(f"Error crítico de enlace UART: {e}")
    exit()

print("\nINICIANDO AUTO-CALIBRADOR DINÁMICO (Efecto Hard-Iron)")
print("El robot va a girar sobre sí mismo usando sus propios motores.")
print("Esto captura la interferencia electromagnética real generada por el chasis.")
print("¡Apártate! Arrancando en 3 segundos...\n")

time.sleep(3)

# =============================================================================
# 2. PARÁMETROS DEL ENSAYO FÍSICO
# =============================================================================
VELOCIDAD_GIRO = 0.35 # PWM normalizado. Suficiente para vencer la fricción sin derrapar.

# Inicialización de las variables de frontera. Se buscan los extremos del 
# círculo magnético desplazado (Deformación geométrica del campo).
max_x, min_x = -99999.0, 99999.0
max_y, min_y = -99999.0, 99999.0

# Duración del ensayo (15 segundos garantizan varias rotaciones completas de 360º)
t_end = time.time() + 15.0
last_motor_update = 0

# =============================================================================
# 3. BUCLE DE MUESTREO (SAMPLING LOOP)
# =============================================================================
while time.time() < t_end:
    
    # ANTI-WATCHDOG Y MANTENIMIENTO CINEMÁTICO
    # Los microcontroladores robóticos tienen un "Failsafe" que apaga los motores 
    # si no reciben comandos frescos. Refrescamos el comando de giro a 2 Hz.
    if time.time() - last_motor_update > 0.5:
        try:
            base.base_speed_ctrl(VELOCIDAD_GIRO, -VELOCIDAD_GIRO)
            last_motor_update = time.time()
        except Exception:
            pass

    # CONTROL DE LATENCIA (Flushing)
    # Si la lectura serial se retrasa, leemos datos antiguos. Vaciamos el buffer
    # si se acumulan más de 100 bytes para asegurar lecturas en tiempo real.
    if base.ser.in_waiting > 100:
        base.ser.reset_input_buffer()
        base.ser.readline() # Descartamos la línea truncada fruto del corte
        
    try:
        # Decodificación blindada frente a caracteres corruptos en el enlace serie
        line = base.ser.readline().decode('utf-8', errors='ignore').strip()
        
        # Filtramos exclusivamente los datagramas que contienen vectores magnéticos
        if 'mx' in line and 'my' in line:
            data = json.loads(line)
            mx, my = data['mx'], data['my']
            
            # --- ALGORITMO MIN-MAX ---
            # Registramos los picos máximos y mínimos de la señal en ambos ejes 
            # durante la rotación completa.
            if mx > max_x: max_x = mx
            if mx < min_x: min_x = mx
            if my > max_y: max_y = my
            if my < min_y: min_y = my
            
            print(f"Mapeando ruido... X: {mx:>6.1f} | Y: {my:>6.1f}    ", end='\r')
    except Exception:
        # Los errores de parseo JSON transitorios se ignoran para no interrumpir el ensayo
        pass

# =============================================================================
# 4. PROTOCOLO DE PARADA SEGURA
# =============================================================================
# Redundancia de apagado: Se envía el comando de freno 3 veces consecutivas 
# para garantizar que el robot no se quede girando infinitamente si se pierde un paquete.
for _ in range(3):
    try:
        base.base_speed_ctrl(0, 0)
        time.sleep(0.1)
    except Exception:
        pass

# =============================================================================
# 5. CÁLCULO ANALÍTICO DEL SESGO (BIAS CALCULATION)
# =============================================================================
# Matemáticamente, el centro del círculo de mediciones magnéticas debería ser (0,0).
# La interferencia Hard-Iron desplaza todo el círculo. Calculamos el centro de 
# ese círculo deformado para obtener el vector de corrección exacto.
offset_x = (max_x + min_x) / 2.0
offset_y = (max_y + min_y) / 2.0

print("\n\n¡CALIBRACIÓN ACTIVA COMPLETADA!")
print("Apunta estos nuevos números blindados y actualiza tu config.py:")
print("--------------------------------------------------")
print(f"self.state['bias_mx'] = {offset_x:.2f}")
print(f"self.state['bias_my'] = {offset_y:.2f}")
print("--------------------------------------------------")