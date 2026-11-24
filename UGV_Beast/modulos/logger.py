"""
PROYECTO: Diseño e Implementación de una Red de Drones Terrestres 
MÓDULO: Subsistema de Trazabilidad y Registro 
ARCHIVO: logger.py
DESCRIPCIÓN: Actúa como la "Caja Negra" del vehículo. Centraliza la salida estándar,
             gestiona la persistencia de los eventos en la tarjeta SD mediante rotación 
             (evitando el desbordamiento de memoria) y captura excepciones no controladas 
             a nivel de intérprete para auditoría forense en caso de caída del sistema.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time


# 1. SUPRESIÓN DE RUIDO Y SINCRONIZACIÓN TEMPORAL (OS-LEVEL)
# Silenciador de la librería subyacente de C++. 
# Al transmitir vídeo por UDP (sin garantía de entrega), es normal recibir 
# fotogramas incompletos. Esto evita que la consola se inunde con falsos errores 
# de decodificación JPEG que colapsarían el buffer de texto de la Raspberry Pi.
os.environ["OPENCV_LOG_LEVEL"] = "SILENT" 

# Fijación estricta de la zona horaria del teatro de operaciones.
# Garantiza que las marcas de tiempo (timestamps) de las evidencias y los logs 
# coincidan con la hora local de la estación de control, independientemente de 
# la configuración regional del sistema operativo de la placa base.
os.environ['TZ'] = 'Europe/Madrid' 
time.tzset()


# 2. CONFIGURACIÓN DEL ÁRBOL DE DIRECTORIOS Y FORMATO
# Resolución dinámica de la ruta del proyecto para importar las constantes globales
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOGS_DIR

# Aseguramiento de la persistencia 
os.makedirs(LOGS_DIR, exist_ok=True)
archivo_log = os.path.join(LOGS_DIR, 'sistema_tactico.log')

# Estructura del datagrama de texto: [Hora] | [Gravedad] | [Mensaje]
formato = '%(asctime)s | [%(levelname)s] | %(message)s'
formato_fecha = '%H:%M:%S'

# Purga de handlers heredados: Evita que librerías de terceros (como Flask o Werkzeug) 
# dupliquen las líneas de log al usar el logger raíz (Root Logger).
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# 3. MOTOR DE TRAZABILIDAD 
logging.basicConfig(
    # Nivel WARNING por defecto en consola: Mantiene la terminal limpia durante 
    # la teleoperación, mostrando únicamente alertas tácticas o fallos de hardware.
    level=logging.WARNING, 
    format=formato,
    datefmt=formato_fecha,
    handlers=[
        # ROTATING FILE HANDLER: Protección contra desbordamiento (OOM/Disk Full).
        # Limita el archivo a 5 MB. Cuando se llena, lo renombra (backup) y crea uno nuevo.
        # Mantiene un máximo de 3 copias históricas (15 MB totales en la SD).
        RotatingFileHandler(archivo_log, maxBytes=5242880, backupCount=3, encoding='utf-8'),
        
        # Multiplexación de la salida: Envía el texto a la consola estándar simultáneamente.
        logging.StreamHandler()
    ]
)

# Instanciación del logger público que será importado por el resto de módulos del UGV
log = logging.getLogger("C3_DRONES")


# 4. SECUESTRO DE EXCEPCIONES GLOBALES 

def handle_exception(exc_type, exc_value, exc_traceback):
    """
    Hook a nivel de sistema. Intercepta cualquier excepción de Python no manejada
    (Crash de aplicación) justo antes de que el proceso muera.
    """
    # Si el operador inyecta un Ctrl+C (Interrupción manual), se permite el apagado
    # ordenado sin registrarlo como una caída catastrófica.
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
        
    # Si el sistema colapsa operando en modo Headless (sin monitor), el volcado 
    # de memoria (Stacktrace) se guarda obligatoriamente en el archivo de texto 
    # para su posterior análisis forense por el ingeniero.
    log.critical("EXCEPCIÓN CRÍTICA DE SISTEMA (CRASH)", exc_info=(exc_type, exc_value, exc_traceback))

# Sobrescritura del manejador por defecto del intérprete de Python
sys.excepthook = handle_exception