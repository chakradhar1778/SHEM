
/*
  ============================================================
  SHEM - SMART HOME ENERGY MANAGEMENT SYSTEM
  ESP32 + PZEM-004T + RELAY + LCD + EMQX MQTT Cloud
  ============================================================

  HARDWARE:
  ESP32 DevKit
  PZEM-004T
  16x2 I2C LCD
  1-channel relay module

  CONNECTIONS:
  PZEM RX -> ESP32 GPIO16
  PZEM TX -> ESP32 GPIO17

  LCD SDA -> GPIO21
  LCD SCL -> GPIO22

  Relay IN -> GPIO23

  MQTT FLOW:
  ESP32 -> EMQX -> FastAPI
  FastAPI -> EMQX -> ESP32

  IMPORTANT:
  Relay is configured ACTIVE LOW.
  Verify this against your actual relay module.
*/

// ============================================================
// LIBRARIES
// ============================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <PZEM004Tv30.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <time.h>
#include <math.h>


// ============================================================
// 1. WIFI + MQTT CREDENTIALS
// ============================================================
// WIFI_SSID, WIFI_PASSWORD, MQTT_USERNAME and MQTT_PASSWORD live in
// secrets.h (git-ignored). Copy secrets.example.h to secrets.h and fill it in.

#include "secrets.h"


// ============================================================
// 2. EMQX CLOUD CONFIGURATION
// ============================================================

// Enter the EMQX Cloud cluster hostname.
// EMQX deployment hostname (without https://)

const char* MQTT_HOST = "xf061010.ala.asia-southeast1.emqxsl.com";
const int MQTT_PORT = 8883;
// MQTT_USERNAME / MQTT_PASSWORD come from secrets.h

const char* DEVICE_ID = "001";


// Paste the trusted root CA certificate for your
// EMQX Cloud TLS certificate chain here.
//
// Do not use a certificate copied from an untrusted source.
// Do not leave this empty for the secure configuration.

static const char MQTT_ROOT_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----
)EOF";


// ============================================================
// 3. HARDWARE CONFIGURATION
// ============================================================

#define PZEM_RX 16
#define PZEM_TX 17

#define LCD_SDA 21
#define LCD_SCL 22

#define RELAY_PIN 23

// Confirm this with your relay module.
// ACTIVE LOW: LOW = ON, HIGH = OFF.

#define RELAY_ON LOW
#define RELAY_OFF HIGH


// ============================================================
// 4. MQTT TOPICS
// ============================================================

String TOPIC_TELEMETRY;
String TOPIC_STATUS;
String TOPIC_RELAY_COMMAND;
String TOPIC_RELAY_STATE;
String TOPIC_RELAY_ACK;


// ============================================================
// 5. OBJECTS
// ============================================================

PZEM004Tv30 pzem(Serial2, PZEM_RX, PZEM_TX);

LiquidCrystal_I2C lcd(0x27, 16, 2);

WiFiClientSecure secureClient;
PubSubClient mqtt(secureClient);


// ============================================================
// 6. TIMING
// ============================================================

const unsigned long TELEMETRY_INTERVAL = 2000;
const unsigned long LCD_INTERVAL = 2500;
const unsigned long WIFI_RETRY_INTERVAL = 20000;
const unsigned long MQTT_RETRY_INTERVAL = 5000;

unsigned long lastTelemetryTime = 0;
unsigned long lastLCDTime = 0;
unsigned long lastWiFiAttempt = 0;
unsigned long lastMQTTAttempt = 0;


// ============================================================
// 7. DEVICE STATE
// ============================================================

bool relayState = false;

float voltage = NAN;
float current = NAN;
float power = NAN;
float energy = NAN;
float frequency = NAN;
float powerFactor = NAN;

bool meterReadingsValid = false;

String lastCommandId = "";

int lcdPage = 0;


// ============================================================
// 8. RELAY CONTROL
// ============================================================

void setRelay(bool state) {

  relayState = state;

  digitalWrite(
    RELAY_PIN,
    relayState ? RELAY_ON : RELAY_OFF
  );

  Serial.print("Relay 1: ");
  Serial.println(relayState ? "ON" : "OFF");
}


// ============================================================
// 9. TIME CONFIGURATION
// ============================================================

bool isTimeSynchronized() {

  return time(nullptr) > 1700000000;
}


