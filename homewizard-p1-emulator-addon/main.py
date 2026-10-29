from flask import Flask, jsonify, request
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

@app.after_request
def add_api_headers(response):
    response.headers["X-Api-Version"] = "2.3.0"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

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
debug_setting = str(DEBUG_MODE).lower() == 'true'

if DEBUG_MODE:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.ERROR)
    
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
CLOUD_ENABLED = False

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
    # --- Energy Imports/Exports ---
    import_t1 = round(get_ha_state("import_t1"), 3)
    import_t2 = round(get_ha_state("import_t2"), 3) if options.get("import_t2") else 0.0
    import_t3 = round(get_ha_state("import_t3"), 3) if options.get("import_t3") else 0.0
    import_t4 = round(get_ha_state("import_t4"), 3) if options.get("import_t4") else 0.0
    
    export_t1 = round(get_ha_state("export_t1"), 3)
    export_t2 = round(get_ha_state("export_t2"), 3) if options.get("export_t2") else 0.0
    export_t3 = round(get_ha_state("export_t3"), 3) if options.get("export_t3") else 0.0
    export_t4 = round(get_ha_state("export_t4"), 3) if options.get("export_t4") else 0.0

    # --- Combined Totals (Required by API) ---
    total_import = import_t1 + import_t2 + import_t3 + import_t4
    total_export = export_t1 + export_t2 + export_t3 + export_t4

    # --- Total Power (Convert HA kW to API Watts) ---
    p_cons = get_ha_state("active_power_consumed")
    p_prod = get_ha_state("active_power_produced")
    
    # Multiply by 1000 to output W instead of kW
    power_consumed_w = int(round(p_cons * 1000))
    power_produced_w = int(round(p_prod * 1000))
    
    netto_power = power_consumed_w - power_produced_w
    active_current_l1 = get_ha_state("current_l1") if options.get("current_l1") else round(netto_power / 230.0, 2)

    # --- Build the Base Payload (Always Returned) ---
    data = {
        "smr_version": 50,
        "meter_model": "AM550",
        "unique_id": DEVICE_SERIAL.encode("ascii").hex().upper(),
        "wifi_ssid": "Home_Assistant",
        "wifi_strength": 100,
        "active_tariff": 2,
        
        "total_power_import_kwh": round(total_import, 3),
        "total_power_import_t1_kwh": import_t1,
        "total_power_import_t2_kwh": import_t2,
        
        "total_power_export_kwh": round(total_export, 3),
        "total_power_export_t1_kwh": export_t1,
        "total_power_export_t2_kwh": export_t2,
        
        "active_power_w": netto_power,
        
        # Fallback to calculated/hardcoded L1 values ONLY IF not provided in UI
        "active_power_l1_w": get_ha_state("power_l1") if options.get("power_l1") else netto_power,
        "active_voltage_l1_v": get_ha_state("voltage_l1") if options.get("voltage_l1") else 230.0,
        "active_current_a": active_current_l1,
        "active_current_l1_a": active_current_l1,
        "active_frequency_hz": get_ha_state("frequency") if options.get("frequency") else 50.0,
        
        # Correctly mapped power failure API keys
        "any_power_fail_count": int(get_ha_state("power_fail", default=0)),
        "long_power_fail_count": int(get_ha_state("short_power_drop", default=0))
    }

    # --- Conditionally Add T2/T3/T4 Tariffs ---
    if options.get("import_t3"): data["total_power_import_t3_kwh"] = import_t3
    if options.get("import_t4"): data["total_power_import_t4_kwh"] = import_t4
    if options.get("export_t3"): data["total_power_export_t3_kwh"] = export_t3
    if options.get("export_t4"): data["total_power_export_t4_kwh"] = export_t4

    # --- Conditionally Add L2/L3 (3-Phase Systems) ---
    if options.get("power_l2"): data["active_power_l2_w"] = get_ha_state("power_l2")
    if options.get("power_l3"): data["active_power_l3_w"] = get_ha_state("power_l3")
    if options.get("voltage_l2"): data["active_voltage_l2_v"] = get_ha_state("voltage_l2")
    if options.get("voltage_l3"): data["active_voltage_l3_v"] = get_ha_state("voltage_l3")
    if options.get("current_l2"): data["active_current_l2_a"] = get_ha_state("current_l2")
    if options.get("current_l3"): data["active_current_l3_a"] = get_ha_state("current_l3")

    # --- Conditionally Add Sags & Swells ---
    if options.get("voltage_sag_l1"): data["voltage_sag_l1_count"] = int(get_ha_state("voltage_sag_l1"))
    if options.get("voltage_sag_l2"): data["voltage_sag_l2_count"] = int(get_ha_state("voltage_sag_l2"))
    if options.get("voltage_sag_l3"): data["voltage_sag_l3_count"] = int(get_ha_state("voltage_sag_l3"))
    if options.get("voltage_swell_l1"): data["voltage_swell_l1_count"] = int(get_ha_state("voltage_swell_l1"))
    if options.get("voltage_swell_l2"): data["voltage_swell_l2_count"] = int(get_ha_state("voltage_swell_l2"))
    if options.get("voltage_swell_l3"): data["voltage_swell_l3_count"] = int(get_ha_state("voltage_swell_l3"))

    # --- Conditionally Add Peak Demand (Belgian Users) ---
    if options.get("active_power_average"): 
        data["active_power_average_w"] = get_ha_state("active_power_average")
    if options.get("monthly_power_peak"): 
        data["montly_power_peak_w"] = get_ha_state("monthly_power_peak")
    if options.get("monthly_power_peak_timestamp"): 
        data["montly_power_peak_timestamp"] = int(get_ha_state("monthly_power_peak_timestamp"))

    # --- Conditionally Add Gas Meter Data ---
    if options.get("total_gas"):
        gas_value = round(get_ha_state("total_gas"), 3)
        gas_timestamp = int(get_ha_state("gas_timestamp")) if options.get("gas_timestamp") else int(time.strftime("%y%m%d%H%M%S"))
        gas_unique_id = ("GAS" + DEVICE_SERIAL).encode("ascii").hex().upper()
        data["total_gas_m3"] = gas_value
        data["gas_timestamp"] = gas_timestamp
        data["gas_unique_id"] = gas_unique_id
        data["external"] = [{
            "unique_id": gas_unique_id,
            "type": "gas_meter",
            "timestamp": gas_timestamp,
            "value": gas_value,
            "unit": "m3"
        }]

    return data

