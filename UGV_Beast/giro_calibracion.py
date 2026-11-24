"""
=============================================================================
Script: giro_calibracion.py
Descripción: Herramienta de calibración cinemática para el robot UGV Beast.
Propósito: Permite ejecutar giros sobre su propio eje (pivote) durante un 
           tiempo exacto para medir físicamente cuántos grados gira el chasis.
           Los resultados de esta prueba alimentarán las constantes de 
           navegación autónoma (ej. TIEMPO_GIRO_90) en el sistema principal.
=============================================================================
"""

import time
import sys
# Importamos la capa de abstracción de hardware (HAL) que se comunica con el ESP32
from base_ctrl import BaseController

# --- PARÁMETROS DE CALIBRACIÓN ---
# Velocidad de giro en m/s (o porcentaje PWM según el firmware del sub-controlador).
# Debe coincidir EXACTAMENTE con la velocidad que usará el robot en modo autónomo 
# para que los tiempos calibrados sean válidos.
VEL_GIRO = 0.55

def main():
    print("========================================")
    print("    CALIBRADOR DE GIROS - UGV BEAST     ")
    print("========================================")
    print("Instrucciones: Marca el frente del robot en el suelo con cinta.")
    print("Introduce el tiempo en segundos para probar cuánto gira.")
    print("Escribe 'q' para salir.")
    
    try:
        # Inicializamos la conexión Serial (UART) entre la Raspberry Pi 4 (Cerebro) 
        # y el ESP32 (Sub-controlador de motores). 
        # '/dev/serial0' a 115200 baudios es el estándar físico en la placa Waveshare.
        base = BaseController('/dev/serial0', 115200)
        
        # Pausa de seguridad para permitir que el ESP32 resetee e inicialice 
        # sus puertos I2C internos y los drivers del motor tras abrir el puerto Serie.
        time.sleep(2) 
    except Exception as e:
        print(f"[ERROR CRÍTICO] Fallo conectando al hardware base: {e}")
        sys.exit(1)

    # Bucle infinito para realizar múltiples pruebas de ensayo y error
    while True:
        try:
            # Capturamos el input del usuario bloqueando el hilo principal
            entrada = input("\nIntroduce tiempo en segundos (ej: 0.85) o 'q' para salir: ")
            
            # Condición de salida limpia
            if entrada.lower() == 'q':
                break
                
            # Convertimos el string a decimal (float)
            tiempo = float(entrada)
            
            print(f"-> Ejecutando maniobra: Velocidad={VEL_GIRO} | Duración={tiempo}s...")
            
            # --- COMANDO DE MOVIMIENTO (GIRO SOBRE SU EJE) ---
            # Diccionario JSON compatible con el protocolo del ESP32 de Waveshare:
            # "T": 1 -> Modo de Control de Velocidad Lineal (CMD_SPEED_CTRL).
            # "L": Positivo -> Oruga izquierda avanza hacia adelante.
            # "R": Negativo -> Oruga derecha retrocede.
            # Resultado: El robot gira sobre su centro geométrico hacia la DERECHA.
            cmd = {"T": 1, "L": VEL_GIRO, "R": -VEL_GIRO}
            base.send_command(cmd)
            
            # Mantenemos el hilo de Python suspendido mientras los motores del ESP32
            # ejecutan el giro en la vida real.
            time.sleep(tiempo)
            
            # --- COMANDO DE FRENADO DE EMERGENCIA (KILL-SWITCH) ---
            # Mandamos un 0.0 absoluto a ambas orugas para evitar derivas o "fantasmas"
            # en el buffer del puerto serie.
            stop_cmd = {"T": 1, "L": 0.0, "R": 0.0}
            base.send_command(stop_cmd)
            
            print("-> Freno aplicado. Mide el ángulo real con un transportador o móvil.")
            
        except ValueError:
            # Captura el error si el usuario introduce letras en lugar de números
            print("[ADVERTENCIA] Por favor, introduce un número decimal válido.")
        except KeyboardInterrupt:
            # Permite salir elegantemente si el usuario pulsa Ctrl+C en medio de una prueba
            print("\n[SISTEMA] Interrupción manual detectada (Ctrl+C).")
            break

    # Rutina de limpieza y seguridad antes de destruir el proceso
    print("\nCerrando calibrador y asegurando motores...")
    
    # Doble confirmación de frenado para evitar que el robot se quede en marcha
    # si el programa se cierra abruptamente.
    stop_cmd = {"T": 1, "L": 0.0, "R": 0.0}
    base.send_command(stop_cmd)

# Punto de entrada estándar en Python
if __name__ == "__main__":
    main()