# HomeWizard P1 Meter Emulator for Home Assistant (Add-on)

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-1.0.14-green.svg)](https://github.com/wmnl25/homewizard-p1-emulator-addon)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project emulates a physical **HomeWizard P1 Energy Meter** on your local network. It pulls real-time data from your **Home Assistant** sensors and serves it via the official HomeWizard Local API (`v1`).

Perfect for feeding energy data into smart devices like the **Zendure SolarFlow / Hyper** or other systems that support HomeWizard P1 meters, without needing the actual hardware.

---

## ✨ Features

* **100% API Compliance:** Implements `/api`, `/api/v1/system`, and `/api/v1/data` endpoints matching the original hardware specifications.
* **Comprehensive Data:** Supports 3-phase systems, T1-T4 tariffs, gas meters, grid quality (sags/swells/failures), and peak demand (capacity tariffs).
* **Auto-Discovery:** Uses **mDNS (Zeroconf)** to broadcast as `_hwenergy._tcp.local.`, making it instantly visible in the Zendure app.
* **Easy Configuration:** Features **Entity Selectors** in the Home Assistant UI—simply select your sensors from dropdown menus.
* **Multi-Language Support:** Full translations for **English, Dutch, German, French, and Spanish**.
* **Smart Calculations:** Automatically calculates combined totals and Amperage (`A`) based on Wattage and Voltage if specific sensors are missing.
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

## 📝 Configuration Options 

The add-on is pre-configured with standard Home Assistant P1 sensor names. You can adjust these in the **Configuration** tab. Empty fields are safely ignored, allowing you to emulate anything from a basic 1-phase setup to a complex 3-phase system with gas.

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
* **`debug_mode`**: Enable to see live data updates and API requests in the logs (Default: `true`).
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