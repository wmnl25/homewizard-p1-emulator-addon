from flask import Flask, jsonify
import random
import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf
import time

app = Flask(__name__)

# Fictieve startwaardes
import_t1 = 15000.123
import_t2 = 12000.456
export_t1 = 3000.789
export_t2 = 1500.012

@app.route('/api', methods=['GET'])
def get_basic_info():
    return jsonify({
        "product_type": "HWE-P1",
        "product_name": "P1 Meter Emulator",
        "serial": "112233445566",
        "firmware_version": "4.19",
        "api_version": "v1"
    })

@app.route('/api/v1/data', methods=['GET'])
def get_data():
    global import_t1, import_t2, export_t1, export_t2
    
    current_power = random.randint(200, 600)
    import_t1 += (current_power / 3600000) * 10 

    return jsonify({
        "smr_version": 50,
        "meter_model": "Emulator AM550",
        "wifi_ssid": "Mijn_Smarthome_Netwerk",
        "wifi_strength": 85,
        "total_power_import_t1_kwh": round(import_t1, 3),
        "total_power_import_t2_kwh": round(import_t2, 3),
        "total_power_export_t1_kwh": round(export_t1, 3),
        "total_power_export_t2_kwh": round(export_t2, 3),
        "active_power_w": current_power,
        "active_power_l1_w": current_power,
        "active_power_l2_w": 0,
        "active_power_l3_w": 0,
        "active_voltage_l1_v": 230.5,
        "active_voltage_l2_v": 230.1,
        "active_voltage_l3_v": 229.8,
        "active_current_l1_a": round(current_power / 230.5, 2),
        "active_current_l2_a": 0,
        "active_current_l3_a": 0,
        "any_short_power_drop": False,
        "any_power_fail": False
    })

def get_local_ip():
    """Trucje om het actuele IP-adres van deze machine op het netwerk te vinden."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def setup_mdns():
    """Stelt de Zeroconf/mDNS broadcast in voor HomeWizard discovery."""
    ip_address = get_local_ip()
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    
    # Dit is de metadata die Zendure/Home Assistant zoekt tijdens het scannen
    properties = {
        b'api_version': b'v1',
        b'product_name': b'P1 Meter Emulator',
        b'product_type': b'HWE-P1',
        b'serial': b'112233445566'
    }

    info = ServiceInfo(
        "_hwenergy._tcp.local.",
        "HWE-P1-112233445566._hwenergy._tcp.local.",
        addresses=[socket.inet_aton(ip_address)],
        port=80,
        properties=properties,
        server="hwe-p1-112233445566.local.",
    )

    zeroconf.register_service(info)
    print(f"mDNS geactiveerd: De emulator zendt nu uit op IP {ip_address}...")
    return zeroconf, info

if __name__ == '__main__':
    zc, info = setup_mdns()
    try:
        print("Start webserver op poort 80...")
        # Start de Flask app. Blockt totdat je het script stopt (Ctrl+C)
        app.run(host='0.0.0.0', port=80)
    finally:
        # Zorg dat we netjes afsluiten op het netwerk als we het script stoppen
        print("Sluit mDNS netjes af...")
        zc.unregister_service(info)
        zc.close()