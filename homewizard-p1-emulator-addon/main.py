from flask import Flask, jsonify
import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf
import requests
import threading
import time
import logging
import os
import uuid
import json
import sys

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ==========================================
# HOME ASSISTANT ADD-ON CONFIGURATION
# ==========================================
SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
OPTIONS_FILE = "/data/options.json"

try:
    with open(OPTIONS_FILE) as f:
        options = json.load(f)
except Exception as e:
    print(f"❌ ERROR: Could not load options: {e}", flush=True)
    options = {}

DEBUG_MODE = options.get("debug_mode", False)

# ==========================================
# MANAGE UNIQUE SERIAL NUMBER / MAC
# ==========================================
SERIAL_FILE = "/data/.serial"

def get_or_create_serial():
    env_serial = options.get("device_serial", "")
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
# LOGIC & DATA GATHERING
# ==========================================
def get_ha_state(entity_key, default=0.0):
    entity_id = options.get(entity_key)
    
    if not SUPERVISOR_TOKEN:
        print("❌ ERROR: SUPERVISOR_TOKEN is missing! Make sure 'homeassistant_api: true' is in config.yaml", flush=True)
        return default

    if not entity_id:
        return default

    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            state = response.json().get("state")
            if state in ["unknown", "unavailable", None]:
                if DEBUG_MODE:
                    print(f"⚠️ Sensor {entity_id} is temporarily '{state}'", flush=True)
                return default
            
            if isinstance(default, bool):
                return str(state).lower() in ["true", "on", "1", "yes"]
            
            try:
                val = float(state)
                return val
            except ValueError:
                return default
        else:
            return default
    except Exception:
        return default

def gather_api_data():
    import_t1 = round(get_ha_state("import_t1"), 3)
    import_t2 = round(get_ha_state("import_t2"), 3)
    export_t1 = round(get_ha_state("export_t1"), 3)
    export_t2 = round(get_ha_state("export_t2"), 3)
    
    p_cons = get_ha_state("active_power_consumed")
    p_prod = get_ha_state("active_power_produced")
    
    power_consumed = int(round(p_cons * 1000 if p_cons < 100 else p_cons))
    power_produced = int(round(p_prod * 1000 if p_prod < 100 else p_prod))
    netto_power = power_consumed - power_produced

    return {
        "smr_version": 50,
        "meter_model": "Emulator AM550",
        "wifi_ssid": "Home_Assistant",
        "wifi_strength": 100,
        "total_power_import_t1_kwh": import_t1,
        "total_power_import_t2_kwh": import_t2,
        "total_power_export_t1_kwh": export_t1,
        "total_power_export_t2_kwh": export_t2,
        "active_power_w": netto_power,
        "active_power_l1_w": netto_power,
        "active_voltage_l1_v": 230.0,
        "active_current_l1_a": round(netto_power / 230.0, 2)
    }

def print_cli_updates():
    while True:
        data = gather_api_data()
        print(f"🐛 DEBUG [{time.strftime('%H:%M:%S')}]: Net Power: {data['active_power_w']}W | Import: {data['total_power_import_t1_kwh']}kWh", flush=True)
        time.sleep(10)

@app.route('/api', methods=['GET'])
def get_basic_info():
    return jsonify({
        "product_type": "HWE-P1",
        "product_name": "P1 Meter Emulator",
        "serial": DEVICE_SERIAL,
        "firmware_version": "4.19",
        "api_version": "v1"
    })

@app.route('/api/v1/data', methods=['GET'])
def get_data():
    return jsonify(gather_api_data())

def get_local_ip():
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

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    local_ip = get_local_ip()
    
    display_mac = DEVICE_SERIAL.ljust(12, '0')[:12]
    mac_format = ':'.join(display_mac[i:i+2] for i in range(0, 12, 2))
    
    print("\n" + "="*45, flush=True)
    print("🔌 HOMEWIZARD P1 EMULATOR (v1.0.7)", flush=True)
    print("="*45, flush=True)
    print(f"🌐 IP Address:    {local_ip}", flush=True)
    print(f"🏷️  MAC Address:   {mac_format}", flush=True)
    print(f"🔢 Serial Number: {DEVICE_SERIAL}", flush=True)
    print(f"🚪 Port:          80", flush=True)
    print(f"📡 mDNS (Local):  HWE-P1-{DEVICE_SERIAL}.local", flush=True)

    if DEBUG_MODE:
        print("🐛 Debug Mode:    ON (Live updates visible)", flush=True)
    else:
        print("🤫 Debug Mode:    OFF", flush=True)
    print("="*45 + "\n", flush=True)
    
    zc, info = setup_mdns(local_ip)
    
    if DEBUG_MODE:
        threading.Thread(target=print_cli_updates, daemon=True).start()

    try:
        app.run(host='0.0.0.0', port=80, debug=False)
    except OSError as e:
        if e.errno == 98 or e.errno == 48:
            print("\n" + "!"*45, flush=True)
            print("❌ CRITICAL ERROR: PORT 80 IS ALREADY IN USE!", flush=True)
            print("This usually means Nginx or another webserver", flush=True)
            print("is already running on this Home Assistant IP.", flush=True)
            print("!"*45 + "\n", flush=True)
        else:
            print(f"❌ ERROR: Could not start server: {e}", flush=True)
    finally:
        print("Stopping mDNS advertiser...", flush=True)
        zc.unregister_service(info)
        zc.close()
        sys.exit(1 if 'e' in locals() else 0)