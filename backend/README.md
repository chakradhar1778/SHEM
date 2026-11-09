# SHEM Backend

FastAPI + SQLite backend for SHEM. Receives PZEM-004T AC telemetry from the ESP32 via EMQX (MQTT/TLS), controls relay 1, stores household data, and serves insights. The React frontend talks only to this API, never to EMQX.

## Run

```bash
pip install -r requirements.txt        # tzdata is needed on Windows for TIMEZONE
cp .env.example .env                   # fill MQTT_PASSWORD, API_KEY
python run.py                          # http://127.0.0.1:8000/docs
```

## Frontend (React)

```bash
cd ../frontend
npm install
npm run dev          # http://localhost:5173, /api (incl. WebSocket) is proxied to the backend on :8000
npm run build        # the backend then serves frontend/dist at "/" (FRONTEND_DIST_PATH)
```

Enter the API key once in **Settings → Backend connection**. It's stored only on that device. Every other piece of data (home setup, rooms, appliances, bills, target) lives in the backend database. Appliances linked to the relay are real (switched by the relay, measured by the PZEM). Every other appliance runs as a **simulated device** (see below) and is tagged *Simulated* wherever its usage appears.

## Simulated appliances

The prototype has one relay, so only one appliance can be measured for real. In **Devices → Add/Edit → Connection**, choose *Real relay* or *Simulated device* (the default when no relay is selected). Simulated devices are handled by `app/services/simulation_service.py`:

