# Diseño e Implementación de una Red de Drones Terrestres

## Descripción del Proyecto
Este repositorio aloja el código fuente y la documentación correspondientes al Trabajo Fin de Grado del Grado en Ingeniería de Tecnologías Específicas de Telecomunicación de la Universidad de Valladolid. 

El proyecto documenta el diseño, desarrollo e implementación de una arquitectura tecnológica y de comunicaciones inalámbricas para el despliegue de Vehículos Terrestres No Tripulados (UGV) de bajo coste. El sistema está concebido para la exploración, monitorización y perimetraje en entornos rurales aislados o en situaciones de emergencia, pudiendo operar de manera totalmente autónoma en una red de área local (WLAN) sin necesidad de infraestructura comercial de Internet.

## Características Principales
* **Operación Aislada y Cartografía Local:** Uso de la herramienta *Mobile Atlas Creator (MOBAC)* para empaquetar mapas satelitales (*tiles* de la capa 5 a la 18) y operarlos en entornos sin cobertura de red externa.
* **Navegación Autónoma y Evasión de Obstáculos:** Seguimiento de rutas mediante coordenadas GPS esquivando de forma dinámica zonas prohibidas designadas por el usuario y obstáculos físicos detectados por LiDAR/Ultrasonidos.
* **Sistema Híbrido de Control:** Capacidad de interrumpir rutinas autónomas para asumir el control manual directo desde la estación base con baja latencia.
* **Telemetría en Tiempo Real:** Monitorización de temperatura, presión atmosférica, posicionamiento GNSS, número de satélites, estado del enlace WiFi, uso de CPU y RAM.
* **Transmisión de Vídeo de Baja Latencia:** Captura y compresión mediante OpenCV y FFmpeg (MPEG-1 sobre UDP a 1500 kbps) y visualización en un HUD central a través de WebSockets sin bloqueos de red.
* **Tolerancia a Fallos:** Arquitectura distribuida en hilos, aislamiento del tráfico multimedia y alertas automáticas de seguridad si la degradación de la señal WiFi cae por debajo del 45%.

## Arquitectura de Hardware
El enjambre está compuesto por dos vehículos comerciales modificados y dotados de microcontroladores auxiliares:

### 1. Vehículo Yahboom G1 Tank (Tracción por orugas)
* **Unidad de procesamiento principal:** Raspberry Pi 4B (8 GB RAM) sobre Raspbian 10.
* **Tracción:** Motores DC con reductora 25GA-370.
* **Navegación y Percepción:** Sensor de posicionamiento GNSS Beitian BN-808, Sensor de ultrasonidos HC-SR04 montado sobre servomotor SG90.
* **Sistema de Visión:** Cámara USB de 1 Megapíxel montada sobre mecanismo articulado *pan-tilt*.

### 2. Vehículo Waveshare UGV Beast (Tracción con suspensión independiente)
* **Unidades de procesamiento:** Raspberry Pi 4B (8 GB RAM) sobre Debian 12, respaldada por un subcontrolador ESP32 para el control a bajo nivel.
* **Tracción:** Motores DC con encoder DCGM-3865.
* **Navegación y Percepción:** Sensor de posicionamiento GNSS Beitian BN-808, Escáner LiDAR 2D D500 (360º de barrido) e IMU ICM20948 (9 ejes).
* **Sistema de Visión:** Cámara USB IMX335 de 5 Megapíxeles sobre mecanismo *pan-tilt* (Servos de bus serie ST3215).
* **Alimentación:** Módulo UPS 3S con telemetría INA219.

### Subsistema Auxiliar (Común en ambos drones)
Ambos vehículos integran una placa **Arduino Nano** configurada mediante bus SPI para gestionar en exclusiva la lectura de un sensor **BMP280**, delegando la medición térmica y barométrica fuera del procesador principal.

## Arquitectura de Comunicaciones
* **Topología:** Red en estrella gobernada por un Punto de Acceso (AP) montado en el equipo portátil de la estación base (ej. usando MyPublicWiFi).
* **Enlace de Datos Táctico:** Transporte basado íntegramente en datagramas **UDP** (puerto 65432). Los vehículos emiten telemetría mediante difusión (*Broadcast*), mientras que la estación base enruta comandos directamente a cada IP física (*Unicast*).
* **Pasarela de Servidor (Estación Base):** El *Backend* de la estación (Flask) convierte el tráfico UDP en conexiones persistentes **TCP** y **WebSockets** para alimentar el *Frontend* de forma asíncrona, evitando el bloqueo del navegador.