String getTimestamp() {

  time_t now = time(nullptr);

  if (!isTimeSynchronized()) {
    return "";
  }

  struct tm timeinfo;

  gmtime_r(&now, &timeinfo);

  char buffer[30];

  strftime(
    buffer,
    sizeof(buffer),
    "%Y-%m-%dT%H:%M:%SZ",
    &timeinfo
  );

  return String(buffer);
}


// ============================================================
// 10. WIFI CONNECTION
// ============================================================

void connectWiFi() {

  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();

  if (now - lastWiFiAttempt < WIFI_RETRY_INTERVAL) {
    return;
  }

  lastWiFiAttempt = now;

  Serial.println();
  Serial.println("Connecting to WiFi...");

  // Fully reset any half-finished attempt before restarting, so
  // WiFi.begin() does not collide with the auto-reconnect logic
  // (this collision starves IDLE0 and trips the task watchdog).
  WiFi.disconnect(false, false);
  delay(100);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}


// ============================================================
// 11. MQTT STATUS
// ============================================================

void publishDeviceStatus(const char* status) {

  if (!mqtt.connected()) {
    return;
  }

  StaticJsonDocument<256> doc;

  doc["deviceId"] = DEVICE_ID;
  doc["status"] = status;
  doc["relay1State"] = relayState ? "ON" : "OFF";
  doc["timestamp"] = getTimestamp();

  char payload[256];

  size_t length = serializeJson(doc, payload);

  mqtt.publish(
    TOPIC_STATUS.c_str(),
    reinterpret_cast<const uint8_t*>(payload),
    length,
    true
  );
}


// ============================================================
// 12. RELAY STATE PUBLICATION
// ============================================================

void publishRelayState() {

  if (!mqtt.connected()) {
    return;
  }

  StaticJsonDocument<192> doc;

  doc["deviceId"] = DEVICE_ID;
  doc["channel"] = 1;
  doc["state"] = relayState ? "ON" : "OFF";
  doc["timestamp"] = getTimestamp();

  char payload[192];

  size_t length = serializeJson(doc, payload);

  mqtt.publish(
    TOPIC_RELAY_STATE.c_str(),
    reinterpret_cast<const uint8_t*>(payload),
    length,
    true
  );
}


// ============================================================
// 13. COMMAND ACKNOWLEDGEMENT
// ============================================================

void publishCommandAck(
  const String& commandId,
  const char* result
) {

  if (!mqtt.connected()) {
    return;
  }

  StaticJsonDocument<256> doc;

  doc["deviceId"] = DEVICE_ID;
  doc["channel"] = 1;
  doc["commandId"] = commandId;
  doc["commandedState"] = relayState ? "ON" : "OFF";
  doc["status"] = result;
  doc["timestamp"] = getTimestamp();

  char payload[256];

  size_t length = serializeJson(doc, payload);

  mqtt.publish(
    TOPIC_RELAY_ACK.c_str(),
    reinterpret_cast<const uint8_t*>(payload),
    length,
    false
  );
}


// ============================================================
// 14. MQTT COMMAND HANDLER
// ============================================================

void mqttCallback(
  char* topic,
  byte* payload,
  unsigned int length
) {

  StaticJsonDocument<384> doc;

  DeserializationError error =
    deserializeJson(doc, payload, length);

  if (error) {

    Serial.println("Invalid MQTT JSON command");

    return;
  }

  String commandId = doc["commandId"] | "";
  String state = doc["state"] | "";
  int channel = doc["channel"] | 0;

  long expiresAt = doc["expiresAtUnix"] | 0;

  Serial.println();
  Serial.println("Remote command received");

  Serial.print("Command ID: ");
  Serial.println(commandId);

  Serial.print("Requested state: ");
  Serial.println(state);


  // Validate command ID.

  if (commandId.length() == 0) {

    Serial.println("Rejected: missing command ID");

    return;
  }


  // Only relay channel 1 is implemented.

  if (channel != 1) {

    publishCommandAck(commandId, "rejected_invalid_channel");

    return;
  }


  // Validate requested state.

  if (state != "ON" && state != "OFF") {

    publishCommandAck(commandId, "rejected_invalid_state");

    return;
  }


  // Require synchronized time to validate expiry.

  if (!isTimeSynchronized()) {

    publishCommandAck(commandId, "rejected_time_unsynchronized");

    return;
  }


  // Expired or missing expiry timestamps are rejected.

  if (expiresAt <= 0 || time(nullptr) > expiresAt) {

    publishCommandAck(commandId, "rejected_expired");

    return;
  }


  // Prevent duplicate command execution.

  if (commandId == lastCommandId) {

    publishCommandAck(commandId, "duplicate");

    return;
  }


  // Execute command.

  bool requestedState = (state == "ON");

  setRelay(requestedState);

  lastCommandId = commandId;


  // Publish actual commanded relay state.

  publishRelayState();

  publishCommandAck(commandId, "applied");

  Serial.println("Remote command applied");
}


