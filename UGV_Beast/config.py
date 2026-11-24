"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres.
MÓDULO: Configuración Global
ARCHIVO:config.py
DESCRIPCIÓN: Archivo central de parametrización estática. Contiene las constantes de 
             sintonización para el algoritmo de control proporcional (P), 
             los sesgos de calibración de los sensores inerciales (IMU) y las 
             directivas de red táctica. Evita el uso de "Hardcoded" 
             en el resto de los módulos.
"""


# PARÁMETROS DE NAVEGACIÓN Y CONTROL CINEMÁTICO (LAZO CERRADO)
NAV_PARAMS = {
    # Corrección de polaridad hardware (Inversión de giro de motores o lectura de encoders)
    'INVERTIR_SENSOR': -1,
    
    # Constante Proporcional (Kp) para el control del giro en la evasión de obstáculos.
    # Define la agresividad con la que el UGV corrige su trayectoria ante un muro.
    'KP_GIRO': 0.02,
    
    # Compensación de fricción estática. Fuerza mínima de PWM inyectada 
    # a los motores DC para vencer la inercia física del chasis desde el reposo.
    'FUERZA_MINIMA': 0.05,
    
    # Constante Proporcional (Kp) para el control del rumbo (Heading). 
    # Mantiene al dron alineado con el azimut del Waypoint GPS.
    'KP_RUMBO': 0.015,
    
    # Vectores base de velocidad normalizada (0.0 a 1.0) para avance lineal y rotación.
    'VEL_RECTA': 0.7,
    'VEL_GIRO': 0.35,
    
    # Histéresis angular. Evita la oscilación constante (jittering) de 
    # los motores si el dron está casi alineado con el objetivo (+/- 15 grados).
    'TOLERANCIA_ANGULO': 15,
    
    # Radio de aceptación del Waypoint. Tolerancia de error cinemático y de ruido GPS.
    # Se ajusta a 0.8 metros para escenarios de alta precisión.
    'UMBRAL_LLEGADA': 0.8, #1.5


    # Look-Up Table (LUT) de tiempos de giro empíricos.
    # El robot interpolará matemáticamente cualquier ángulo intermedio usando esta tabla.
    'TIEMPOS_GIRO': {
        0: 0.0,
        30: 0.07,
        45: 0.18,
        90: 0.34,
        180: 0.655
    }
}


# GÉNESIS DEL ESTADO GLOBAL 

# Diccionario semilla que inicializa el estado en memoria RAM del robot antes
# de recibir la primera lectura de los sensores físicos.
INITIAL_STATE = {
    # Posicionamiento GPS y Metas
    "curr_lat": 0.0, "curr_lon": 0.0,
    "target_lat": None, "target_lon": None,
    "heading": 0.0, "active": False, "dist": 0.0,
    "fix": False, "sats": 0, "port": "GPSD Local",
    
    # Calibración del Giroscopio (GZ): Corrección de deriva (Drift) en reposo.
    "bias_gz": 0.0, "current_gz": 0.0,
    
    # Calibración Hard-Iron del Magnetómetro (MX, MY). 
    # Compensación estática de las interferencias magnéticas generadas por el propio
    # chasis metálico del UGV y los campos electromagnéticos de sus motores DC.
    "bias_mx": -93.13,  
    "bias_my": -9.39,
    
    # Estado de hardware informático y enlaces
    "telemetry": {'cpu': 0, 'ram': 0, 'temp': 0, 'wifi': 0},
    
    # Estado de actuadores periféricos
    "lights": False,
    "pan": 0, "tilt": 0,
    "speed": 0.7,
    "zoom_level": 1.0,
    "camera_active": False
}


# CONSTANTES FÍSICAS, MATEMÁTICAS Y DE COMUNICACIÓN

# Constante trigonométrica esencial para la Ecuación de Haversine.
# Modela la Tierra como una esfera para calcular la distancia 
# (línea recta sobre la superficie curva) entre dos coordenadas GPS.
RADIO_TIERRA_M = 6371000.0  

# Capa de Transporte - Puerto de escucha para la malla Ad-Hoc.
# Se utiliza el puerto alto 65432 para evitar colisiones 
# con servicios nativos del sistema operativo Linux.
PUERTO_COMANDOS = 65432     

# Identificador único del nodo dentro del enjambre.
# Utilizado por la Capa de Aplicación para filtrar el tráfico UDP Broadcast.
ROBOT_ID = "beast"


# ESTRUCTURA DE ARCHIVOS Y RUTAS
# Directorio local de persistencia de datos. 
# Almacena registros de eventos, volcados de errores y trazas de telemetría.
LOGS_DIR = "logs"