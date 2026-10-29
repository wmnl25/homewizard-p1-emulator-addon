# HomeWizard P1 Meter Emulator for Home Assistant (Add-on)

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-2.0.0-green.svg)](https://github.com/wmnl25/homewizard-p1-emulator-addon)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project emulates a physical **HomeWizard P1 Energy Meter** on your local network. It pulls real-time data from your **Home Assistant** sensors and serves HomeWizard Local API v1 and v2.

Perfect for feeding energy data into smart devices like the **Zendure SolarFlow / Hyper** or other systems that support HomeWizard P1 meters, without needing the actual hardware.

---

## ✨ Features

* **HomeWizard API-compatible endpoints:** Implements `/api`, `/api/v1/system`, `/api/v1/data`, and a DSMR-formatted `/api/v1/telegram`, including the API version and CORS response headers. Optional readings are included when their corresponding sensors are configured; emulator identity and some device details are synthetic.
* **Dual API support:** API v1 over HTTP and API v2 over HTTPS are served simultaneously. `api_mode` defaults to `v1`, so Home Assistant uses the legacy HTTP flow unless trusted TLS is configured and `v2` is selected. The add-on page's **Open Web UI** button opens pairing and device status; v2 provides bearer authorization, measurements, system, telegram, battery-control state, and WebSocket access.
* **Telegram-derived meter model:** Optionally configure a Home Assistant entity containing the raw DSMR/P1 telegram. Its original telegram is served unchanged, and its header supplies the meter model. If unavailable, the configurable meter-type header defaults to `/ISK5\2M550E-1013`.
* **TLS for Home Assistant v2:** The add-on mounts `/ssl`. Set `tls_certificate` and `tls_private_key` to a certificate chain trusted by Home Assistant and its matching key to use v2 pairing in the built-in integration. The generated self-signed certificate is only for direct test clients that explicitly trust it; Home Assistant's built-in v2 client rejects it. Reboot and identify actions are acknowledged, but cannot affect physical hardware. API v2 remains experimental; keep bearer tokens on trusted networks.
* **Comprehensive Data:** Supports 3-phase systems, T1-T4 tariffs, gas meters, grid quality (sags/swells/failures), and peak demand (capacity tariffs) when configured.
* **Auto-Discovery:** Uses **mDNS (Zeroconf)** to broadcast as `_hwenergy._tcp.local.`, making it instantly visible in the Zendure app.
* **Easy Configuration:** Enter Home Assistant sensor entity IDs in the add-on Configuration tab; optional sensor settings can be left blank.
* **Multi-Language Support:** Full translations for **English, Dutch, German, French, and Spanish**.
* **Smart Calculations:** Automatically calculates combined energy totals and estimates current from net power when a current sensor is not configured.
* **Persistent Identity:** Generates and saves a serial/MAC address to keep the emulator identity stable across restarts. API device and gas IDs are derived synthetic identifiers, not IDs from a physical meter.

---

## 🛠️ Installation

1. In Home Assistant, go to **Settings** -> **Add-ons** -> **Add-on Store**.
2. Click the **three dots** (top right) -> **Repositories**.
3. Add the URL: `https://github.com/wmnl25/homewizard-p1-emulator-addon`
4. Find **HomeWizard P1 Emulator** at the bottom and click **Install**.
5. Go to the **Configuration** tab and select your sensors.
6. Click **Start**.

---

## 📝 Configuration Options 

The add-on is pre-configured with standard Home Assistant P1 sensor names. You can adjust these in the **Configuration** tab. Empty fields are safely ignored, allowing you to emulate anything from a basic 1-phase setup to a complex 3-phase system with gas.

### 🔐 API v2 certificate setup for Home Assistant

Home Assistant's built-in HomeWizard integration validates the API v2 TLS chain. The add-on's generated self-signed certificate does **not** satisfy that validation. Keep `api_mode` set to `v1` (the default) to use the working v1 fallback, or configure a certificate signed by a CA trusted by Home Assistant before selecting `v2`.

One option is a Let's Encrypt certificate for a DNS name you control. On a Linux machine with Certbot and access to that domain's DNS, request one with a DNS challenge:

```sh
certbot certonly --manual --preferred-challenges dns --agree-tos \
  -m you@example.net -d ha.example.net
```

Follow Certbot's instructions to publish the required DNS TXT record. Copy the resulting `fullchain.pem` and `privkey.pem` into Home Assistant's `/ssl` directory (for example, using the Samba `ssl` share). In the add-on **Configuration** tab set:

| Option | Value |
| :--- | :--- |
| `api_mode` | `v2` |
| `tls_certificate` | `/ssl/fullchain.pem` |
| `tls_private_key` | `/ssl/privkey.pem` |

Save and restart the add-on. Then enable pairing from **Open Web UI** when Home Assistant asks for authorization. Both API versions remain served; `api_mode` controls which protocol Home Assistant discovers first. Do not use a self-signed certificate for this v2 pairing flow.

### 📄 Raw P1 Telegram and Meter Type
| Option | Description |
| :--- | :--- |
| `raw_telegram` | Optional Home Assistant entity containing the complete raw telegram in its state or an attribute. When available, the telegram endpoints return it unchanged and the meter model is parsed from its first line. |
| `meter_type` | Fallback telegram header when no valid raw telegram is available. Default: `/ISK5\2M550E-1013`. |

### ⚡ Core Sensors (Main Power)
| Option | Description |
| :--- | :--- |
| `active_power_consumed` | Current Total Power Usage (kW) |
| `active_power_produced` | Current Total Power Production (kW) |
| `import_t1` | Energy Consumed Tariff 1 (kWh) |
| `export_t1` | Energy Produced Tariff 1 (kWh) |

### 📈 Extended Tariffs (Optional)
| Option | Description |
| :--- | :--- |
| `import_t2` / `import_t3` / `import_t4` | Energy Consumed Tariffs 2, 3 & 4 (kWh) |
| `export_t2` / `export_t3` / `export_t4` | Energy Produced Tariffs 2, 3 & 4 (kWh) |

### 🔌 Advanced Phase Monitoring (Optional)
| Option | Description |
| :--- | :--- |
| `power_l1`, `power_l2`, `power_l3` | Per-phase active power (W) |
| `voltage_l1`, `voltage_l2`, `voltage_l3` | Per-phase active voltage (V) |
| `current_l1`, `current_l2`, `current_l3` | Per-phase active current (A) |
| `frequency` | Line frequency (Hz) |

### 🛑 Grid Quality & Failures (Optional)
| Option | Description |
| :--- | :--- |
| `power_fail` | Number of power failures detected (count) |
| `short_power_drop` | Number of long power failures detected (count) |
| `voltage_sag_l1`, `voltage_sag_l2`, `voltage_sag_l3` | Number of voltage sags per phase (count) |
| `voltage_swell_l1`, `voltage_swell_l2`, `voltage_swell_l3` | Number of voltage swells per phase (count) |

### 📊 Peak Demand / Capacity Tariff (Optional)
| Option | Description |
| :--- | :--- |
| `active_power_average` | Active average demand (W) |
| `monthly_power_peak` | Peak average demand this month (W) |
| `monthly_power_peak_timestamp` | Timestamp of peak demand (`YYMMDDhhmmss`) |

### 💡 External Devices (Optional)
| Option | Description |
| :--- | :--- |
| `total_gas` | Gas meter reading (m³) |
| `gas_timestamp` | Most recent gas update (`YYMMDDhhmmss`) |

### ⚙️ System Settings
* **`debug_mode`**: Enable to see live data updates in the logs (Default: `false`).
* **`device_serial`**: Unique 12-character hex string. If empty, a stable serial is auto-generated.

---

## ⚠️ Network Requirements

* The emulator **must** run on the same local network/VLAN as the Zendure Hub (or target app).
* **Port 80** must be available and not blocked by other webservers (like Nginx) on your Home Assistant instance.
* Discovery works via mDNS; ensure your network router allows multicast traffic.

---

## 🐛 Troubleshooting
* **Add-on won't start:** Check the logs. A Port 80 conflict is the most common issue.
* **Zendure app can't find it:** Phone and Emulator must be on the same WiFi network and VLAN during setup.
* **Data shows 0.0:** Verify that the selected sensors have a valid state in Home Assistant, and check that the Home Assistant internal API is accessible.
* **Amperage is wildly incorrect:** Ensure your `active_power_consumed` and `active_power_produced` sensors in HA are outputting in **kW** (the add-on multiplies by 1000 for the API).

## 📄 License
MIT License. Feel free to use, modify, and contribute!