// ============================================================
// 15. MQTT CONNECTION
// ============================================================

void connectMQTT() {

  if (mqtt.connected()) {
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();

  if (now - lastMQTTAttempt < MQTT_RETRY_INTERVAL) {
    return;
  }

  lastMQTTAttempt = now;

  Serial.println("Connecting to EMQX Cloud...");

  String clientId = "SHEM_ESP32_" + String(DEVICE_ID);

  const char* willMessage = "{\"deviceId\":\"001\",\"status\":\"offline\"}";

  bool connected = mqtt.connect(
    clientId.c_str(),
    MQTT_USERNAME,
    MQTT_PASSWORD,
    TOPIC_STATUS.c_str(),
    1,
    true,
    willMessage
  );

  if (connected) {

    Serial.println("EMQX Connected");

    mqtt.subscribe(
      TOPIC_RELAY_COMMAND.c_str(),
      1
    );

    publishDeviceStatus("online");

    publishRelayState();

  } else {

    Serial.print("MQTT connection failed. State: ");
    Serial.println(mqtt.state());
  }
}


// ============================================================
// 16. PZEM READING
// ============================================================

void readPZEM() {

  float v = pzem.voltage();
  float a = pzem.current();
  float w = pzem.power();
  float e = pzem.energy();
  float hz = pzem.frequency();
  float pf = pzem.pf();

  bool valid =
    isfinite(v) &&
    isfinite(a) &&
    isfinite(w) &&
    isfinite(e) &&
    v >= 0 &&
    a >= 0 &&
    w >= 0 &&
    e >= 0;

  if (!valid) {

    meterReadingsValid = false;

    Serial.println("PZEM reading invalid");

    return;
  }

  voltage = v;
  current = a;
  power = w;
  energy = e;

  frequency = hz;
  powerFactor = pf;

  meterReadingsValid = true;
}


// ============================================================
// 17. TELEMETRY PUBLICATION
// ============================================================

void publishTelemetry() {

  if (!mqtt.connected() || !meterReadingsValid) {
    return;
  }

  StaticJsonDocument<512> doc;

  doc["deviceId"] = DEVICE_ID;

  doc["voltage"] = voltage;
  doc["current"] = current;
  doc["power"] = power;

  doc["energy"] = energy;
  doc["energyUnit"] = "kWh";

  if (isfinite(frequency)) {
    doc["frequency"] = frequency;
  }

  if (isfinite(powerFactor)) {
    doc["powerFactor"] = powerFactor;
  }

  doc["relay1State"] = relayState ? "ON" : "OFF";

  doc["supplyType"] = "AC";
  doc["source"] = "PZEM-004T";

  doc["timestamp"] = getTimestamp();

  char payload[512];

  size_t length = serializeJson(doc, payload);

  bool published = mqtt.publish(
    TOPIC_TELEMETRY.c_str(),
    reinterpret_cast<const uint8_t*>(payload),
    length,
    false
  );

  if (published) {
    Serial.println("Telemetry published");
  } else {
    Serial.println("Telemetry publication failed");
  }
}


// ============================================================
// 18. LCD DISPLAY
// ============================================================

void updateLCD() {

  lcd.clear();

  if (!meterReadingsValid) {

    lcd.setCursor(0, 0);
    lcd.print("PZEM Error");

    lcd.setCursor(0, 1);
    lcd.print("Check Meter");

    return;
  }

  switch (lcdPage) {

    case 0:

      lcd.setCursor(0, 0);
      lcd.print("Voltage:");

      lcd.print(voltage, 1);
      lcd.print("V");

      lcd.setCursor(0, 1);
      lcd.print("Current:");

      lcd.print(current, 2);
      lcd.print("A");

      break;


    case 1:

      lcd.setCursor(0, 0);
      lcd.print("Power:");

      lcd.print(power, 1);
      lcd.print("W");

      lcd.setCursor(0, 1);
      lcd.print("Energy:");

      lcd.print(energy, 3);
      lcd.print("kWh");

      break;


    case 2:

      lcd.setCursor(0, 0);
      lcd.print("Freq:");

      if (isfinite(frequency)) {
        lcd.print(frequency, 1);
        lcd.print("Hz");
      } else {
        lcd.print("--");
      }

      lcd.setCursor(0, 1);
      lcd.print("PF:");

      if (isfinite(powerFactor)) {
        lcd.print(powerFactor, 2);
      } else {
        lcd.print("--");
      }

      break;


    case 3:

      lcd.setCursor(0, 0);
      lcd.print("Relay 1:");

      lcd.print(relayState ? "ON" : "OFF");

      lcd.setCursor(0, 1);
      lcd.print("WiFi:");

      lcd.print(
        WiFi.status() == WL_CONNECTED
        ? "Connected"
        : "Offline"
      );

      break;
  }

  lcdPage = (lcdPage + 1) % 4;
}


// ============================================================
// 19. SERIAL MONITOR CONTROL
// ============================================================

void handleSerial() {

  if (!Serial.available()) {
    return;
  }

  char command = Serial.read();

  if (command == '1') {

    setRelay(true);

    publishRelayState();

    Serial.println("Local relay ON");

  } else if (command == '0') {

    setRelay(false);

    publishRelayState();

    Serial.println("Local relay OFF");

  } else if (command == 'r' || command == 'R') {

    readPZEM();

    Serial.println("PZEM refresh requested");
  }
}


// ============================================================
// 20. SETUP
// ============================================================

void setup() {

  Serial.begin(115200);

  delay(500);

  Serial.println();
  Serial.println("================================");
  Serial.println("SHEM ESP32 AC ENERGY MONITOR");
  Serial.println("================================");


  // Initialize relay safely OFF.

  digitalWrite(RELAY_PIN, RELAY_OFF);

  pinMode(RELAY_PIN, OUTPUT);

  setRelay(false);


  // Initialize I2C.

  Serial.println("[1] I2C init");
  Wire.begin(LCD_SDA, LCD_SCL);

  Serial.println("[2] LCD init");
  lcd.init();
  lcd.backlight();

  lcd.setCursor(0, 0);
  lcd.print("SHEM Starting");

  lcd.setCursor(0, 1);
  lcd.print("Please Wait");


  // Initialize MQTT topics.

  String prefix = "shem/device/" + String(DEVICE_ID);

  TOPIC_TELEMETRY = prefix + "/telemetry";
  TOPIC_STATUS = prefix + "/status";

  TOPIC_RELAY_COMMAND = prefix + "/relay/1/command";
  TOPIC_RELAY_STATE = prefix + "/relay/1/state";
  TOPIC_RELAY_ACK = prefix + "/relay/1/ack";


  // PZEM UART is already initialised by the PZEM004Tv30
  // constructor (Serial2, RX, TX). Do not call Serial2.begin() again.


  // Configure WiFi.

  Serial.println("[3] WiFi.mode(STA)");
  WiFi.mode(WIFI_STA);
  Serial.println("[4] WiFi mode set");
  WiFi.persistent(false);
  WiFi.setAutoReconnect(false);   // we handle reconnects in connectWiFi()
  WiFi.setSleep(false);


  // Configure TLS certificate validation.

  secureClient.setCACert(MQTT_ROOT_CA);


  // Configure MQTT.

  mqtt.setServer(MQTT_HOST, MQTT_PORT);

  mqtt.setCallback(mqttCallback);

  mqtt.setBufferSize(512);

  mqtt.setKeepAlive(30);

  mqtt.setSocketTimeout(5);


  // Start network connection.

  connectWiFi();


  // Configure NTP time.

  configTime(
    0,
    0,
    "pool.ntp.org",
    "time.google.com"
  );


  readPZEM();

  updateLCD();

  Serial.println("SHEM initialization complete");
}


// ============================================================
// 21. MAIN LOOP
// ============================================================

void loop() {

  connectWiFi();

  if (WiFi.status() == WL_CONNECTED) {

    connectMQTT();

    if (mqtt.connected()) {
      mqtt.loop();
    }
  }


  // Local Serial control.

  handleSerial();


  unsigned long now = millis();


  // Refresh PZEM readings.

  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL) {

    lastTelemetryTime = now;

    readPZEM();

    publishTelemetry();
  }


  // LCD refresh.

  if (now - lastLCDTime >= LCD_INTERVAL) {

    lastLCDTime = now;

    updateLCD();
  }

  // Give IDLE tasks / WiFi stack time to run.
  delay(10);
}