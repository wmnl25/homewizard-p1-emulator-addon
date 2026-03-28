from flask import Flask, jsonify
import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf
import requests
import threading
import time
import logging
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

app = Flask(__name__)

# Disable default Flask/Werkzeug request logs to keep the CLI clean
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ==========================================
# MANAGE UNIQUE SERIAL NUMBER / MAC
# ==========================================
SERIAL_FILE = ".serial"

def get_or_create_serial():
    """Checks .env first, then the .serial file, otherwise auto-generates."""
    env_serial = os.getenv("DEVICE_SERIAL")
    if env_serial and env_serial.strip():
        return env_serial.strip().upper()
        
    if os.path.exists(SERIAL_FILE):
        with open(SERIAL_FILE, "r") as f:
            return f.read().strip()
            
    new_serial = uuid.uuid4().hex[:12].upper()
    with open(SERIAL_FILE, "w") as f:
        f.write(new_serial)
    return new_serial

DEVICE_SERIAL = get_or_create_serial()

# ==========================================
# HOME ASSISTANT CONFIGURATION
# ==========================================
HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() in ("true", "on", "1")

if not HA_TOKEN or not HA_URL:
    print("❌ ERROR: HA_URL or HA_TOKEN not found in the .env file!")
    exit(1)

# Dynamic sensor mapping based on .env configuration
SENSORS = {
    "import_t1": os.getenv("SENSOR_IMPORT_T1", "sensor.p1_energy_consumed_tariff_1"),
    "import_t2": os.getenv("SENSOR_IMPORT_T2", "sensor.p1_energy_consumed_tariff_2"),
    "export_t1": os.getenv("SENSOR_EXPORT_T1", "sensor.p1_energy_produced_tariff_1"),
    "export_t2": os.getenv("SENSOR_EXPORT_T2", "sensor.p1_energy_produced_tariff_2"),
    "active_power_consumed": os.getenv("SENSOR_POWER_CONSUMED", "sensor.p1_power_consumed"),
    "active_power_produced": os.getenv("SENSOR_POWER_PRODUCED", "sensor.p1_power_produced"),
    
    # Optional phase sensors
    "power_l1": os.getenv("SENSOR_POWER_L1", ""),
    "power_l2": os.getenv("SENSOR_POWER_L2", ""),
    "power_l3": os.getenv("SENSOR_POWER_L3", ""),
    "voltage_l1": os.getenv("SENSOR_VOLTAGE_L1", ""),
    "voltage_l2": os.getenv("SENSOR_VOLTAGE_L2", ""),
    "voltage_l3": os.getenv("SENSOR_VOLTAGE_L3", ""),
    "current_l1": os.getenv("SENSOR_CURRENT_L1", ""),
    "current_l2": os.getenv("SENSOR_CURRENT_L2", ""),
    "current_l3": os.getenv("SENSOR_CURRENT_L3", ""),
    
    # Optional boolean sensors
    "short_power_drop": os.getenv("SENSOR_SHORT_POWER_DROP", ""),
    "power_fail": os.getenv("SENSOR_POWER_FAIL", "")
}
# ==========================================

def get_ha_state(entity_id, default=0.0):
    """Fetches the current state of a specific sensor from Home Assistant."""
    if not entity_id:
        return default

    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            state = response.json().get("state")
            if state in ["unknown", "unavailable", None]:
                return default
            
            # Handle boolean requests specifically
            if isinstance(default, bool):
                return str(state).lower() in ["true", "on", "1", "yes"]
            
            # Try to cast to the same type as the default value (e.g., float)
            try:
                return type(default)(state)
            except ValueError:
                return default
        else:
            return default
    except Exception:
        return default

def gather_api_data():
    """Gathers all data from HA and applies fallbacks/calculations."""
    import_t1 = round(get_ha_state(SENSORS["import_t1"]), 3)
    import_t2 = round(get_ha_state(SENSORS["import_t2"]), 3)
    export_t1 = round(get_ha_state(SENSORS["export_t1"]), 3)
    export_t2 = round(get_ha_state(SENSORS["export_t2"]), 3)
    
    # Main power calculations (converting kW to W)
    power_consumed = int(round(get_ha_state(SENSORS["active_power_consumed"]) * 1000))
    power_produced = int(round(get_ha_state(SENSORS["active_power_produced"]) * 1000))
    netto_power = power_consumed - power_produced

    # Phase Power (fallback to putting all netto_power on L1 if L1 is not configured)
    p_l1 = int(round(get_ha_state(SENSORS["power_l1"]) * 1000)) if SENSORS["power_l1"] else netto_power
    p_l2 = int(round(get_ha_state(SENSORS["power_l2"]) * 1000)) if SENSORS["power_l2"] else 0
    p_l3 = int(round(get_ha_state(SENSORS["power_l3"]) * 1000)) if SENSORS["power_l3"] else 0

    # Phase Voltage (fallback to standard 230V if not configured)
    v_l1 = round(get_ha_state(SENSORS["voltage_l1"]), 1) if SENSORS["voltage_l1"] else 230.0
    v_l2 = round(get_ha_state(SENSORS["voltage_l2"]), 1) if SENSORS["voltage_l2"] else 230.0
    v_l3 = round(get_ha_state(SENSORS["voltage_l3"]), 1) if SENSORS["voltage_l3"] else 230.0

    # Phase Current (fallback to calculation P/V if not configured)
    c_l1 = round(get_ha_state(SENSORS["current_l1"]), 2) if SENSORS["current_l1"] else round(p_l1 / v_l1, 2)
    c_l2 = round(get_ha_state(SENSORS["current_l2"]), 2) if SENSORS["current_l2"] else (round(p_l2 / v_l2, 2) if p_l2 else 0)
    c_l3 = round(get_ha_state(SENSORS["current_l3"]), 2) if SENSORS["current_l3"] else (round(p_l3 / v_l3, 2) if p_l3 else 0)

    # Boolean failures
    short_drop = get_ha_state(SENSORS["short_power_drop"], default=False)
    power_fail = get_ha_state(SENSORS["power_fail"], default=False)

    return {
        "smr_version": 50,
        "meter_model": "Emulator AM550",
        "wifi_ssid": "SmartHome_Network",
        "wifi_strength": 85,
        "total_power_import_t1_kwh": import_t1,
        "total_power_import_t2_kwh": import_t2,
        "total_power_export_t1_kwh": export_t1,
        "total_power_export_t2_kwh": export_t2,
        "active_power_w": netto_power,
        "active_power_l1_w": p_l1,
        "active_power_l2_w": p_l2,
        "active_power_l3_w": p_l3,
        "active_voltage_l1_v": v_l1,
        "active_voltage_l2_v": v_l2,
        "active_voltage_l3_v": v_l3,
        "active_current_l1_a": c_l1,
        "active_current_l2_a": c_l2,
        "active_current_l3_a": c_l3,
        "any_short_power_drop": short_drop,
        "any_power_fail": power_fail
    }

