"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres 
MÓDULO: Librería de Geodesia y Navegación Espacial
ARCHIVO: math_util.py
DESCRIPCIÓN: Implementa trigonometría esférica para la resolución de trayectorias, 
             cálculo de distancias y evaluación algorítmica de zonas 
             de exclusión.
"""

import math
import config

def calc_distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia ortodrómica (el camino más corto sobre la superficie de 
    una esfera) entre dos coordenadas GPS utilizando la Fórmula de Haversine.
    
    Ecuación implementada:
    $$a = \sin^2\left(\frac{\Delta\varphi}{2}\right) + \cos(\varphi_1) \cdot \cos(\varphi_2) \cdot \sin^2\left(\frac{\Delta\lambda}{2}\right)$$
    $$c = 2 \cdot \text{atan2}\left(\sqrt{a}, \sqrt{1-a}\right)$$
    $$d = R \cdot c$$
    
    Retorna: Distancia lineal en metros (float).
    """
    # Conversión del sistema sexagesimal (grados) a radianes
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    # Aplicación del teorema del semi-verseno
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    # Multiplicación por el radio volumétrico terrestre extraído de config.py
    return config.RADIO_TIERRA_M * c

def calc_rumbo_deseado(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula el Azimut (Bearing) inicial necesario para ir del punto A al punto B.
    
    Ecuación implementada:
    $$\theta = \text{atan2}\left( \sin(\Delta\lambda) \cdot \cos(\varphi_2), \cos(\varphi_1) \cdot \sin(\varphi_2) - \sin(\varphi_1) \cdot \cos(\varphi_2) \cdot \cos(\Delta\lambda) \right)$$
    
    Retorna: Ángulo en grados respecto al Norte Geográfico [0º - 360º].
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    
    # math.atan2 devuelve valores entre -180 y +180. Se normaliza a la rosa de los vientos (0-360).
    brng = math.degrees(math.atan2(y, x))
    return (brng + 360.0) % 360.0

def punto_en_poligono(lat: float, lon: float, poligono_geojson: list) -> bool:
    """
    Algoritmo de Trazado de Rayos (Ray-Casting Algorithm / Even-Odd Rule).
    Determina si una coordenada GPS se encuentra en el interior de un polígono irregular.
    Se traza un rayo imaginario horizontal desde el punto hacia el infinito y se 
    cuenta cuántas veces cruza los bordes del polígono (Impar = Dentro, Par = Fuera).
    """
    # Aplanamiento de la estructura GeoJSON: Extrae el anillo de coordenadas base
    if len(poligono_geojson) > 0 and isinstance(poligono_geojson[0], list) and isinstance(poligono_geojson[0][0], list):
        anillo = poligono_geojson[0]
    else:
        anillo = poligono_geojson
        
    adentro = False
    j = len(anillo) - 1 # El vértice anterior al primero es el último (cierra el polígono)
    
    for i in range(len(anillo)):
        lon_i, lat_i = anillo[i][0], anillo[i][1]
        lon_j, lat_j = anillo[j][0], anillo[j][1]
        
        # Condición topológica: Verifica si el rayo horizontal intersecta la arista del segmento
        intersecta = ((lat_i > lat) != (lat_j > lat)) and (lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i)
        
        if intersecta:
            adentro = not adentro # Alterna el estado topológico (Inversión booleana)
            
        j = i # Avanza el vértice para el siguiente segmento
        
    return adentro

def evaluar_zona_prohibida(lat: float, lon: float, zonas: list) -> bool:
    """
    Subsistema de Seguridad Táctica (Geofencing).
    Itera sobre la lista de zonas de exclusión (Ej: focos activos de incendio, 
    barrancos) y detiene la evaluación al primer impacto positivo.
    """
    if not zonas: return False
    
    for zona in zonas:
        if punto_en_poligono(lat, lon, zona): 
            return True
            
    return False

def proyectar_punto_gps(lat, lon, rumbo, distancia_m):
    """
    Resuelve el Problema Geodésico Directo.
    Calcula una nueva coordenada GPS de destino proyectando un vector de avance 
    ($d$) con un azimut específico ($\theta$) desde el punto de origen.
    
    Fórmulas base:
    $$\delta = \frac{d}{R}$$
    $$\varphi_2 = \arcsin\left( \sin(\varphi_1) \cdot \cos(\delta) + \cos(\varphi_1) \cdot \sin(\delta) \cdot \cos(\theta) \right)$$
    $$\lambda_2 = \lambda_1 + \text{atan2}\left( \sin(\theta) \cdot \sin(\delta) \cdot \cos(\varphi_1), \cos(\delta) - \sin(\varphi_1) \cdot \sin(\varphi_2) \right)$$
    
    Se utiliza principalmente para evadir obstáculos ciegos o recalcular rutas 
    dinámicas cuando el UGV detecta un muro con el LiDAR.
    """
    dist_rad = distancia_m / config.RADIO_TIERRA_M
    rumbo_rad = math.radians(rumbo)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    new_lat = math.asin(math.sin(lat_rad) * math.cos(dist_rad) +
                        math.cos(lat_rad) * math.sin(dist_rad) * math.cos(rumbo_rad))
                        
    new_lon = lon_rad + math.atan2(math.sin(rumbo_rad) * math.sin(dist_rad) * math.cos(lat_rad),
                                   math.cos(dist_rad) - math.sin(lat_rad) * math.sin(new_lat))
    
    # Reconversión a sistema sexagesimal para su inyección en la IA de navegación
    return math.degrees(new_lat), math.degrees(new_lon)

# Añadir al final de modulos/math_utils.py

def interpolar_tiempo_giro(angulo_grados: float, tabla_tiempos: dict) -> float:
    """
    Interpolación lineal sobre la Look-Up Table (LUT) para calcular el tiempo
    exacto de giro venciendo la no-linealidad de la fricción estática de las orugas.
    """
    angulo_abs = abs(float(angulo_grados))
    
    # Si el ángulo es mayor de 180, girará por el otro lado (que es menor de 180)
    # Esto ya lo maneja el cálculo de err_rumbo, pero lo aseguramos aquí.
    if angulo_abs > 180.0:
        angulo_abs = 360.0 - angulo_abs

    # Ordenar las claves (ángulos calibrados) para la interpolación
    angulos = sorted(list(tabla_tiempos.keys()))
    
    # Si el ángulo coincide exactamente con uno calibrado, o se pasa del máximo
    if angulo_abs in angulos:
        return tabla_tiempos[angulo_abs]
    if angulo_abs > angulos[-1]:
        # Extrapolación simple si se pasa de 180 (no debería ocurrir)
        proporcion = angulo_abs / angulos[-1]
        return tabla_tiempos[angulos[-1]] * proporcion

    # Búsqueda de los dos puntos más cercanos para interpolar
    ang_inferior = 0
    ang_superior = 180
    
    for ang in angulos:
        if ang < angulo_abs:
            ang_inferior = ang
        elif ang > angulo_abs:
            ang_superior = ang
            break
            
    tiempo_inf = tabla_tiempos[ang_inferior]
    tiempo_sup = tabla_tiempos[ang_superior]
    
    # Fórmula de interpolación lineal: y = y1 + (x - x1) * ((y2 - y1) / (x2 - x1))
    proporcion = (angulo_abs - ang_inferior) / (ang_superior - ang_inferior)
    tiempo_calculado = tiempo_inf + (proporcion * (tiempo_sup - tiempo_inf))
    
    return tiempo_calculado