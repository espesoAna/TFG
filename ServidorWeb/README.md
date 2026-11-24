# Estación Base y Servidor Web (ServidorWeb)

Este directorio contiene el código fuente y los recursos de la estación base encargada de la gestión global, monitorización y control manual de la red de Vehículos Terrestres No Tripulados (UGV).

## Arquitectura Lógica
El sistema opera bajo un modelo Cliente-Servidor separando el procesamiento lógico del enrutamiento multimedia:
* **`estacion_tierra.py`**: Núcleo del Backend desarrollado en Python con **Flask**. Intercepta la telemetría UDP de los drones, gestiona el enrutamiento de comandos (Unicast/Broadcast) y levanta conexiones TCP/WebSockets (*Socket.IO*) para sincronizar el Frontend de forma asíncrona.
* **`video_gateway.py`**: Pasarela multimedia independiente (usando `asyncio`). Captura el flujo de vídeo MPEG-TS entrante por el puerto UDP 5000 y lo retransmite al navegador mediante túneles WebSocket puros por el puerto 5001, evitando la saturación del servidor principal.

## Estructura de Directorios y Archivos

```text
├── assets/
│   └── mapas/               # Capas de mapas satelitales (zoom 5 al 18) generadas con MOBAC.
├── css/
│   ├── style_main.css       # Hoja de estilo de la página principal.
│   ├── style_manual.css     # Hoja de estilo del entorno de control manual.
│   └── [Imágenes estáticas]
├── js/
│   ├── script_main.js       # Lógica del panel principal, gestión de estado y mapa interactivo (Leaflet).
│   ├── script_manual.js     # Lógica del control individual y regulación de tasa de eventos táctiles/teclado.
│   └── [Librerías externas] # Archivos descargados para asegurar el funcionamiento offline.
├── media/                   # Almacenamiento local centralizado de las fotografías y vídeos capturados por la flota.
├── estacion_tierra.py       # Script principal de Python que inicializa el servidor web y orquesta la red.
├── estacion_tierra.spec     # Archivo de configuración para compilar la plataforma como ejecutable con PyInstaller.
├── index.html               # Archivo HTML correspondiente a la página principal y visor global.
├── manual.html              # Archivo HTML del panel de control manual (renderizado en un iframe).
├── video_gateway.py         # Pasarela dedicada a capturar vídeo en UDP (puerto 5000) y retransmitirlo por WebSockets.
├── logo.ico                 # Recurso de icono visual.
├── .gitignore               # Reglas de exclusión de Git.
└── README.md                # Documentación de este directorio.

## Requisitos y Configuración de Red
1. El equipo anfitrión debe levantar una red WLAN local (Punto de Acceso) usando herramientas como *MyPublicWiFi*.
2. El servidor web opera por defecto en el puerto **5000**.
3. Se requiere recepción de tráfico UDP habilitada en los puertos **5000** (Vídeo) y **65432** (Telemetría).

## Ejecución
Para iniciar el servidor en modo desarrollo (requiere dependencias de Python instaladas):
```bash
python estacion_tierra.py

Compilación (Ejecutable Portable)

El sistema está diseñado para empaquetarse en un archivo ejecutable único, integrando todos los recursos estáticos mediante PyInstaller y el archivo estacion_tierra.spec. Para compilar, ejecutar en la consola:

python -m PyInstaller --noconfirm --onefile --console --icon="logo.ico" --hidden-import="engineio.async_drivers.threading" --hidden-import="websockets.legacy.server" --add-data "*.html;." --add-data "css;css/" --add-data "js;js/" --add-data "assets;assets/" estacion_tierra.py