def print_cli_updates():
    """Runs a loop to print live data to the CLI (only if DEBUG_MODE is enabled)."""
    while True:
        data = gather_api_data()

        print("\n" + "-"*35)
        print(f"🐛 DEBUG: LIVE DATA UPDATE ({time.strftime('%H:%M:%S')})")
        print("-"*35)
        print(f"Import T1: {data['total_power_import_t1_kwh']} kWh | T2: {data['total_power_import_t2_kwh']} kWh")
        print(f"Export T1: {data['total_power_export_t1_kwh']} kWh | T2: {data['total_power_export_t2_kwh']} kWh")
        print(f"Net Power: {data['active_power_w']} W")
        print(f"L1: {data['active_power_l1_w']} W | {data['active_voltage_l1_v']} V | {data['active_current_l1_a']} A")
        if data['active_power_l2_w'] != 0 or data['active_power_l3_w'] != 0:
            print(f"L2: {data['active_power_l2_w']} W | {data['active_voltage_l2_v']} V | {data['active_current_l2_a']} A")
            print(f"L3: {data['active_power_l3_w']} W | {data['active_voltage_l3_v']} V | {data['active_current_l3_a']} A")
        print("-"*35)
        
        time.sleep(10)

@app.route('/api', methods=['GET'])
def get_basic_info():
    """Endpoint for basic device discovery."""
    return jsonify({
        "product_type": "HWE-P1",
        "product_name": "P1 Meter Emulator",
        "serial": DEVICE_SERIAL,
        "firmware_version": "4.19",
        "api_version": "v1"
    })

@app.route('/api/v1/data', methods=['GET'])
def get_data():
    """Endpoint providing the actual meter readings and live power usage."""
    data = gather_api_data()
    return jsonify(data)

def get_local_ip():
    """Tricks the system into finding the active local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def setup_mdns(ip_address):
    """Sets up Zeroconf/mDNS broadcasting to mimic a real HomeWizard device."""
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    
    properties = {
        b'api_version': b'v1',
        b'product_name': b'P1 Meter Emulator',
        b'product_type': b'HWE-P1',
        b'serial': DEVICE_SERIAL.encode('utf-8')
    }

    info = ServiceInfo(
        "_hwenergy._tcp.local.",
        f"HWE-P1-{DEVICE_SERIAL}._hwenergy._tcp.local.",
        addresses=[socket.inet_aton(ip_address)],
        port=80,
        properties=properties,
        server=f"hwe-p1-{DEVICE_SERIAL.lower()}.local.",
    )

    zeroconf.register_service(info)
    return zeroconf, info

if __name__ == '__main__':
    local_ip = get_local_ip()
    
    display_mac = DEVICE_SERIAL.ljust(12, '0')[:12]
    mac_format = ':'.join(display_mac[i:i+2] for i in range(0, 12, 2))
    
    print("\n" + "="*45)
    print("🔌 HOMEWIZARD P1 EMULATOR STARTED")
    print("="*45)
    print(f"🌐 IP Address:    {local_ip}")
    print(f"🏷️  MAC Address:   {mac_format}")
    print(f"🔢 Serial Number: {DEVICE_SERIAL}")
    print(f"🚪 Port:          80")
    print(f"📡 mDNS (Local):  HWE-P1-{DEVICE_SERIAL}.local")
    
    if DEBUG_MODE:
        print("🐛 Debug Mode:    ON (Live updates visible)")
    else:
        print("🤫 Debug Mode:    OFF (Live updates hidden)")
    print("="*45 + "\n")

    zc, info = setup_mdns(local_ip)
    
    if DEBUG_MODE:
        updater_thread = threading.Thread(target=print_cli_updates, daemon=True)
        updater_thread.start()

    try:
        app.run(host='0.0.0.0', port=80)
    except OSError as e:
        print(f"\n❌ ERROR: Cannot start on port 80. Make sure no other script is using it ({e})")
        print("💡 Tip: Use 'sudo killall python3' on Linux/Mac to stop stuck scripts.")
    finally:
        print("\nShutting down mDNS gracefully...")
        try:
            zc.unregister_service(info)
            zc.close()
        except NameError:
            pass