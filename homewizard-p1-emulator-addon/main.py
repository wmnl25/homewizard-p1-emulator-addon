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
                return type(default)(state)
            except ValueError:
                return default
        else:
            print(f"⚠️ API ERROR for {entity_id}: HTTP {response.status_code}", flush=True)
            return default
    except Exception as e:
        print(f"🚨 NETWORK ERROR reaching HA for {entity_id}: {e}", flush=True)
        return default

def gather_api_data():
    import_t1 = round(get_ha_state("import_t1"), 3)
    import_t2 = round(get_ha_state("import_t2"), 3)
    export_t1 = round(get_ha_state("export_t1"), 3)
    export_t2 = round(get_ha_state("export_t2"), 3)
    
    power_consumed = int(round(get_ha_state("active_power_consumed") * 1000))
    power_produced = int(round(get_ha_state("active_power_produced") * 1000))
    netto_power = power_consumed - power_produced

    p_l1 = int(round(get_ha_state("power_l1") * 1000)) if options.get("power_l1") else netto_power
    p_l2 = int(round(get_ha_state("power_l2") * 1000)) if options.get("power_l2") else 0
    p_l3 = int(round(get_ha_state("power_l3") * 1000)) if options.get("power_l3") else 0

    v_l1 = round(get_ha_state("voltage_l1"), 1) if options.get("voltage_l1") else 230.0
    v_l2 = round(get_ha_state("voltage_l2"), 1) if options.get("voltage_l2") else 230.0
    v_l3 = round(get_ha_state("voltage_l3"), 1) if options.get("voltage_l3") else 230.0

    c_l1 = round(get_ha_state("current_l1"), 2) if options.get("current_l1") else round(p_l1 / v_l1, 2)
    c_l2 = round(get_ha_state("current_l2"), 2) if options.get("current_l2") else (round(p_l2 / v_l2, 2) if p_l2 else 0)
    c_l3 = round(get_ha_state("current_l3"), 2) if options.get("current_l3") else (round(p_l3 / v_l3, 2) if p_l3 else 0)

    short_drop = get_ha_state("short_power_drop", default=False)
    power_fail = get_ha_state("power_fail", default=False)

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
    while True:
        data = gather_api_data()
        print("\n" + "-"*35, flush=True)
        print(f"🐛 DEBUG: LIVE DATA UPDATE ({time.strftime('%H:%M:%S')})", flush=True)
        print("-"*35, flush=True)
        print(f"Import T1: {data['total_power_import_t1_kwh']} kWh | T2: {data['total_power_import_t2_kwh']} kWh", flush=True)
        print(f"Export T1: {data['total_power_export_t1_kwh']} kWh | T2: {data['total_power_export_t2_kwh']} kWh", flush=True)
        print(f"Net Power: {data['active_power_w']} W", flush=True)
        print(f"L1: {data['active_power_l1_w']} W | {data['active_voltage_l1_v']} V | {data['active_current_l1_a']} A", flush=True)
        if data['active_power_l2_w'] != 0 or data['active_power_l3_w'] != 0:
            print(f"L2: {data['active_power_l2_w']} W | {data['active_voltage_l2_v']} V | {data['active_current_l2_a']} A", flush=True)
            print(f"L3: {data['active_power_l3_w']} W | {data['active_voltage_l3_v']} V | {data['active_current_l3_a']} A", flush=True)
        print("-"*35, flush=True)
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

if __name__ == '__main__':
    local_ip = get_local_ip()
    display_mac = DEVICE_SERIAL.ljust(12, '0')[:12]
    mac_format = ':'.join(display_mac[i:i+2] for i in range(0, 12, 2))
    
    print("\n" + "="*45, flush=True)
    print("🔌 HOMEWIZARD P1 EMULATOR STARTED (HA ADD-ON)", flush=True)
    print("="*45, flush=True)
    print(f"🌐 IP Address:    {local_ip}", flush=True)
    print(f"🏷️  MAC Address:   {mac_format}", flush=True)
    print(f"🔢 Serial Number: {DEVICE_SERIAL}", flush=True)
    print(f"🚪 Port:          80", flush=True)
    print(f"📡 mDNS (Local):  HWE-P1-{DEVICE_SERIAL}.local", flush=True)
    
    if DEBUG_MODE:
        print("🐛 Debug Mode:    ON (Live updates visible in log)", flush=True)
    else:
        print("🤫 Debug Mode:    OFF (Live updates hidden)", flush=True)
    print("="*45 + "\n", flush=True)

    zc, info = setup_mdns(local_ip)
    
    if DEBUG_MODE:
        threading.Thread(target=print_cli_updates, daemon=True).start()

    try:
        app.run(host='0.0.0.0', port=80)
    finally:
        print("\nShutting down mDNS gracefully...", flush=True)
        zc.unregister_service(info)
        zc.close()