# HomeWizard P1 Meter Emulator for Home Assistant

This project is a lightweight Python-based emulator that mimics a physical **HomeWizard P1 Energy Meter** on your local network. It acts as a bridge, pulling live energy data from your **Home Assistant** instance and broadcasting it via the official HomeWizard Local API standards.

This is especially useful if you want to feed real-time energy consumption and solar production data into smart home battery systems (like **Zendure SolarFlow / Hyper**) or other apps that natively support HomeWizard P1 meters, without actually needing to buy the physical hardware.

## ✨ Features
* **100% HomeWizard Local API Compliant:** Endpoints and data formatting strictly follow the official HomeWizard `v1` API documentation.
* **mDNS / Zeroconf Discovery:** Automatically broadcasts itself on the network as `_hwenergy._tcp.local.`, making it instantly discoverable by the Zendure app and Home Assistant.
* **Persistent MAC / Serial:** Auto-generates and saves a unique serial number so your apps don't think it's a new device after every reboot (can also be manually overridden).
* **Fully Customizable:** Map any of your existing Home Assistant sensors (Import, Export, Power, Voltage, Phases) via a simple `.env` file.
* **Smart Fallbacks:** Automatically calculates missing values (like Current `A` based on Power and Voltage) if you don't have sensors for them.
* **Live CLI Debugger:** Real-time terminal output to monitor exactly what data is being pulled and served.

## ⚠️ Important Note on Network Topology
If you are using this to feed data to a local device (like a Zendure battery hub), **this script must run on the exact same Local Network / VLAN as the battery hub itself.** When you add the emulator via the app, the app simply passes the local IP address to the hub. The hub then takes over the polling. If the emulator runs at your house, but the battery hub is at another location (or isolated VLAN), the data will remain at `0`.

## ⚙️ Prerequisites
* Python 3.7+
* A Home Assistant instance accessible over the network.
* A Home Assistant **Long-Lived Access Token** (Create one in HA: *Profile -> Security -> Long-Lived Access Tokens*).

## 🚀 Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/homewizard-p1-emulator.git](https://github.com/YOUR_USERNAME/homewizard-p1-emulator.git)
   cd homewizard-p1-emulator
   ```

2. **Install the required Python packages:**
   ```bash
   pip install flask requests zeroconf python-dotenv
   ```

3. **Configure the Environment:**
   Create a `.env` file in the root directory and configure your Home Assistant details and sensor entities.

   **Example `.env` file:**
   ```env
   # Home Assistant Connection
   HA_URL="[http://192.168.1.100:8123](http://192.168.1.100:8123)"
   HA_TOKEN="eyJhbGciOiJIUz...YOUR_LONG_TOKEN_HERE"
   DEBUG_MODE="true"

   # Optional: Force a specific MAC/Serial (leave empty to auto-generate)
   # DEVICE_SERIAL="AABBCCDDEEFF" 

   # Main Energy Sensors (kWh)
   SENSOR_IMPORT_T1="sensor.energy_consumed_tariff_1"
   SENSOR_IMPORT_T2="sensor.energy_consumed_tariff_2"
   SENSOR_EXPORT_T1="sensor.energy_produced_tariff_1"
   SENSOR_EXPORT_T2="sensor.energy_produced_tariff_2"

   # Main Power Sensors (kW or W depending on your HA setup, the script converts to W)
   SENSOR_POWER_CONSUMED="sensor.power_consumed"
   SENSOR_POWER_PRODUCED="sensor.power_produced"

   # OPTIONAL: Phase specific sensors (Leave commented if you don't have them)
   # SENSOR_POWER_L1="sensor.power_l1"
   # SENSOR_VOLTAGE_L1="sensor.voltage_l1"
   # SENSOR_CURRENT_L1="sensor.current_l1"
   ```

## 🏃‍♂️ Running the Emulator

Most third-party apps (like Zendure) strictly expect the HomeWizard API to be available on **Port 80**. On Linux/macOS, binding to port 80 requires root privileges.

Run the script using `sudo`:
   ```bash
   sudo python3 main.py
   ```

You should see a startup screen displaying your Emulator's IP, generated MAC address, and active port. If `DEBUG_MODE="true"` is set in your `.env` file, you will also see live data updates every 10 seconds.

## 🛠️ Troubleshooting
* **`OSError: [Errno 48] Address already in use`**: This means another service (like Apache, Nginx, or a previously crashed instance of this script) is already using Port 80. You need to stop that service or kill the old Python process (`sudo killall python3`) before starting the emulator.
* **App finds the meter but shows 0W**: Ensure the device running this Python script allows inbound traffic on port 80 in its firewall, and is on the exact same local network as the requesting hardware (see Network Topology note).

## 📄 License
This project is open-source and available under the MIT License. Feel free to fork, modify, and improve!