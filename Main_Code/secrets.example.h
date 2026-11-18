// Copy this file to secrets.h (same folder) and fill in your values.
// secrets.h is git-ignored so credentials never reach the repository.
#pragma once

// ------------------------------------------------------------
// WiFi Networks (priority order: index 0 = highest priority)
// Add or remove entries freely. Update WIFI_NETWORK_COUNT too.
// ------------------------------------------------------------

struct WiFiCredential {
  const char* ssid;
  const char* password;
};

const WiFiCredential WIFI_NETWORKS[] = {
  { "your-first-wifi",  "first-password"  },   // 0 — highest priority
  // { "your-second-wifi", "second-password" }, // 1
  // { "your-third-wifi",  "third-password"  }, // 2
  // { "your-fourth-wifi", "fourth-password" }, // 3
};

const int WIFI_NETWORK_COUNT = 1;   // <-- keep in sync with active entries above (max 4)

// ------------------------------------------------------------
// MQTT Credentials
// ------------------------------------------------------------

const char* MQTT_USERNAME = "your-emqx-device-username";
const char* MQTT_PASSWORD = "your-emqx-device-password";
