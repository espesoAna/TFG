
```markdown
# Software de Control - Waveshare UGV Beast

Este directorio aloja la arquitectura de software desplegada a bordo del vehículo Waveshare UGV Beast. El sistema se ejecuta sobre una Raspberry Pi 4B con **Debian 12 (Bookworm)** (Python 3.11).

## Arquitectura de Hardware y Sensores
El control de hardware de este modelo se abstrae a través de un subcontrolador **ESP32** (comunicación vía bus serie).
* **Telemetría Ambiental:** Sensor digital BMP280 integrado mediante placa auxiliar **Arduino Nano** (Comunicación UART/USB a 115200 bps con el script `codigoArduino.ino`).
* **Percepción Espacial:** Escáner LiDAR 2D D500 (360º de barrido, 5000 Hz, interfaz `/dev/ttyACM1` a 230400 bps).
* **Posicionamiento:** Módulo GNSS Beitian BN-808 (procesado con `gpsd`) apoyado por la Unidad de Medición Inercial (IMU) interna ICM20948 por bus I2C (0x68).
* **Visión:** Cámara USB IMX335 (5 MP, YUY2/MJPG, FOV 160º-175º) sobre mecanismo pan-tilt con servos de bus serie ST3215.

## Estructura de Directorios y Archivos
El código se estructura de manera concurrente mediante hilos independientes que interactúan mediante colas de datos seguras (*thread-safe queues*).

```text
├── logs/                    # Archivos generados de registro y "Caja Negra" (política de rotación).
├── media/                   # Almacenamiento de fotografías y flujo de vídeo capturados a nivel local.
├── modulos/                 # Directorio de los hilos de procesamiento asíncrono:
│   ├── camera_stream.py     # Captura (OpenCV), compresión y emisión de red (FFmpeg UDP Broadcast a 1500k).
│   ├── entorno.py           # Adquisición y procesado de las tramas I2C del sensor BMP280.
│   ├── gps_imu.py           # Extracción y filtrado espacial desde las tramas NMEA (GPSD) y la IMU interna.
│   ├── hardware.py          # Traducción de comandos lógicos superiores a las directivas nativas del ESP32.
│   ├── lidar.py             # Lógica de evasión de colisiones basándose en nubes de puntos 2D (con máscara trasera).
│   ├── logger.py            # Gestor de los registros internos y control de excepciones.
│   ├── math_utils.py        # Módulo de trigonometría esférica (predicción de vectores y zonas prohibidas).
│   ├── navigator.py         # Planificador continuo de rutas hacia waypoints GNSS e integración de polígonos prohibidos.
│   ├── robot_ctrl.py        # Capa de control de estado físico para evitar colisiones lógicas en el hardware.
│   ├── rx_node.py           # Servicio de escucha UDP pasiva y enrutamiento interno de paquetes JSON.
│   ├── telemetria.py        # Extractor de nivel de sistema (Linux) para métricas de CPU, RAM y enlace de radio WiFi.
│   └── tx_node.py           # Inyección de los diccionarios de estado de la red (UDP Broadcast).
├── app_ugv.py               # Script núcleo e inicializador orquestado del sistema.
├── base_ctrl.py             # Módulo proporcionado por Waveshare para la gestión UART del subcontrolador.
├── calibracionBrujula.py    # Utilidad para la calibración del magnetómetro.
├── codigoArduino.ino        # Script de programación en C para la lectura del BMP280 (Arduino Nano).
├── config.py                # Definición centralizada de constantes operativas (parámetros de red y cinemática).
├── config.yaml              # Archivo descriptivo del hardware para el módulo de control base.
├── giro_calibracion.py      # Utilidad para el ajuste de rotación inercial.
├── Documentacion UGV Beast.pdf # Manual de características del chasis o componentes.
├── .gitignore               # Reglas de exclusión de Git.
└── README.md                # Documentación de este directorio.
## Requisitos de Red
El vehículo gestiona la conectividad mediante `Network Manager` (`nmcli`). Requiere una IP estática o resolución DHCP en la subred generada por la estación base. 

## Ejecución
Para arrancar los procesos del vehículo:
```bash
python app_ugv.py