def print_cli_updates():
    while True:
        data = gather_api_data()
        print(f"🐛 DEBUG [{time.strftime('%H:%M:%S')}]: Net Power: {data['active_power_w']}W", flush=True)
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

def format_p1_value(value, width=10, decimals=3):
    return f"{float(value):0{width}.{decimals}f}"

def calculate_dsmr_checksum(telegram):
    """Return the DSMR CRC-16 checksum for the telegram through its final '!'."""
    crc = 0
    for byte in telegram.encode("ascii"):
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return f"{crc:04X}"

@app.route('/api/v1/telegram', methods=['GET'])
def get_telegram():
    data = gather_api_data()

    meter_model = str(data.get("meter_model", "2M550E-1013"))
    if meter_model.upper().startswith("ISKRA "):
        meter_model = meter_model[6:]

    lines = [
        f"/ISK5\\{meter_model}",
        f"1-3:0.2.8({int(data.get('smr_version', 50))})",
        f"0-0:1.0.0({time.strftime('%y%m%d%H%M%S')}W)",
        f"0-0:96.1.1({data.get('unique_id', '')})",
        f"1-0:1.8.1({format_p1_value(data.get('total_power_import_t1_kwh', 0))}*kWh)",
        f"1-0:1.8.2({format_p1_value(data.get('total_power_import_t2_kwh', 0))}*kWh)",
        f"1-0:2.8.1({format_p1_value(data.get('total_power_export_t1_kwh', 0))}*kWh)",
        f"1-0:2.8.2({format_p1_value(data.get('total_power_export_t2_kwh', 0))}*kWh)",
        f"0-0:96.14.0({int(data.get('active_tariff', 0)):04d})",
    ]

    active_power_w = float(data.get("active_power_w", 0))
    phase_power_w = float(data.get("active_power_l1_w", active_power_w))
    lines.extend([
        f"1-0:1.7.0({format_p1_value(max(active_power_w, 0) / 1000, width=6)}*kW)",
        f"1-0:2.7.0({format_p1_value(max(-active_power_w, 0) / 1000, width=6)}*kW)",
        f"0-0:96.7.21({int(data.get('any_power_fail_count', 0)):05d})",
        f"0-0:96.7.9({int(data.get('long_power_fail_count', 0)):05d})",
        "1-0:99.97.0()",
        f"1-0:32.32.0({int(data.get('voltage_sag_l1_count', 0)):05d})",
        f"1-0:32.36.0({int(data.get('voltage_swell_l1_count', 0)):05d})",
        "0-0:96.13.0()",
        f"1-0:32.7.0({float(data.get('active_voltage_l1_v', 0)):.1f}*V)",
        f"1-0:31.7.0({int(abs(float(data.get('active_current_l1_a', data.get('active_current_a', 0)))) + 0.999999):03d}*A)",
        f"1-0:21.7.0({format_p1_value(max(phase_power_w, 0) / 1000, width=6)}*kW)",
        f"1-0:22.7.0({format_p1_value(max(-phase_power_w, 0) / 1000, width=6)}*kW)",
    ])

    external = data.get("external") or []
    gas_meter = next((item for item in external if item.get("type") == "gas_meter"), None)
    if gas_meter:
        gas_timestamp = int(gas_meter.get("timestamp", data.get("gas_timestamp", 0)))
        lines.extend([
            "0-1:24.1.0(003)",
            f"0-1:96.1.0({gas_meter.get('unique_id', data.get('gas_unique_id', ''))})",
            f"0-1:24.2.1({gas_timestamp:012d}W)({format_p1_value(gas_meter.get('value', data.get('total_gas_m3', 0)))}*m3)",
        ])

    telegram = "\r\n".join(lines) + "\r\n!"
    checksum = calculate_dsmr_checksum(telegram)
    return app.response_class(f"{telegram}{checksum}\r\n", mimetype="text/plain")

@app.route('/api/v1/system', methods=['GET', 'PUT'])
def system_state():
    global CLOUD_ENABLED
    
    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        if 'cloud_enabled' in data:
            CLOUD_ENABLED = bool(data['cloud_enabled'])
            if DEBUG_MODE:
                print(f"🐛 DEBUG: cloud_enabled updated to {CLOUD_ENABLED}", flush=True)
                
    return jsonify({
        "cloud_enabled": CLOUD_ENABLED
    })
    
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
    zeroconf.register_service(info, allow_name_change=True)
    return zeroconf, info

# ==========================================
# MAIN EXECUTION
# ==========================================
if __name__ == '__main__':
    local_ip = get_local_ip()
    
    display_mac = DEVICE_SERIAL.ljust(12, '0')[:12]
    mac_format = ':'.join(display_mac[i:i+2] for i in range(0, 12, 2))
    
    print("\n" + "="*45, flush=True)
    print("🔌 HOMEWIZARD P1 EMULATOR", flush=True)
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
        app.run(host='0.0.0.0', port=80, debug=debug_setting)
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
