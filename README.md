# HomeWizard P1 Meter Emulator

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This project emulates a physical **HomeWizard P1 Energy Meter** on your local network. It pulls real-time data from **Home Assistant** and serves it via the official HomeWizard Local API (`v1`).

It is designed to feed energy data into smart devices like the **Zendure SolarFlow / Hyper** or other apps that natively support HomeWizard P1 meters, without requiring the actual hardware.

---

## ✨ Features

* **Full API Compliance:** Implements `/api` and `/api/v1/data` exactly like a real HomeWizard device.
* **Auto-Discovery:** Uses **mDNS (Zeroconf)** to broadcast itself as `_hwenergy._tcp.local.`, making it instantly visible to the Zendure app.
* **Flexible Mapping:** Map any Home Assistant sensor (Import, Export, Power per phase, Voltage, etc.) via configuration.
* **Smart Fallbacks:** Automatically calculates Amperage (`A`) based on Wattage and Voltage if sensors are missing.
* **Two Ways to Run:** Use it as a **standalone Python script** or a **native Home Assistant Add-on**.
* **Persistent Identity:** Generates a unique serial/MAC address and saves it to keep the device stable in your apps.

---

## 🛠️ Installation Options

### Option A: Home Assistant Add-on (Recommended)
The easiest way to use this project. It integrates directly with your HA instance.

1.  In Home Assistant, go to **Settings** -> **Add-ons** -> **Add-on Store**.
2.  Click the three dots (top right) -> **Repositories**.
3.  Add your repository URL: `https://github.com/wmnl25/homewizard-p1-emulator-addon`
4.  Find **HomeWizard P1 Emulator** at the bottom and click **Install**.
5.  Go to the **Configuration** tab, enter your sensor entity IDs, and click **Start**.

### Option B: Standalone Python Script
Ideal for running on a separate Raspberry Pi or server.

1.  **Install dependencies:**
    ```bash
    pip install flask requests zeroconf python-dotenv
    ```
2.  **Configure `.env`:** Create a `.env` file with your `HA_URL`, `HA_TOKEN`, and sensor names.
3.  **Run with sudo** (Required for Port 80):
    ```bash
    sudo python3 main.py
    ```

---

## ⚠️ Important: Network Topology
For the **Zendure SolarFlow/Hub** to work:
* The emulator **must** run on the same local network (VLAN/Subnet) as the Zendure Hub.
* When you add the meter in the Zendure app, the app sends the emulator's local IP to the Hub. The Hub then polls the emulator directly.
* **If the Hub and Emulator are in different locations/networks, data will stay at 0.**

---

## 📝 Configuration (Add-on)

| Option | Description |
| :--- | :--- |
| `debug_mode` | Show live data updates in the add-on logs. |
| `device_serial` | (Optional) Manually set a 12-char hex serial/MAC. |
| `import_t1` | Entity ID for Energy Consumed Tariff 1 (kWh). |
| `active_power_consumed` | Entity ID for Current Power Usage (kW or W). |
| `voltage_l1` | (Optional) Entity ID for Phase 1 Voltage (V). |

---

## 🐛 Troubleshooting
* **Logs show 0.0 values:** Ensure `homeassistant_api: true` is enabled (for Add-on users) and check if your entity IDs are typed correctly.
* **Port 80 Error:** Port 80 is required by the HomeWizard standard. Ensure no other webserver (like Nginx or Apache) is blocking the port.
* **Not found in app:** Ensure your phone is on the same 2.4GHz/5GHz WiFi as the device running the emulator.

## 📄 License
This project is licensed under the MIT License. Feel free to use and contribute!