# HomeWizard P1 Meter Emulator for Home Assistant (Add-on)

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.0.5-green.svg)](https://github.com/wmnl25/homewizard-p1-emulator-addon)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project emulates a physical **HomeWizard P1 Energy Meter** on your local network. It pulls real-time data from your **Home Assistant** sensors and serves it via the official HomeWizard Local API (`v1`).

Perfect for feeding energy data into smart devices like the **Zendure SolarFlow / Hyper** or other systems that support HomeWizard P1 meters, without needing the actual hardware.

---

## ✨ Features (v1.0.5)

* **Full API Compliance:** Implements `/api` and `/api/v1/data` exactly like the original hardware.
* **Auto-Discovery:** Uses **mDNS (Zeroconf)** to broadcast as `_hwenergy._tcp.local.`, making it instantly visible in the Zendure app.
* **Easy Configuration:** Features **Entity Selectors** in the Home Assistant UI—simply select your sensors from dropdown menus.
* **Multi-Language Support:** Full translations for **English, Dutch, German, French, and Spanish**.
* **Smart Calculations:** Automatically calculates Amperage (`A`) based on Wattage and Voltage if specific sensors are missing.
* **Persistent Identity:** Generates and saves a unique serial/MAC address to keep the device stable in your apps.

---

## 🛠️ Installation

1. In Home Assistant, go to **Settings** -> **Add-ons** -> **Add-on Store**.
2. Click the **three dots** (top right) -> **Repositories**.
3. Add the URL: `https://github.com/wmnl25/homewizard-p1-emulator-addon`
4. Find **HomeWizard P1 Emulator** at the bottom and click **Install**.
5. Go to the **Configuration** tab and select your sensors.
6. Click **Start**.

---

## 📝 Configuration Options (v1.0.5)

The add-on is pre-configured with standard Home Assistant P1 sensor names. You can adjust these in the **Configuration** tab.

### ⚡ Core Sensors (Main Power)
| Option | Description | Default Entity ID |
| :--- | :--- | :--- |
| `active_power_consumed` | Current Total Power Usage (W or kW) | `sensor.p1_power_consumed` |
| `active_power_produced` | Current Total Power Production (W or kW) | `sensor.p1_power_produced` |
| `import_t1` | Energy Consumed Tariff 1 (kWh) | `sensor.p1_energy_consumed_tariff_1` |
| `import_t2` | Energy Consumed Tariff 2 (kWh) | `sensor.p1_energy_consumed_tariff_2` |
| `export_t1` | Energy Produced Tariff 1 (kWh) | `sensor.p1_energy_produced_tariff_1` |
| `export_t2` | Energy Produced Tariff 2 (kWh) | `sensor.p1_energy_produced_tariff_2` |

### 🔌 Advanced Phase Monitoring (Optional)
If these sensors are provided, the emulator serves detailed per-phase data.
* **Power (W/kW):** `power_l1`, `power_l2`, `power_l3`
* **Voltage (V):** `voltage_l1`, `voltage_l2`, `voltage_l3`
* **Current (A):** `current_l1`, `current_l2`, `current_l3`

### ⚙️ System Settings
* **`debug_mode`**: Enable to see live data updates and API requests in the logs (Default: `true`).
* **`device_serial`**: Unique 12-character hex string. If empty, a stable serial is auto-generated.

---

## ⚠️ Network Requirements

* The emulator **must** run on the same local network/VLAN as the Zendure Hub.
* **Port 80** must be available and not blocked by other webservers.
* Discovery works via mDNS; ensure your network allows multicast traffic.

---

## 🐛 Troubleshooting
* **Add-on won't start:** Check the logs.
* **Zendure app can't find it:** Phone and Emulator must be on the same WiFi network during setup.
* **Data shows 0.0:** Verify that the selected sensors have a valid state in Home Assistant.

## 📄 License
MIT License. Feel free to use, modify, and contribute!