* **Power** follows a type-specific model × quantity, ticked every 2 s: fridge and AC compressor cycles with start-up surge, inverter AC modulation, TV brightness fluctuation, fan drift, a geyser thermostat, washing-machine (60 min) and dishwasher (90 min) programmes that finish and switch themselves off, and resistive loads scaled by the live mains voltage (from the meter when it's fresh).
* **Routine**: with *Follow routine*, the device runs about its "hours used per day" at typical times (lights in the evening, fans and AC at night, geyser in the morning, kitchen appliances at mealtimes, fridge always on). *Manual only* turns the routine off.
* **On/off switch**: `POST /api/simulation/appliances/{id}/command {"state":"ON"|"OFF"}` applies immediately. It overrides the routine until the routine's next scheduled change, or indefinitely when the routine is off. `POST …/auto` resumes the routine. `GET /api/simulation/status` returns live state.
* **Energy** is integrated (P × Δt) into `sim_energy_hourly` (per appliance, per local hour). Insights add it to metered energy, so home totals, budget and target include it. Nothing is back-filled: history starts when the appliance is added and accrues only while the backend runs.
* WebSocket: `init_snapshot.simStatus` and a `sim_update` event every 2 s. `SIMULATION_ENABLED=false` turns the loop off.

Day breakdowns: `GET /api/insights/today?date=YYYY-MM-DD` (any past local date) returns hourly metered/simulated energy, the night/morning/afternoon/evening split with the peak period, peak hour and top appliances, and per-appliance usage. `GET /api/insights/days?days=14` returns per-day totals for the day strip.

## Billing: tariff and projected bill

`app/services/billing_service.py` prices energy the way a utility bill does: a flat rate or rising **slabs** (cumulative kWh limits per cycle), a **fixed charge** per bill, **fuel adjustment** (₹/kWh) and **electricity duty** (% of energy + fuel charges). The **billing cycle** starts on the meter-reading day (`billingCycleDay`, 1 = calendar month). Set it in **Settings → Electricity tariff**.

* `GET /api/billing/bills/{id}/appliances` splits a recorded bill: the fixed charge on its own line, the rest across appliances by metered + simulated kWh in the bill period (its own dates, else the cycle starting in its month) at the bill's average usage rate, and unmeasured billed units as "rest of home". It also returns billed vs recorded kWh per day (`billedDailyKWh`, `recordedDailyKWh`, `variancePercent`; at least 6 recorded hours needed), which the Bill page uses instead of rated-watt estimates. The projection also returns `applianceCosts`.
* `GET/PUT /api/billing/tariff`, `POST /api/billing/estimate {"kwh": 250}` (itemised bill), and `GET /api/billing/projection`: cycle-to-date metered + simulated kWh and bill, the projected bill at the current pace (the last 24 h when under a day into the cycle), current slab and kWh left before the next one, budget status, and a confidence level.
* All cost estimates use the same model: the flat rate, or with slabs the blended variable rate at this cycle's projected usage. The budget's kWh is the inverse of the bill (fixed charge included).
* Budget conflicts and recommendations use this projection, so simulated appliances count. A bill whose amount is far from what the tariff predicts for its units is flagged, as is a budget below the fixed charge.
* The AI tools `get_bill_projection` and `get_tariff` expose it, and the AI snapshot includes the projected bill.

## SHEM AI (energy guide)

Set `GEMINI_API_KEY` and/or `GROQ_API_KEY` ([Groq](https://console.groq.com/keys)) in `.env`. Both are called through the OpenAI SDK; `AI_PRIMARY_PROVIDER` is tried first and the other provider takes over on any error (mid-stream too: the client gets `fallback` + `reset` events).

* **Tools (36)**: read everything (snapshot, telemetry, insights, inventory, bills, target, events, and read-only SQL over the whole DB via `query_database`, which uses a `mode=ro` connection plus an authorizer that permits SELECT only). Write tools reuse the REST validation: relay and appliance on/off, appliances, rooms, bills, target, and household settings. Every write goes to `ai_action_log` and is broadcast as an `ai_action` WebSocket event.
* **UI components**: the model embeds ```` ```shem-ui {json} ``` ```` blocks. The backend validates them (`app/ai/components.py`) and streams them as `component` events. Follow-ups come in a ```` ```shem-followups ``` ```` block, with rule-based ones as a fallback.
* **Conflicts** (`app/ai/conflicts.py`, rule-based): declared wattage vs measured power on the relay (e.g. 9 W declared, 480 W measured), load while the relay is OFF, implausible ratings, estimates vs meter, bill ₹/kWh vs tariff, duplicate bills, budget exceeded or at risk, device offline, voltage, invalid readings, and failed relay commands. A scan runs every 60 s and pushes `ai_conflict` events for new conflicts.
* **Daily insights**: after `AI_DAILY_INSIGHT_HOUR`, yesterday's briefing is generated: metric cards and an hourly chart built from facts, plus an LLM narrative. If no provider is available, a rule-based narrative is used. The result is pushed as an `ai_daily_insight` event.

### SHEM AI Live (voice)

Set `SARVAM_API_KEY`. The browser streams 16 kHz PCM16 audio over `wss://…/api/ai/voice/live?api_key=…`. The backend forwards it to Sarvam's realtime STT (Saaras, with VAD end-of-speech detection, language auto-detected). Each final transcript runs through the same Gemini/Groq agent and tools, in a short voice-friendly style in the detected language. The reply text is split into sentences and spoken with Bulbul TTS. UI components and tool events are forwarded unchanged, so they appear on screen while the AI talks.

* Utterances are answered one at a time, in order. Barge-in (`AI_VOICE_BARGE_IN`): if you start speaking while the AI is talking, its remaining speech is dropped, but that turn's tool actions and UI still finish.
* Live exchanges are saved to the same conversation as chat.
* The protocol is documented in `app/ai/voice.py`. One-shot helpers are `POST /api/ai/voice/transcribe` (raw audio body) and `POST /api/ai/voice/speak` (returns WAV).

Endpoints are under `/api/ai/*` (see `app/api/ai.py`). Streaming uses `POST /api/ai/chat/stream` (SSE over fetch).

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest                                   # 171 tests, ~12 s
python -m pytest --cov=app --cov-report=term-missing
```

Every test runs against a temporary SQLite file with a fake or mocked MQTT client. Nothing touches `shem.db`, EMQX, or the physical relay.

| Suite | Covers |
|---|---|
| `test_telemetry_device` | AC-only validation, DC/unknown-device/unit rejection, NaN → invalid, NULL PF/Hz, timestamps, online/offline/stale, retained status |
| `test_relay` | pending → published → applied, duplicate/late/rejected acks, timeout, broker-down 503, channel 1 only |
| `test_stream` | WS auth, snapshot, telemetry from the MQTT thread, heartbeat, relay_update, ping/pong, client cleanup |
| `test_crud` | household, rooms (delete keeps appliances), appliances, bills (sorted, validated), target |
| `test_insights` | measured-only trends, register resets, period comparison, today buckets, data-driven recommendations |
| `test_energy_retention` | register-delta rules, lossless hourly rollups, retention pruning, history downsampling |
| `test_security` | 401s, fail-closed empty key, rate limits per tunnel client, CORS |
| `test_mqtt_client` | TLS (CERT_REQUIRED), QoS 1 subscriptions, reconnect resubscribe, denied subscriptions, dispatch, publish rules, missing CA |
| `test_resilience` | **survives EMQX disconnect/reconnect**: health, REST availability, safe relay refusal, WS notifications, recovery |
| `test_contracts` | exact firmware payloads and every ack status; REST/WS responses vs `frontend/src/api/types.ts` |
| `test_hardening` | concurrent MQTT and API writes, timeout/stale pushes, slow/dead WS clients, DB errors contained |
| `test_ai` | SHEM AI: component stream parsing, read-only SQL guard, write tools + audit log, 9 W-vs-480 W conflict, tool loop, provider fallback, SSE events, daily insights, real SDK stream parsing (mocked HTTP) |
| `test_voice` | Live voice: sentence chunking and speech cleanup, full WS session with fake Sarvam (transcript, tools, UI, ordered audio, Hindi), interrupt, auth, REST voice endpoints, and the Sarvam REST/realtime wire format against local mocks |
| `test_simulation` | simulated appliances: power profiles, routine and override expiry, programme auto-off, energy integration, metered + simulated insights, any-date breakdown, day totals |
| `test_billing` | slab/fixed/fuel/duty maths and inverse, billing-cycle dates, tariff API validation, projection from metered + simulated energy, budget kWh, budget conflicts counting simulated appliances, bill check against the tariff model |
| `test_schema_migration` | automatic column upgrade, SPA vs API routing |

## API conventions

* Auth: `X-API-Key` header on everything except `GET /api/health`. The WebSocket uses `wss://…/api/stream?api_key=…`. An empty `API_KEY` means every request is refused.
* JSON keys are camelCase, with units spelled the way the frontend uses them: `totalKWh`, `monthlyBudgetINR`, `energyKWh`, `activePowerW`. Requests also accept snake_case.
* Times are UTC ISO 8601 (`2026-11-01T09:30:00Z`). Calendar logic ("today", weeks, months, hour of day) uses `TIMEZONE`.
* `POST /api/relay/1/command` returns **202** with `status: "published"`. The relay has only switched when the command reaches `applied`, which you'll see via `GET /api/relay/1/commands/{id}` or the `relay_update` WebSocket event.

### WebSocket events (`/api/stream`)

| type | when | data |
|---|---|---|
| `init_snapshot` | on connect | `deviceStatus`, `latestTelemetry`, `relayStatus`, `serverTime` |
| `telemetry` | every valid reading (~2 s) | reading incl. `loadActive` |
| `sim_update` | every 2 s | simulated appliances: state, `powerW`, mode, routine, `todayKWh`; `totalPowerW` |
| `device_status` | online/offline/stale changes, MQTT connect changes | device status |
| `relay_state` | ESP32 relay/state message | relay status |
| `relay_update` | ack received or command timed out | command lifecycle + `commandedState` |
| `heartbeat` | every 5 s | `serverTime`, `mqttConnected` |
| `pong` | reply to client text `ping` | `serverTime` |

## Data storage and retention

At 2 s intervals the ESP32 produces about 43,200 readings a day, which would be about 15.7 M rows a year. Storage is tiered:

| Table | Content | Kept |
|---|---|---|
| `telemetry` | raw readings | `RAW_TELEMETRY_RETENTION_DAYS` (7) |
| `telemetry_hourly` | one row per local hour: energy used, avg/min/max V, avg A, avg/max W, avg PF/Hz | indefinitely (~8,760 rows/yr) |
| `device_status_events`, finished `relay_commands` | event log | `EVENT_RETENTION_DAYS` (90) |

A background job runs every `MAINTENANCE_INTERVAL_SECONDS` (and once at startup). It rolls completed hours into `telemetry_hourly`, then prunes raw rows. Raw rows are only pruned once their hour has been rolled up, and the latest valid reading is always kept. Insights and `history?resolution=1h` read rollups and recent raw data together, so the retention boundary never shows up in the results.

**Energy maths:** the PZEM `energy` field is a cumulative register, so readings are never summed. Consumption is the register difference between consecutive readings. Float noise up to 10 Wh is ignored. A meter reset counts the energy since the reset. Steps that would need more than 26 kW are discarded as glitches.

`/api/telemetry/history` downsamples automatically (`resolution=auto`): raw for ≤ 30 min, 1-minute buckets for ≤ 6 h, 5-minute buckets for ≤ 48 h, hourly beyond that (up to 366 days).

## Remote access (Phase 10): Cloudflare Tunnel

1. Install `cloudflared` and keep `HOST=127.0.0.1` so nothing on the LAN can bypass the tunnel.
2. Quick test URL, which changes on every restart:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
   For a stable demo URL, create a named tunnel (`cloudflared tunnel login`, `cloudflared tunnel create shem`, then route a DNS name to it).
3. Add the frontend's HTTPS origin to `ALLOWED_ORIGINS` and restart the backend.
4. Consider `EXPOSE_DOCS=false` on the public URL.
5. Test checklist, on mobile data rather than Wi-Fi:
   - [ ] `https://<tunnel>/api/health` → `"status":"ok"`
   - [ ] `https://<tunnel>/api/bills` with `X-API-Key` → 200 (without it → 401)
   - [ ] `wss://<tunnel>/api/stream?api_key=…` → `init_snapshot`, then `telemetry` every ~2 s
   - [ ] `POST /api/relay/1/command {"state":"ON"}` → `relay_update` with `status:"applied"` and the relay switches