## Estructura del Repositorio
El repositorio cuenta con una estructura dividida entre el servidor y los dos clientes móviles:

```text
├── Esquema de carpetas.txt
├── .gitignore
├── README.md
│
├── ServidorWeb/
│   ├── assets/               # Capas cartográficas generadas con MOBAC.
│   ├── css/                  # Hojas de estilo y recursos visuales.
│   ├── js/                   # Scripts de la interfaz web (Leaflet, WebSockets).
│   ├── media/                # Almacenamiento base de fotos y vídeos capturados.
│   ├── estacion_tierra.py    # Script principal del backend (Flask).
│   ├── estacion_tierra.spec  # Configuración para compilación PyInstaller.
│   ├── video_gateway.py      # Pasarela asíncrona dedicada al flujo de vídeo (asyncio).
│   ├── index.html            # Panel principal de gestión global.
│   ├── manual.html           # Panel de control individual integrado en iframe.
│   ├── logo.ico
│   ├── .gitignore
│   └── README.md
│
├── Yahboom_Tank_G1/
│   ├── app_y.py              # Punto de entrada y orquestador del G1 Tank.
│   ├── build.py              # Capa física para pines GPIO.
│   ├── config.py             # Constantes cinemáticas y parámetros fijos.
│   ├── codigoArduino.ino     # Firmware para la placa Arduino Nano (BMP280).
│   ├── Documentacion G1 Tank Yahbooml.pdf
│   ├── logs/                 # Consola de depuración y registro rotativo.
│   ├── media/                # Almacenamiento multimedia local del vehículo.
│   ├── modulos/
│   │   ├── camera_stream.py  # Procesado OpenCV y transmisión FFmpeg MPEG-TS.
│   │   ├── env_sensor.py     # Hilo colector de variables ambientales vía UART/USB.
│   │   ├── evasion_system.py # Lógica reactiva ante el barrido de ultrasonidos.
│   │   ├── gps_reader.py     # Hilo capturador del demonio GPSD (Tramas NMEA).
│   │   ├── manual_control.py # Traducción de eventos teclado a control de motores.
│   │   ├── math_utils.py     # Algoritmos trigonométricos espaciales.
│   │   ├── navigator.py      # Planificador de trayectorias GNSS predictivo.
│   │   ├── robot_ctrl.py     # Abstracción de estado con colas seguras (thread-safe).
│   │   ├── rx_node.py        # Hilo receptor UDP de comandos (JSON).
│   │   ├── tx_node.py        # Hilo transmisor UDP de telemetría (Broadcast).
│   │   └── logger.py         # Gestor de registros y caja negra.
│   ├── .gitignore
│   └── README.md
│
└── UGV_Beast/
    ├── app_ugv.py            # Punto de entrada y orquestador del UGV Beast.
    ├── base_ctrl.py          # Controlador nativo para el ESP32 interno.
    ├── config.py             # Parámetros estáticos de configuración.
    ├── config.yaml           # Archivo de perfiles de hardware (Fabricante).
    ├── calibracionBrujula.py # Script de calibración magnética.
    ├── giro_calibracion.py   # Script de calibración de rotación.
    ├── codigoArduino.ino     # Firmware para la placa Arduino Nano (BMP280).
    ├── Documentacion UGV Beast.pdf
    ├── logs/
    ├── media/
    ├── modulos/
    │   ├── camera_stream.py  
    │   ├── entorno.py        # Lógica de adquisición ambiental.
    │   ├── lidar.py          # Máquina de estados para control evasivo basado en nube de puntos.
    │   ├── gps_imu.py        # Procesamiento combinado NMEA e IMU.
    │   ├── hardware.py       # Traducción de comandos de alto nivel al bus ESP32.
    │   ├── math_utils.py     
    │   ├── navigator.py      
    │   ├── robot_ctrl.py     
    │   ├── rx_node.py        
    │   ├── tx_node.py        
    │   ├── telemetria.py     # Monitor de sistema (CPU, RAM, RSSI WiFi).
    │   └── logger.py         
    ├── .gitignore
    └── README.md