# SHEM: Complete Local Setup Guide

This guide takes you from **"I have the GitHub repo and the hardware"** to **"SHEM is running on my PC and my phone, showing live readings from my meter."**

It's written for beginners. Follow the steps in order and don't skip any. Each step tells you what to do, why, and how to check it worked.

> **Time needed:** about 2–3 hours the first time (most of it is installing things and wiring).
> **Main guide is for Windows.** macOS and Linux differences are noted where the commands change.

---

## Table of contents

0. [What you are building](#0-what-you-are-building)
1. [Hardware checklist](#1-hardware-checklist)
2. [Software and accounts you need](#2-software-and-accounts-you-need)
3. [Get the code](#3-get-the-code)
4. [Set up the MQTT broker (EMQX Cloud)](#4-set-up-the-mqtt-broker-emqx-cloud)
5. [Wire the hardware](#5-wire-the-hardware)
6. [Flash the ESP32 firmware](#6-flash-the-esp32-firmware)
7. [Set up the backend (Python)](#7-set-up-the-backend-python)
8. [Set up the frontend (Node.js)](#8-set-up-the-frontend-nodejs)
9. [Run SHEM](#9-run-shem)
10. [First-time setup inside the app](#10-first-time-setup-inside-the-app)
11. [Install the app on your phone](#11-install-the-app-on-your-phone)
12. [Final checklist: is everything working?](#12-final-checklist-is-everything-working)
13. [Everyday use: starting and stopping](#13-everyday-use-starting-and-stopping)
14. [Optional extras (AI assistant, voice, remote access)](#14-optional-extras)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick reference](#16-quick-reference)

---

## 0. What you are building

```
 ┌──────────────┐   MQTT over TLS   ┌──────────────────┐   MQTT over TLS   ┌────────────────────┐
 │  ESP32 board │ ────────────────► │  EMQX Cloud      │ ◄──────────────── │  SHEM backend      │
 │  + PZEM-004T │ ◄──────────────── │  (MQTT broker on │ ────────────────► │  (Python, on your  │
 │  + relay     │  relay commands   │   the internet)  │   live readings   │   PC)              │
 │  + LCD       │                   └──────────────────┘                   │  + database        │
 └──────────────┘                                                          │  + web app         │
   measures your                                                           └─────────┬──────────┘
   appliance's power,                                                                │ HTTPS (your Wi-Fi)
   switches it ON/OFF                                                       ┌────────▼─────────┐
                                                                            │  Browser / phone │
                                                                            │  (SHEM app)      │
                                                                            └──────────────────┘
```

- The **ESP32** reads voltage, current, power and energy from the **PZEM-004T** meter every 2 seconds, shows them on the **LCD**, and sends them to the **MQTT broker**.
- The **backend** (a Python program on your PC) receives those readings, stores them in a local database file (`shem.db`), and serves the **web app**.
- You open the web app on your PC or phone. When you press the ON/OFF button, the command goes backend → broker → ESP32 → **relay**.
- The ESP32 and the PC never talk directly. Both connect to the broker on the internet, so **both need internet access**.

> **Don't have the hardware yet?** You can still run the software (sections 7–10). The device will show as *offline*, but simulated appliances, bills, tariff, budget and the AI assistant all work.

---

## 1. Hardware checklist

| # | Item | Notes |
|---|------|-------|
| 1 | **ESP32 DevKit** (ESP32-WROOM-32, 30 or 38 pin) | The main controller |
| 2 | **PZEM-004T v3.0** energy meter | Must be **v3.0** (the firmware uses the v3 library). It comes in a 10 A version (inline shunt) or a 100 A version (with a CT clamp coil) |
| 3 | **1-channel relay module, 5 V** | The firmware assumes the relay is **active LOW** (the most common type). Pick one rated for your appliance's current (e.g. 10 A / 250 VAC) |
| 4 | **16x2 LCD with I2C backpack** (PCF8574) | I2C address is usually `0x27` (sometimes `0x3F`) |
| 5 | Jumper wires (female-female / male-female) | For the low-voltage side |
| 6 | **Micro-USB or USB-C data cable** | It must be a *data* cable, not a charge-only one. Use whichever connector your ESP32 has |
| 7 | AC plug, socket, mains-rated wire, enclosure/terminal blocks | For the 230 V side |
| 8 | A test appliance (e.g. a bulb or fan) | What SHEM will measure and switch |
| 9 | A PC/laptop (Windows 10/11, macOS or Linux) | Runs the backend |
| 10 | **2.4 GHz Wi-Fi** with internet | The ESP32 **can't** join 5 GHz-only networks |
| 11 | A smartphone (optional) | Android or iPhone, on the same Wi-Fi as the PC |

> ⚠️ **SAFETY: MAINS ELECTRICITY CAN KILL.** The PZEM-004T and the relay are connected to 230 V AC. Always unplug everything before touching any wire. Never touch the PZEM or relay terminals while it is plugged in. Put the mains parts inside an insulated box. **If you have never wired mains before, get someone experienced to do or check the AC wiring.**

---

## 2. Software and accounts you need

Install these **in this order**. After each install, **close and reopen** your terminal so it picks up the new program.

### 2.1 Git (downloads the code)
- Download: <https://git-scm.com/downloads>. On Windows, the default options are fine.
- Check it: open **PowerShell** (Start menu → type "PowerShell") and run:
  ```powershell
  git --version
  ```
  You should see something like `git version 2.x`.

### 2.2 Python 3.11 or newer (runs the backend)
- Download: <https://www.python.org/downloads/>
- **Windows: on the first installer screen, tick ☑ "Add python.exe to PATH".** This matters, so don't skip it.
- Check it:
  ```powershell
  python --version
  ```
  You should see `Python 3.11` or higher. On macOS/Linux, use `python3 --version` (and `python3` instead of `python` everywhere in this guide).

### 2.3 Node.js 22 LTS or newer (builds the web app)
- Download the **LTS** version: <https://nodejs.org/>
- Check it:
  ```powershell
  node --version
  npm --version
  ```
  `node` should be `v22.12` or higher (v24 is fine too).

### 2.4 Arduino IDE 2.x (puts the firmware on the ESP32)
- Download: <https://www.arduino.cc/en/software>
- You'll configure it in [section 6](#6-flash-the-esp32-firmware).

### 2.5 USB driver for the ESP32 (Windows, sometimes macOS)
Plug the ESP32 into the PC, then open **Device Manager → Ports (COM & LPT)**.
- If you see something like `Silicon Labs CP210x (COM5)` or `USB-SERIAL CH340 (COM5)`, you're done. Note the **COM number**.
- If nothing appears, or you see an "Unknown device", install the driver for the chip printed on your board, near the USB port:
  - **CP2102/CP2104**: <https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers>
  - **CH340/CH341**: search "CH340 driver" on the WCH website (wch-ic.com)
- Still nothing? Try a different USB cable (a charge-only cable is the most common cause).

### 2.6 A code/text editor (recommended)
- **VS Code**: <https://code.visualstudio.com/>. Notepad works too, but VS Code makes editing `.env` files much easier.

### 2.7 Accounts
| Account | Needed? | Why |
|---------|---------|-----|
| **EMQX Cloud** (<https://cloud.emqx.com>) | **Required**, unless the repo owner gives you broker access | The MQTT broker the ESP32 and backend talk through. The free *Serverless* plan is enough |
| GitHub | Only if the repo is private | To clone it |
| Google AI Studio (Gemini key) and/or Groq | Optional | For the SHEM AI chat assistant ([section 14](#14-optional-extras)) |
| Sarvam AI | Optional | For the voice assistant |

---

## 3. Get the code

Pick a folder for the project, for example your Documents folder.

```powershell
cd $HOME\Documents
git clone https://github.com/chakradhar1778/SHEM.git
cd SHEM
```

(On macOS/Linux: `cd ~/Documents` and then the same two commands.)

You should now have this structure:

```
SHEM/
├── Main_Code/          ← ESP32 firmware (Arduino)
│   ├── Main_Code.ino
│   └── secrets.example.h
├── backend/            ← Python server (FastAPI + SQLite)
│   ├── .env.example
│   ├── certs/emqxsl-ca.crt
│   ├── requirements.txt
│   └── run.py
├── frontend/           ← React web app
│   ├── .env.example
│   └── package.json
├── start.py            ← one command to run everything
└── SETUP.md            ← this file
```

---

## 4. Set up the MQTT broker (EMQX Cloud)

The ESP32 and the backend both connect to an MQTT broker. Choose **one** of these options:

### Option A: Use the repo owner's existing broker
If the owner gives you:
- the broker **hostname** (it looks like `xxxxxxxx.ala.asia-southeast1.emqxsl.com`),
- a **device username + password** (for the ESP32),
- a **backend username + password** (for the PC),

then skip to [section 5](#5-wire-the-hardware). The hostname already in the code is the owner's broker.

### Option B: Create your own free broker (recommended if you're setting up independently)

1. Go to <https://cloud.emqx.com> and sign up.
2. Click **New Deployment** → choose **Serverless** (free tier) → pick the region closest to you → **Deploy**. Wait until the status shows **Running**.
3. Open the deployment's **Overview** page and write down:
   - **Address / Connect address**, e.g. `ab12cd34.ala.asia-southeast1.emqxsl.com`. This is your **MQTT host**.
   - **MQTT over TLS/SSL port**: `8883`.
4. On the same page, click **CA Certificate → Download**. Save it as:
   ```
   SHEM/backend/certs/emqxsl-ca.crt
   ```
   (replacing the file that's already there).
5. Go to **Access Control → Authentication → Add** and create **two users**:

   | Username | Password | Used by |
   |----------|----------|---------|
   | `shem_device` (any name you like) | a strong password | the ESP32 |
   | `shem_backend` | a different strong password | the backend on your PC |

   Write all four values down. You'll need them in sections 6 and 7.
6. *(Only if you've turned on authorization/ACL rules.)* Allow both users to publish and subscribe to `shem/device/#`. By default Serverless allows this, so you can normally skip this step.

7. **Tell the firmware about your broker.** Open `Main_Code/Main_Code.ino` in any editor, find this line (near the top, around line 63), and replace the hostname with **your** address:
   ```cpp
   const char* MQTT_HOST = "xf061010.ala.asia-southeast1.emqxsl.com";   // ← change to yours
   ```
   *About the certificate in the firmware:* `Main_Code.ino` already contains the **DigiCert Global Root G2** certificate (the `MQTT_ROOT_CA` block). EMQX Serverless uses this same root, so you normally **don't** need to change it. To double-check, open the `.crt` you downloaded in a text editor. If its text differs from the `MQTT_ROOT_CA` block, paste yours between the `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----` lines.

You'll put the backend's broker details in the `.env` file in [section 7](#7-set-up-the-backend-python).

---

## 5. Wire the hardware

> ⚠️ **Do all wiring with everything UNPLUGGED from the mains and from USB.**

### 5.1 Pin map (low-voltage side)

| From | To (ESP32) | Notes |
|------|------------|-------|
| **PZEM-004T 5V** | **VIN / 5V** | The PZEM's TTL side needs 5 V |
| **PZEM-004T GND** | **GND** | |
| **PZEM-004T TX** | **GPIO16** (RX2) | The ESP32 *receives* on GPIO16 |
| **PZEM-004T RX** | **GPIO17** (TX2) | The ESP32 *transmits* on GPIO17 |
| **LCD VCC** | **VIN / 5V** | |
| **LCD GND** | **GND** | |
| **LCD SDA** | **GPIO21** | |
| **LCD SCL** | **GPIO22** | |
| **Relay VCC** | **VIN / 5V** | |
| **Relay GND** | **GND** | |
| **Relay IN** | **GPIO23** | |

> **Note on the PZEM TX/RX:** the code sets up the PZEM serial port as `PZEM004Tv30(Serial2, 16, 17)`, which means **GPIO16 = ESP32 receive** and **GPIO17 = ESP32 transmit**. Wire **PZEM TX → GPIO16** and **PZEM RX → GPIO17** (TX always goes to RX). The comment at the top of `Main_Code.ino` labels these the other way round. If you get no readings, swap these two wires. It won't damage anything.

All the GND wires must be connected together (common ground).

### 5.2 Mains side (230 V AC)

```
 Mains plug                                                     Appliance socket
   L (live) ───── [PZEM CT coil around this wire] ─── Relay COM ┐
                  (or through the PZEM 10A terminals)            │
                                                     Relay NO ───┴──── socket L
   N (neutral) ─────────────────────────────────────────────────────── socket N

 PZEM voltage terminals:  L ── mains L,   N ── mains N
```

- **PZEM voltage input**: connect the PZEM's two AC voltage terminals to mains **L** and **N**. This powers its measuring circuit.
- **PZEM current sensing**:
  - *100 A version:* pass the **live wire only** through the CT coil (clamp).
  - *10 A version:* the live wire goes **through** the PZEM's current terminals (in series).
- **Relay**: put the relay **in series with the live wire** going to the appliance socket. Use **COM** and **NO** (normally open), so the appliance is **OFF** whenever the ESP32 is off or rebooting.
- Neutral goes straight to the socket.
- Insulate every exposed conductor, and put the AC parts in an enclosure.

### 5.3 Before powering on
- [ ] No bare mains wire is exposed
- [ ] The relay switches the **live** wire, using COM + NO
- [ ] PZEM TX/RX go to GPIO16/17, and the LCD goes to GPIO21/22
- [ ] All grounds are connected together
- [ ] Nothing metallic touches the boards

---

## 6. Flash the ESP32 firmware

### 6.1 Add ESP32 support to the Arduino IDE
1. Open **Arduino IDE** → **File → Preferences**.
2. In **Additional boards manager URLs**, paste:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
   and click **OK**.
3. Go to **Tools → Board → Boards Manager**, search for **esp32**, and install **"esp32 by Espressif Systems"** (latest version).

### 6.2 Install the libraries
Go to **Tools → Manage Libraries** (or **Sketch → Include Library → Manage Libraries**), then search for and install each of these:

| Search for | Install this one (author) |
|------------|---------------------------|
| `PubSubClient` | **PubSubClient** by Nick O'Leary |
| `ArduinoJson` | **ArduinoJson** by Benoit Blanchon (v7 works but shows harmless "deprecated" warnings; v6.21.x shows none) |
| `PZEM004Tv30` | **PZEM-004T-v30** by Jakub Mandula |
| `LiquidCrystal I2C` | **LiquidCrystal I2C** by Frank de Brabander |

(`WiFi`, `WiFiClientSecure` and `Wire` come with the ESP32 board package, so you don't install them separately.)

### 6.3 Create the secrets file (Wi-Fi + broker login)
1. In the `Main_Code` folder, **copy** `secrets.example.h` and name the copy **`secrets.h`** (same folder).
   ```powershell
   Copy-Item Main_Code\secrets.example.h Main_Code\secrets.h
   ```
   (macOS/Linux: `cp Main_Code/secrets.example.h Main_Code/secrets.h`)
2. Open `secrets.h` and fill in your values:
   ```cpp
   const char* WIFI_SSID = "YourWiFiName";          // 2.4 GHz network, exact spelling, case-sensitive
   const char* WIFI_PASSWORD = "YourWiFiPassword";

   const char* MQTT_USERNAME = "shem_device";       // the DEVICE user from section 4
   const char* MQTT_PASSWORD = "device-password";
   ```
   `secrets.h` is git-ignored, so your passwords never get uploaded to GitHub.

3. *(Optional)* `DEVICE_ID` in `Main_Code.ino` is `"001"`. If you change it, use the **same** value for `DEVICE_ID` in the backend `.env`.

### 6.4 Upload
1. Open `Main_Code/Main_Code.ino` in the Arduino IDE (**File → Open**). It must stay inside the folder named `Main_Code`.
2. **Tools → Board → esp32 → ESP32 Dev Module**
3. **Tools → Port →** pick your ESP32's COM port (from step 2.5).
4. Click **Upload** (the → arrow button).
   - If you see `Connecting........_____` and it times out, **hold the BOOT button** on the ESP32 until the upload starts, then let go.
5. Wait for **"Done uploading"**.

### 6.5 Check it's running
1. Open **Tools → Serial Monitor** and set the speed (bottom right) to **115200 baud**.
2. Press the **EN/RST** button on the ESP32. You should see:
   ```
   SHEM ESP32 AC ENERGY MONITOR
   [1] I2C init
   [2] LCD init
   ...
   WiFi connected ...
   MQTT connected ...
   SHEM initialization complete
   ```
3. The LCD shows "SHEM Starting", then live readings.
4. In the EMQX Cloud console, under **Clients** or **Monitoring**, you should see one connected client.

If any of this doesn't happen, see [Troubleshooting](#15-troubleshooting).

---

## 7. Set up the backend (Python)

Open **PowerShell** in the `SHEM` folder for all of these commands.

### 7.1 Create a virtual environment (an isolated place for Python packages)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
- After this, your prompt starts with `(.venv)`. **You need to activate it every time you open a new terminal** to run SHEM.
- **Windows error "running scripts is disabled on this system"?** Run this once, then try again:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```
- macOS/Linux:
  ```bash
  cd backend
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 7.2 Install the backend packages
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```
This takes 1–3 minutes.

### 7.3 Create the `.env` settings file
```powershell
Copy-Item .env.example .env
```
(macOS/Linux: `cp .env.example .env`)

**Generate an API key.** This is the password the web app uses to talk to the backend:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the long output and keep it safe. You'll paste it into the app in section 10.

Open `backend/.env` in your editor and change **these lines** (leave everything else as it is):

```ini
# Broker (from section 4: the BACKEND user, not the device user)
MQTT_HOST=ab12cd34.ala.asia-southeast1.emqxsl.com     # your broker address
MQTT_PORT=8883
MQTT_USERNAME=shem_backend
MQTT_PASSWORD=your-backend-password
MQTT_CA_CERT_PATH=./certs/emqxsl-ca.crt

# Must match DEVICE_ID in Main_Code.ino
DEVICE_ID=001

# Paste the key you just generated
API_KEY=paste-the-64-character-key-here

# Your timezone (used for "today", "this month", etc.)
TIMEZONE=Asia/Kolkata

# Your electricity rate in ₹/kWh (you can change this later in the app)
DEFAULT_TARIFF_RATE_INR_PER_KWH=7.5
```

> ❗ If `API_KEY` is left empty, the backend **refuses every request** (this is a deliberate safety default). Always set it.

> AI and voice keys (`GEMINI_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`) are optional. You can leave them empty for now ([section 14](#14-optional-extras)).

### 7.4 (Optional) Run the tests to confirm the install
```powershell
pip install -r requirements-dev.txt
python -m pytest
```
All tests should pass. They use a temporary database and a fake broker, so they don't touch your hardware.

---

## 8. Set up the frontend (Node.js)

Open a terminal in the `SHEM` folder:
```powershell
cd frontend
npm install
```
This downloads the web app's packages (1–3 minutes; warnings are normal, errors are not).

You **don't** need a frontend `.env` file for normal use. The defaults work, and you'll enter the API key inside the app.

> `start.py` (next section) also runs `npm install` and the build automatically if you forget. Running it yourself first just makes problems easier to spot.

---

## 9. Run SHEM

There are two ways to run SHEM. **Most people should use Option 1.**

### Option 1 (recommended): one command, works on PC and phone

From the **`SHEM`** folder (not `backend`), with the virtual environment **activated**:

```powershell
cd ..                                # back to the SHEM folder, if you're in backend/ or frontend/
backend\.venv\Scripts\Activate.ps1   # skip if your prompt already shows (.venv)
python start.py
```
(macOS/Linux: `source backend/.venv/bin/activate` then `python3 start.py`)

What it does:
1. Finds your PC's Wi-Fi IP address (e.g. `192.168.1.20`).
2. Creates a private HTTPS certificate for it (once; stored in `backend/.https/`).
3. Builds the web app (first run takes about a minute; after that it only rebuilds when files change).
4. Starts everything and prints:

```
──────────────────────────────────────────────────────────
  SHEM is starting

  Phone, first time : http://192.168.1.20:8080   (set-up page)
  Phone, after that : https://192.168.1.20:8443/  (or the home-screen icon)
  This PC           : https://localhost:8443/

  Phone and PC must be on the same Wi-Fi. Ctrl+C to stop.
──────────────────────────────────────────────────────────
```

- **Windows Firewall pop-up:** click **Allow access** and tick **Private networks**. Otherwise your phone can't connect.
- **On the PC:** open <https://localhost:8443/>. The browser warns that the connection isn't private, because it doesn't know SHEM's home-made certificate yet. Click **Advanced → Continue to localhost**. (To get rid of the warning permanently, see [Troubleshooting](#browser-says-your-connection-is-not-private-on-the-pc).)
- **Keep this terminal window open** while you use SHEM. To stop, press **Ctrl + C**.

Options: `python start.py --port 8443 --setup-port 8080 --no-build`

### Option 2 (for developers editing the code): two terminals, live reload

**Terminal 1, backend:**
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python run.py
```
API at <http://127.0.0.1:8000>, API docs at <http://127.0.0.1:8000/docs>.

**Terminal 2, frontend:**
```powershell
cd frontend
npm run dev
```
Open <http://localhost:5173>. Code changes appear instantly. (Phones can't install the app or use the microphone in this mode, because it's plain HTTP.)

---

## 10. First-time setup inside the app

1. Open the app (<https://localhost:8443/> from Option 1).
2. Go to **Settings → Backend connection**.
   - **Backend URL:** leave it **empty** (same server).
   - **API key:** paste the `API_KEY` from `backend/.env`.
   - Save. The key is stored only in this browser, so **repeat this on each device** (phone, other PCs).
3. The dashboard should show the device as **Online** with live voltage/power updating every ~2 seconds.
4. Set up your home:
   - **Settings → Electricity tariff:** your rate or slabs, fixed charge, and **billing cycle day** (the day your meter is read).
   - **Devices → Add:** add your appliances. For the appliance that's actually connected to the relay, choose **Connection → Real relay**. Any others can be **Simulated device**, which models typical usage so the whole home's numbers make sense.
   - **Bills:** add past electricity bills (a photo/PDF is optional).
   - **Target:** set a monthly budget.
5. Test the relay: press the **ON/OFF** control for the relay appliance. You should hear the relay click, and the status changes to *applied* within a second or two.

---

## 11. Install the app on your phone

The phone and PC must be on the **same Wi-Fi**, and `python start.py` must be running.

1. On the phone, open the **"Phone, first time"** address shown in the terminal, e.g. `http://192.168.1.20:8080`.
2. Tap **1 · Download certificate** and follow the on-screen steps for your phone:
   - **Android:** Settings → search "CA certificate" → Install a certificate → CA certificate → Install anyway → pick `shem-ca.crt`.
   - **iPhone (use Safari):** Allow → Settings → *Profile Downloaded* → Install. Then **Settings → General → About → Certificate Trust Settings** → turn on **SHEM Local CA**.
3. Tap **2 · Open SHEM**.
4. Install it:
   - Android Chrome: **⋮ → Install app**
   - iPhone Safari: **Share → Add to Home Screen**
5. In the app: **Settings → Backend connection** → paste the API key.

You only need to do this once per phone. If your PC's IP address changes later, `start.py` issues a new certificate automatically, and the phone still trusts it (it trusts the SHEM CA, not the individual certificate). Just use the new address.

---

## 12. Final checklist: is everything working?

| # | Check | How |
|---|-------|-----|
| 1 | ESP32 on Wi-Fi + broker | Serial Monitor shows "WiFi connected" and "MQTT connected"; EMQX console shows the client |
| 2 | LCD shows readings | Voltage around 230 V; power rises when the appliance is ON |
| 3 | Backend connected to the broker | Terminal log shows `MQTT connected to …` and no repeating errors |
| 4 | Health check | Open `https://localhost:8443/api/health`. It should say `"status":"ok"` |
| 5 | App connected | Dashboard shows the device **Online** with numbers updating |
| 6 | Relay works | Toggle in the app → relay clicks → appliance switches |
| 7 | Phone works | App opens from the home-screen icon with live data |

---

## 13. Everyday use: starting and stopping

**Start:**
1. Power the ESP32 (USB charger or PC). It reconnects on its own.
2. On the PC:
   ```powershell
   cd $HOME\Documents\SHEM
   backend\.venv\Scripts\Activate.ps1
   python start.py
   ```
3. Open the app on your PC or tap the home-screen icon on your phone.

**Stop:** press **Ctrl + C** in the terminal.

**Your data** lives in `backend/shem.db` (readings, appliances, bills) and `backend/uploads/` (bill photos). **Back up both** if you care about the history. Neither is uploaded to GitHub.

**Updating to a newer version of the code:**
```powershell
cd $HOME\Documents\SHEM
git pull
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python start.py          # rebuilds the frontend automatically; the database upgrades itself
```
If `Main_Code.ino` changed, re-upload the firmware (section 6.4).

---

## 14. Optional extras

### 14.1 SHEM AI chat assistant
Get at least one key:
- **Gemini:** <https://aistudio.google.com/apikey>
- **Groq:** <https://console.groq.com/keys>

Put it in `backend/.env`:
```ini
AI_ENABLED=true
AI_PRIMARY_PROVIDER=gemini      # or groq
GEMINI_API_KEY=your-key
GROQ_API_KEY=your-key           # optional backup; used automatically if the primary fails
```
Restart `start.py`. If both keys are empty, AI chat is unavailable, but everything else works.

### 14.2 Voice assistant (SHEM AI Live)
Get a key from <https://dashboard.sarvam.ai> and set `SARVAM_API_KEY=` in `backend/.env`. The microphone only works over **HTTPS**, which Option 1 (`start.py`) already provides.

### 14.3 Access from outside your home (Cloudflare Tunnel)
See the **"Remote access"** section of `backend/README.md`. In short: install `cloudflared`, run the backend with `python run.py`, then run `cloudflared tunnel --url http://localhost:8000`, and add the tunnel's URL to `ALLOWED_ORIGINS` in `.env`.

---

## 15. Troubleshooting

### ESP32 / firmware

| Problem | Fix |
|---------|-----|
| **No COM port** in the Arduino IDE | Install the CP210x/CH340 driver (step 2.5); try another USB cable (it must carry data) or another USB port |
| Upload stuck at `Connecting....___` | Hold **BOOT** during the upload; close the Serial Monitor; lower **Tools → Upload Speed** to 115200 |
| `secrets.h: No such file or directory` | You didn't create `Main_Code/secrets.h` (step 6.3). It must be in the same folder as `Main_Code.ino` |
| `PZEM004Tv30.h` / `PubSubClient.h` not found | Install the libraries from step 6.2 |
| Wi-Fi never connects | Use a **2.4 GHz** network; check the SSID/password spelling (case-sensitive); move the ESP32 closer to the router; avoid hotspots with special characters in the name |
| Wi-Fi OK but **MQTT fails** (e.g. `rc=-2`, `rc=5`) | `rc=5` / `rc=4` = wrong broker username/password → check `secrets.h` uses the **device** user. `rc=-2` = can't reach the broker → check `MQTT_HOST` in `Main_Code.ino`, that the network allows port 8883, and that the board's time synced (TLS needs the correct time, which comes from NTP automatically) |
| LCD lights up but shows **blocks or nothing** | Turn the small blue **contrast screw** on the back; if still blank, change `0x27` to `0x3F` in `Main_Code.ino` (`LiquidCrystal_I2C lcd(0x27, 16, 2);`) and re-upload |
| Readings are **NaN / 0** or "PZEM error" | Swap the PZEM TX/RX wires (GPIO16/17); check the PZEM has 5 V and **mains connected to its voltage terminals** (it doesn't answer without AC) |
| Relay works **backwards** (ON when it should be OFF) | Your relay is active-HIGH. In `Main_Code.ino`, swap the two lines to `#define RELAY_ON HIGH` and `#define RELAY_OFF LOW`, then re-upload |
| ESP32 keeps rebooting | Weak USB power. Use a good 5 V/1 A+ adapter or a powered USB port |

### Backend / PC

| Problem | Fix |
|---------|-----|
| `python` is not recognized | Reinstall Python with **"Add python.exe to PATH"** ticked, then reopen the terminal |
| `Activate.ps1 cannot be loaded … scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: No module named 'fastapi'` (or `cryptography`, `uvicorn`) | The virtual environment isn't active (no `(.venv)` in the prompt), or the packages aren't installed → activate it and run `pip install -r backend/requirements.txt` |
| `npm not found` when running `start.py` | Install Node.js (step 2.3) and reopen the terminal |
| Every request in the app says **401 / Unauthorized** | The API key in **Settings → Backend connection** doesn't match `API_KEY` in `backend/.env` (or `API_KEY` is empty). Restart `start.py` after editing `.env` |
| Backend log shows **MQTT connection refused / not authorised** | Wrong `MQTT_USERNAME`/`MQTT_PASSWORD` in `.env` → use the **backend** user from section 4 |
| Backend log shows **certificate verify failed** / CA file missing | `backend/certs/emqxsl-ca.crt` is missing or from a different broker → re-download it from your EMQX deployment's Overview page |
| App shows device **Offline** but the ESP32 says MQTT connected | `DEVICE_ID` differs between `Main_Code.ino` and `.env`, or the ESP32 and backend use **different brokers** (`MQTT_HOST`) |
| `Address already in use` / port 8443 busy | Another copy is already running (close it), or use `python start.py --port 9443` |
| `ZoneInfoNotFoundError` / timezone error | `pip install tzdata` (it's in requirements; reinstall them) |
| Frontend build fails (`tsc` / `vite` errors) | Check `node --version` is 22.12+; delete `frontend/node_modules` and run `npm install` again |

### Phone / browser

| Problem | Fix |
|---------|-----|
| Phone can't open `http://<pc-ip>:8080` | Same Wi-Fi? (Not guest Wi-Fi, which often blocks devices from seeing each other.) Allow Python through **Windows Firewall** (Control Panel → Windows Defender Firewall → Allow an app → tick Python for **Private**); make sure your Wi-Fi network is set to **Private** in Windows network settings |
| Phone says "not secure" / certificate error | Repeat section 11 step 2. On iPhone, the **Certificate Trust Settings** toggle is the step people usually miss |
| No "Install app" option | You must be on the **https://…:8443** address with the certificate trusted, not the http set-up page |
| <a id="browser-says-your-connection-is-not-private-on-the-pc"></a>Browser says **"Your connection is not private"** on the PC | Click Advanced → Continue. To fix it permanently on Windows: double-click `backend\.https\shem-ca.crt` → **Install Certificate** → **Current User** → *Place all certificates in the following store* → **Trusted Root Certification Authorities** → Finish, then restart the browser |
| IP address changed (new router, etc.) | Just restart `start.py`. It prints the new address and issues a new certificate automatically |

---

## 16. Quick reference

### Files you create (never committed to Git)
| File | What's in it |
|------|--------------|
| `Main_Code/secrets.h` | Wi-Fi name/password, broker **device** username/password |
| `backend/.env` | Broker **backend** login, `API_KEY`, timezone, optional AI keys |
| `backend/shem.db` | Your data (created automatically) |
| `backend/uploads/` | Bill photos/PDFs (created automatically) |
| `backend/.https/` | SHEM's private HTTPS certificates (created by `start.py`; **never share the `.key` files**) |

### Values that must match
| Value | Location 1 | Location 2 |
|-------|-----------|-----------|
| Broker address | `MQTT_HOST` in `Main_Code/Main_Code.ino` | `MQTT_HOST` in `backend/.env` |
| Device ID | `DEVICE_ID` in `Main_Code/Main_Code.ino` | `DEVICE_ID` in `backend/.env` |
| API key | `API_KEY` in `backend/.env` | App → Settings → Backend connection |

### Ports
| Port | Used for |
|------|----------|
| 8443 | SHEM app + API over HTTPS (`start.py`) |
| 8080 | Phone set-up page (`start.py`) |
| 8000 | Backend in developer mode (`run.py`) |
| 5173 | Frontend dev server (`npm run dev`) |
| 8883 | MQTT over TLS (outgoing, to EMQX Cloud) |

### MQTT topics (for debugging in the EMQX console)
| Topic | Direction |
|-------|-----------|
| `shem/device/001/telemetry` | ESP32 → backend, every 2 s |
| `shem/device/001/status` | ESP32 → backend (online/offline) |
| `shem/device/001/relay/1/command` | backend → ESP32 |
| `shem/device/001/relay/1/state` | ESP32 → backend |
| `shem/device/001/relay/1/ack` | ESP32 → backend |

### Firmware pin summary
| Part | ESP32 pin |
|------|-----------|
| PZEM TX → | GPIO16 |
| PZEM RX → | GPIO17 |
| LCD SDA / SCL | GPIO21 / GPIO22 |
| Relay IN | GPIO23 (active LOW) |

### More detail
- `backend/README.md`: API endpoints, simulation, billing, alerts, AI, data retention, remote access
- `frontend/README.md`: frontend specifics
