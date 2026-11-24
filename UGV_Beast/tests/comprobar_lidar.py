import time
from modulos.lidar import ModuloLidar

lidar = ModuloLidar({}, None)
lidar.iniciar_hilo()

try:
    while True:
        puntos = lidar.get_last_scan()
        if puntos:
            distancias = [distancia for distancia, angulo in puntos]
            print(
                f"{len(puntos)} puntos; "
                f"distancia: {min(distancias)}–{max(distancias)} mm; "
                f"ejemplos: {puntos[:5]}",
                flush=True,
            )
        else:
            print("Esperando el primer barrido...", flush=True)
        time.sleep(1)
except KeyboardInterrupt:
    print("Prueba detenida.")