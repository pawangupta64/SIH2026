#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// =====================================================
// WIFI SETTINGS
// =====================================================

const char* WIFI_SSID = "realme P4 5G a5k4";
const char* WIFI_PASSWORD = "mynw2399";

// =====================================================
// KISANMITRA FLASK SERVER
// =====================================================
//
// IMPORTANT:
// Replace YOUR_PC_IP with your computer's IPv4 address.
//
// Example:
// http://10.187.43.5:5000/api/ingest
//

const char* SERVER_URL =
  "http://10.187.43.205:5000/api/ingest";

// =====================================================
// KISANMITRA USER / DEVICE
// =====================================================

const char* USER_EMAIL =
  "ray.suraj2006@gmail.com";

const char* DEVICE_API_KEY =
  "kisanmitra-device-key";

const char* DEVICE_ID =
  "esp32-1";

// =====================================================
// SENSOR PINS
// =====================================================

// DS18B20 DATA -> GPIO 4
#define ONE_WIRE_BUS 4

// Capacitive Soil Moisture Sensor AO -> GPIO 32
#define SOIL_MOISTURE_PIN 32

// =====================================================
// DS18B20
// =====================================================

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// =====================================================
// SEND INTERVAL
// =====================================================

unsigned long lastSendTime = 0;

const unsigned long SEND_INTERVAL = 5000;


// =====================================================
// CONNECT TO WIFI
// =====================================================

void connectWiFi()
{
  Serial.println();
  Serial.println("================================");
  Serial.println("Connecting to Wi-Fi...");
  Serial.println("================================");

  WiFi.mode(WIFI_STA);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 40)
  {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("Wi-Fi connected!");

    Serial.print("ESP32 IP address: ");
    Serial.println(WiFi.localIP());

    Serial.print("Signal strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  }
  else
  {
    Serial.println("Wi-Fi connection FAILED!");
  }
}


// =====================================================
// SEND SENSOR DATA
// =====================================================

void sendSensorData()
{
  // ---------------------------------------------------
  // CHECK WIFI
  // ---------------------------------------------------

  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("Wi-Fi disconnected.");
    Serial.println("Trying to reconnect...");

    connectWiFi();

    if (WiFi.status() != WL_CONNECTED)
    {
      Serial.println("Could not reconnect to Wi-Fi.");
      return;
    }
  }


  // ---------------------------------------------------
  // READ DS18B20 TEMPERATURE
  // ---------------------------------------------------

  sensors.requestTemperatures();

  float temperatureC =
    sensors.getTempCByIndex(0);

  if (temperatureC == DEVICE_DISCONNECTED_C)
  {
    Serial.println();
    Serial.println("ERROR: Could not read DS18B20!");
    return;
  }


  // ---------------------------------------------------
  // READ SOIL MOISTURE
  // ---------------------------------------------------

  int soilRaw =
    analogRead(SOIL_MOISTURE_PIN);


  // ---------------------------------------------------
  // CONVERT SOIL RAW VALUE TO PERCENTAGE
  // ---------------------------------------------------

  int moisturePercent =
    map(soilRaw, 4095, 0, 0, 100);

  moisturePercent =
    constrain(moisturePercent, 0, 100);


  // ---------------------------------------------------
  // SERIAL MONITOR
  // ---------------------------------------------------

  Serial.println();
  Serial.println("================================");
  Serial.println("SENSOR DATA");
  Serial.println("================================");

  Serial.print("Temperature: ");
  Serial.print(temperatureC);
  Serial.println(" C");

  Serial.print("Soil Raw: ");
  Serial.println(soilRaw);

  Serial.print("Soil Moisture: ");
  Serial.print(moisturePercent);
  Serial.println(" %");


  // ---------------------------------------------------
  // CREATE JSON DATA
  // ---------------------------------------------------

  StaticJsonDocument<256> json;

  json["email"] = USER_EMAIL;
  json["temperature"] = temperatureC;
  json["soil_moisture"] = moisturePercent;
  json["device_id"] = DEVICE_ID;

  String jsonData;

  serializeJson(json, jsonData);


  // ---------------------------------------------------
  // SEND DATA TO FLASK
  // ---------------------------------------------------

  Serial.println();
  Serial.println("Sending data to KisanMitra...");

  HTTPClient http;

  http.begin(SERVER_URL);

  http.addHeader(
    "Content-Type",
    "application/json"
  );

  http.addHeader(
    "X-Device-Key",
    DEVICE_API_KEY
  );


  int httpResponseCode =
    http.POST(jsonData);


  // ---------------------------------------------------
  // SERVER RESPONSE
  // ---------------------------------------------------

  Serial.print("HTTP Response: ");
  Serial.println(httpResponseCode);

  if (httpResponseCode > 0)
  {
    String response =
      http.getString();

    Serial.print("Server response: ");
    Serial.println(response);
  }
  else
  {
    Serial.print("HTTP Error: ");
    Serial.println(
      http.errorToString(httpResponseCode)
    );
  }

  http.end();

  Serial.println("================================");
}


// =====================================================
// SETUP
// =====================================================

void setup()
{
  Serial.begin(115200);

  delay(2000);

  Serial.println();
  Serial.println("================================");
  Serial.println("KISANMITRA AI SENSOR SYSTEM");
  Serial.println("================================");


  // ---------------------------------------------------
  // START DS18B20
  // ---------------------------------------------------

  sensors.begin();

  Serial.println(
    "DS18B20 temperature sensor started"
  );


  // ---------------------------------------------------
  // START SOIL SENSOR
  // ---------------------------------------------------

  pinMode(
    SOIL_MOISTURE_PIN,
    INPUT
  );

  Serial.println(
    "Soil moisture sensor started"
  );


  // ---------------------------------------------------
  // CONNECT WIFI
  // ---------------------------------------------------

  connectWiFi();


  // ---------------------------------------------------
  // READY
  // ---------------------------------------------------

  Serial.println();
  Serial.println("System ready.");
  Serial.println();
}


// =====================================================
// LOOP
// =====================================================

void loop()
{
  unsigned long now = millis();

  if (
    now - lastSendTime >= SEND_INTERVAL
  )
  {
    lastSendTime = now;

    sendSensorData();
  }
}