#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>

// Crear el objeto del sensor por I2C
Adafruit_BMP280 bmp;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  // Inicializar. La dirección 0x76 es la estándar para módulos de 4 pines.
  // Si te da error, cambia el 0x76 por 0x77.
  if (!bmp.begin(0x76)) {
    Serial.println("Error: No se encuentra el sensor BMP280. Revisa los cables.");
    while (1);
  }

  // --- CONFIGURACIÓN AVANZADA PARA DRONES ---
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,     
                  Adafruit_BMP280::SAMPLING_X16,    // Sobremuestreo Temp
                  Adafruit_BMP280::SAMPLING_X16,    // Sobremuestreo Presión
                  Adafruit_BMP280::FILTER_X16,      // Filtro contra viento
                  Adafruit_BMP280::STANDBY_MS_500); 
}

void loop() {
  float temperatura = bmp.readTemperature();
  float presion = bmp.readPressure() / 100.0F;
  

  // Enviar formato a la Raspberry: T:25.10,P:980.15
  Serial.print("T:");
  Serial.print(temperatura, 2);
  Serial.print(",P:");
  Serial.print(presion, 2);
  Serial.println(); 

  delay(1000); 
}