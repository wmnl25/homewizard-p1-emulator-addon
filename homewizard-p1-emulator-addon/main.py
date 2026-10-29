from flask import Flask, jsonify, request, render_template_string, session, send_file, url_for
from flask_sock import Sock
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
import hashlib
import hmac
import re
import secrets
import subprocess
from werkzeug.serving import make_server
from datetime import datetime

API_V2_VERSION = "2.3.0"
DEFAULT_METER_TYPE = "/ISK5\\2M550E-1013"
app = Flask(__name__)
sock = Sock(app)
app.secret_key = os.getenv("UI_SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

class HomeAssistantIngressMiddleware:
    """Preserve the Supervisor ingress prefix when generating UI links."""
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        ingress_path = environ.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            environ["SCRIPT_NAME"] = ingress_path
        return self.wsgi_app(environ, start_response)

app.wsgi_app = HomeAssistantIngressMiddleware(app.wsgi_app)
log = logging.getLogger('werkzeug')

@app.after_request
def add_api_headers(response):
    is_v2 = request.path in {"/api", "/api/user", "/api/measurement", "/api/system", "/api/system/identify", "/api/system/reboot", "/api/telegram", "/api/batteries"} and request.headers.get("X-Api-Version", "").startswith("2")
    response.headers["X-Api-Version"] = API_V2_VERSION
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Api-Version"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

# ==========================================
# HOME ASSISTANT ADD-ON CONFIGURATION
# ==========================================
SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
HA_URL = "http://supervisor/core"
OPTIONS_FILE = os.getenv("OPTIONS_FILE", "/data/options.json")

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
SERIAL_FILE = os.getenv("SERIAL_FILE", "/data/.serial")

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
API_MODE = str(options.get("api_mode", "v1")).lower()
if API_MODE not in {"v1", "v2"}:
    API_MODE = "v1"
API_V1_ENABLED = True
V2_USERS_FILE = options.get("api_v2_users_file", "/data/.api_v2_users.json")
CUSTOM_TLS_CERT_FILE = str(options.get("tls_certificate") or "").strip()
CUSTOM_TLS_KEY_FILE = str(options.get("tls_private_key") or "").strip()
TLS_CERT_FILE = CUSTOM_TLS_CERT_FILE or os.getenv("TLS_CERT_FILE", "/data/.api_v2_certificate.pem")
TLS_KEY_FILE = CUSTOM_TLS_KEY_FILE or os.getenv("TLS_KEY_FILE", "/data/.api_v2_private_key.pem")
USE_CUSTOM_TLS_CERTIFICATE = bool(CUSTOM_TLS_CERT_FILE or CUSTOM_TLS_KEY_FILE)
TLS_CERT_IP_FILE = f"{TLS_CERT_FILE}.ip"
BATTERY_MODE = "zero"
BATTERY_PERMISSIONS = ["charge_allowed", "discharge_allowed"]
BATTERY_CHARGE_TO_FULL = False
PAIRING_WINDOW_SECONDS = 120
PAIRING_UNTIL = 0.0
PAIRING_LOCK = threading.Lock()
USERS_LOCK = threading.Lock()
STARTED_AT = time.monotonic()

def read_v2_users():
    try:
        with open(V2_USERS_FILE, "r", encoding="utf-8") as users_file:
            loaded = json.load(users_file)
            return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}

V2_USERS = read_v2_users()

def save_v2_users(users):
    directory = os.path.dirname(V2_USERS_FILE)
    try:
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary_file = f"{V2_USERS_FILE}.tmp"
        with open(temporary_file, "w", encoding="utf-8") as users_file:
            json.dump(users, users_file)
        os.replace(temporary_file, V2_USERS_FILE)
        return True
    except OSError as error:
        if DEBUG_MODE:
            print(f"Could not persist API v2 users: {error}", flush=True)
        return False

def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def v2_user_for_token(token):
    if not isinstance(token, str) or not token:
        return None
    digest = token_digest(token)
    with USERS_LOCK:
        users = dict(V2_USERS)
    for name, stored_digest in users.items():
        if hmac.compare_digest(digest, str(stored_digest)):
            return name
    return None

def authenticated_v2_user():
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return v2_user_for_token(token)

@app.before_request
def protect_api_v2():
    path = request.path
    api_version_header = request.headers.get("X-Api-Version")
    is_v2_request = bool(api_version_header and api_version_header.startswith("2"))
    if path.startswith("/api/v1/"):
        if not API_V1_ENABLED:
            return jsonify({"error": "api:disabled"}), 404
        return None
    if path == "/api" and not is_v2_request:
        # The HA integration probes HTTPS /api without headers and identifies
        # API v2 by its expected 401. Plain HTTP /api remains the v1 entry point.
        if request.is_secure:
            if authenticated_v2_user():
                return None
            if API_MODE == "v2":
                return jsonify({"error": "user:unauthorized"}), 401
            return jsonify({"error": "api:v1-preferred"}), 404
        if request.headers.get("Authorization"):
            return jsonify({"error": "request:https-required"}), 426
        if API_V1_ENABLED:
            return None
        return jsonify({"error": "api:disabled"}), 404
    v2_path = path in {"/api", "/api/user", "/api/measurement", "/api/system", "/api/system/identify", "/api/system/reboot", "/api/telegram", "/api/batteries"}
    if not v2_path:
        return None
    if request.method == "OPTIONS":
        return None
    if api_version_header and not is_v2_request:
        return jsonify({"error": "request:api-version-not-supported"}), 400
    if not request.is_secure:
        return jsonify({"error": "request:https-required"}), 426
    if request.path == "/api/user" and request.method == "POST":
        return None
    if not authenticated_v2_user():
        return jsonify({"error": "user:unauthorized"}), 401
    return None

def api_v2_error(message, status):
    return jsonify({"error": message}), status

def timestamp_to_iso(value):
    if value is None or value == "":
        return None
    text = str(value)
    if re.fullmatch(r"\d{14}", text):
        try:
            return datetime.strptime(text, "%Y%m%d%H%M%S").isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"\d{12}", text):
        try:
            return datetime.strptime(text, "%y%m%d%H%M%S").isoformat()
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text).replace(microsecond=0).isoformat()
    except ValueError:
        return None

def get_v2_measurement():
    source = gather_api_data()
    measurement = {
        "unique_id": source.get("unique_id"),
        "protocol_version": source.get("smr_version"),
        "meter_model": source.get("meter_model"),
        "timestamp": datetime.now().replace(microsecond=0).isoformat(),
        "tariff": source.get("active_tariff"),
    }
    fields = {
        "energy_import_kwh": "total_power_import_kwh",
        "energy_import_t1_kwh": "total_power_import_t1_kwh",
        "energy_import_t2_kwh": "total_power_import_t2_kwh",
        "energy_import_t3_kwh": "total_power_import_t3_kwh",
        "energy_import_t4_kwh": "total_power_import_t4_kwh",
        "energy_export_kwh": "total_power_export_kwh",
        "energy_export_t1_kwh": "total_power_export_t1_kwh",
        "energy_export_t2_kwh": "total_power_export_t2_kwh",
        "energy_export_t3_kwh": "total_power_export_t3_kwh",
        "energy_export_t4_kwh": "total_power_export_t4_kwh",
        "power_w": "active_power_w",
        "power_l1_w": "active_power_l1_w",
        "power_l2_w": "active_power_l2_w",
        "power_l3_w": "active_power_l3_w",
        "voltage_l1_v": "active_voltage_l1_v",
        "voltage_l2_v": "active_voltage_l2_v",
        "voltage_l3_v": "active_voltage_l3_v",
        "current_a": "active_current_a",
        "current_l1_a": "active_current_l1_a",
        "current_l2_a": "active_current_l2_a",
        "current_l3_a": "active_current_l3_a",
        "frequency_hz": "active_frequency_hz",
        "voltage_sag_l1_count": "voltage_sag_l1_count",
        "voltage_sag_l2_count": "voltage_sag_l2_count",
        "voltage_sag_l3_count": "voltage_sag_l3_count",
        "voltage_swell_l1_count": "voltage_swell_l1_count",
        "voltage_swell_l2_count": "voltage_swell_l2_count",
        "voltage_swell_l3_count": "voltage_swell_l3_count",
        "any_power_fail_count": "any_power_fail_count",
        "long_power_fail_count": "long_power_fail_count",
        "average_power_15m_w": "active_power_average_w",
        "monthly_power_peak_w": "montly_power_peak_w",
    }
    for target, key in fields.items():
        if key in source:
            measurement[target] = source[key]
    if "current_a" in measurement:
        measurement["current_a"] = abs(float(measurement["current_a"]))
    peak_timestamp = timestamp_to_iso(source.get("montly_power_peak_timestamp"))
    if peak_timestamp:
        measurement["monthly_power_peak_timestamp"] = peak_timestamp
    external = []
    for item in source.get("external") or []:
        converted = dict(item)
        converted["timestamp"] = timestamp_to_iso(item.get("timestamp")) or datetime.now().replace(microsecond=0).isoformat()
        external.append(converted)
    if external:
        measurement["external"] = external
    return measurement

def get_v2_system():
    data = gather_api_data()
    wifi_strength = float(data.get("wifi_strength", 0))
    result = {
        "wifi_ssid": data.get("wifi_ssid", ""),
        "wifi_rssi_db": round(-100 + wifi_strength * 0.5),
        "uptime_s": max(0, int(time.monotonic() - STARTED_AT)),
        "cloud_enabled": CLOUD_ENABLED,
        "status_led_brightness_pct": int(options.get("status_led_brightness_pct", 100)),
        "api_v1_enabled": API_V1_ENABLED,
    }
    return result

PAIRING_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HomeWizard P1 Emulator</title>
<style>
body{font:16px system-ui,sans-serif;background:#f3f6fa;color:#192538;margin:0;padding:2rem}
main{max-width:820px;margin:auto}.card{background:white;border-radius:14px;padding:1.4rem;margin:1rem 0;box-shadow:0 3px 16px #172b4d12}
h1{margin-bottom:.2rem}.muted{color:#627086}.status{font-weight:700}.on{color:#087443}.off{color:#8c3b28}
button{border:0;border-radius:8px;padding:.75rem 1rem;background:#0866d6;color:white;font-weight:700;cursor:pointer}
button.secondary{background:#586579}dt{font-weight:650}dd{margin:0 0 .8rem}code{background:#eef2f7;padding:.15rem .35rem;border-radius:4px}
</style></head><body><main>
<h1>HomeWizard P1 Emulator</h1><p class="muted">Local device status and API v2 pairing controls</p>
<section class="card"><h2>Pairing mode</h2>
<p class="status {{ 'on' if pairing_active else 'off' }}">{{ 'Enabled' if pairing_active else 'Disabled' }}{% if pairing_active %} — {{ pairing_seconds }} seconds remaining{% endif %}</p>
<p>Enable pairing before an app sends <code>POST /api/user</code>. Pairing automatically closes after {{ pairing_window }} seconds. The generated API token is returned only to the requesting client and is never shown here. Both API v1 and v2 remain available.</p>
<form method="post" action="{{ url_for('set_pairing_mode') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="enabled" value="1"><button type="submit">Enable pairing for {{ pairing_window }} seconds</button></form>
<form method="post" action="{{ url_for('set_pairing_mode') }}" style="margin-top:.6rem"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="enabled" value="0"><button class="secondary" type="submit">Disable pairing</button></form></section>
<section class="card"><h2>Device</h2><dl><dt>Serial</dt><dd>{{ serial }}</dd><dt>Meter model</dt><dd>{{ meter_model }}</dd><dt>API support</dt><dd>v1 and v2 ({{ api_v2_version }})</dd><dt>Home Assistant discovery preference</dt><dd>{{ api_mode }}</dd><dt>API v1 enabled</dt><dd>{{ 'Yes' if api_v1_enabled else 'No' }}</dd><dt>Registered API v2 users</dt><dd>{{ user_count }}</dd><dt>Uptime</dt><dd>{{ uptime_s }} seconds</dd></dl></section>
<section class="card"><h2>Latest measurement summary</h2><dl><dt>Net power</dt><dd>{{ power_w }} W</dd><dt>Energy import</dt><dd>{{ energy_import }} kWh</dd><dt>Energy export</dt><dd>{{ energy_export }} kWh</dd><dt>Gas</dt><dd>{{ gas_reading }}</dd></dl></section>
<p class="muted">API v2 uses HTTPS on port 443. {% if custom_tls_certificate %}The configured TLS certificate is active.{% else %}A certificate was generated automatically.{% endif %} <a href="{{ url_for('download_tls_certificate') }}">Download the server certificate</a>. Keep bearer tokens private.</p>
</main></body></html>"""

@app.get("/")
def pairing_ui():
    csrf_token = session.setdefault("ui_csrf_token", secrets.token_urlsafe(24))
    data = gather_api_data()
    with PAIRING_LOCK:
        remaining = max(0, int(PAIRING_UNTIL - time.monotonic()))
    with USERS_LOCK:
        user_count = len(V2_USERS)
    gas = data.get("total_gas_m3")
    return render_template_string(
        PAIRING_PAGE,
        csrf_token=csrf_token,
        pairing_active=remaining > 0,
        pairing_seconds=remaining,
        pairing_window=PAIRING_WINDOW_SECONDS,
        serial=DEVICE_SERIAL,
        meter_model=data.get("meter_model", "Unknown"),
        api_mode=API_MODE,
        api_v2_version=API_V2_VERSION,
        custom_tls_certificate=USE_CUSTOM_TLS_CERTIFICATE,
        api_v1_enabled=API_V1_ENABLED,
        user_count=user_count,
        uptime_s=max(0, int(time.monotonic() - STARTED_AT)),
        power_w=data.get("active_power_w", 0),
        energy_import=data.get("total_power_import_kwh", 0),
        energy_export=data.get("total_power_export_kwh", 0),
        gas_reading=f"{gas} m³" if gas is not None else "Not configured",
    )

@app.post("/ui/pairing")
def set_pairing_mode():
    expected = session.get("ui_csrf_token")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return "Invalid or expired UI session", 403
    global PAIRING_UNTIL
    with PAIRING_LOCK:
        PAIRING_UNTIL = time.monotonic() + PAIRING_WINDOW_SECONDS if request.form.get("enabled") == "1" else 0.0
    return pairing_ui()

@app.get("/certificate.pem")
def download_tls_certificate():
    if not os.path.isfile(TLS_CERT_FILE):
        return "TLS certificate is not available", 503
    return send_file(
        TLS_CERT_FILE,
        mimetype="application/x-pem-file",
        as_attachment=True,
        download_name="p1-emulator-certificate.pem",
    )

@app.route("/api/user", methods=["GET", "POST", "DELETE"])
def api_v2_users():
    global PAIRING_UNTIL
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return api_v2_error("request:invalid-json", 400)
        name = payload.get("name")
        if not isinstance(name, str):
            return api_v2_error("json:parameter-invalid-type:name", 400)
        if not name:
            return api_v2_error("user:name-empty", 400)
        if name.startswith("local/") and len(name[6:]) > 40:
            return api_v2_error("user:name-too-long", 400)
        if not re.fullmatch(r"local/[A-Za-z0-9\-_/\\# ]{1,40}", name):
            return api_v2_error("user:name-invalid" if name.startswith("local/") else "user:invalid-prefix", 400)
        with PAIRING_LOCK:
            if PAIRING_UNTIL <= time.monotonic():
                return api_v2_error("user:creation-not-enabled", 403)
        token = secrets.token_hex(16).upper()
        with USERS_LOCK:
            updated_users = dict(V2_USERS)
            updated_users[name] = token_digest(token)
            if not save_v2_users(updated_users):
                return api_v2_error("user:no-storage", 500)
            V2_USERS.clear()
            V2_USERS.update(updated_users)
        with PAIRING_LOCK:
            PAIRING_UNTIL = 0.0
        return jsonify({"token": token, "name": name})

    current_name = authenticated_v2_user()
    with USERS_LOCK:
        users = dict(V2_USERS)
    if request.method == "GET":
        return jsonify([{"name": name, "current": name == current_name} for name in users])

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str):
        return api_v2_error("json:parameter-missing:name", 400)
    target = payload["name"]
    if target not in users:
        return api_v2_error("user:not-found", 404)
    with USERS_LOCK:
        updated_users = dict(V2_USERS)
        del updated_users[target]
        if not save_v2_users(updated_users):
            return api_v2_error("user:no-storage", 500)
        V2_USERS.clear()
        V2_USERS.update(updated_users)
    return "", 204

@app.get("/api/measurement")
def api_v2_measurement():
    return jsonify(get_v2_measurement())

def apply_v2_system_update(payload):
    global CLOUD_ENABLED, API_V1_ENABLED
    if not isinstance(payload, dict) or not payload:
        return "json:no-parameters-recognized"
    allowed = {"cloud_enabled", "status_led_brightness_pct", "api_v1_enabled"}
    unknown = next((key for key in payload if key not in allowed), None)
    if unknown:
        return f"json:parameter-not-recognized:{unknown}"
    for key in ("cloud_enabled", "api_v1_enabled"):
        if key in payload and not isinstance(payload[key], bool):
            return f"json:parameter-invalid-type:{key}"
    if "status_led_brightness_pct" in payload:
        brightness = payload["status_led_brightness_pct"]
        if not isinstance(brightness, int) or isinstance(brightness, bool) or not 0 <= brightness <= 100:
            return "json:parameter-invalid-type:status_led_brightness_pct"
        options["status_led_brightness_pct"] = brightness
    if "cloud_enabled" in payload:
        CLOUD_ENABLED = payload["cloud_enabled"]
    if "api_v1_enabled" in payload:
        API_V1_ENABLED = payload["api_v1_enabled"]
    return None

def get_v2_batteries():
    return {
        "mode": BATTERY_MODE,
        "permissions": list(BATTERY_PERMISSIONS),
        "charge_to_full": BATTERY_CHARGE_TO_FULL,
        "battery_count": 0,
        "power_w": 0,
        "target_power_w": 0,
        "max_consumption_w": 0,
        "max_production_w": 0,
    }

def apply_v2_battery_update(payload):
    global BATTERY_MODE, BATTERY_PERMISSIONS, BATTERY_CHARGE_TO_FULL
    if not isinstance(payload, dict) or not payload:
        return "json:no-parameters-recognized"
    allowed = {"mode", "permissions", "charge_to_full"}
    unknown = next((key for key in payload if key not in allowed), None)
    if unknown:
        return f"json:parameter-not-recognized:{unknown}"
    if "mode" in payload and (not isinstance(payload["mode"], str) or payload["mode"] not in {"zero", "standby", "to_full", "predictive"}):
        return "json:parameter-invalid-type:mode"
    permissions = payload.get("permissions")
    if "permissions" in payload and (
        not isinstance(permissions, list)
        or any(not isinstance(value, str) or value not in {"charge_allowed", "discharge_allowed"} for value in permissions)
        or len(set(permissions)) != len(permissions)
    ):
        return "json:parameter-invalid-type:permissions"
    if "permissions" in payload and (BATTERY_MODE == "predictive" or payload.get("mode") == "predictive"):
        return "json:parameter-invalid-type:permissions"
    if "charge_to_full" in payload and not isinstance(payload["charge_to_full"], bool):
        return "json:parameter-invalid-type:charge_to_full"
    if payload.get("mode") == "to_full" and "permissions" in payload:
        return "json:parameter-not-exclusive"
    if "charge_to_full" in payload and ("mode" in payload or "permissions" in payload):
        return "json:parameter-not-exclusive"

    if "charge_to_full" in payload:
        BATTERY_CHARGE_TO_FULL = payload["charge_to_full"]
        if BATTERY_CHARGE_TO_FULL:
            BATTERY_MODE = "to_full"
            BATTERY_PERMISSIONS = []
        elif BATTERY_MODE == "to_full":
            BATTERY_MODE = "zero"
            BATTERY_PERMISSIONS = ["charge_allowed", "discharge_allowed"]
    else:
        if "mode" in payload:
            BATTERY_MODE = payload["mode"]
            BATTERY_CHARGE_TO_FULL = BATTERY_MODE == "to_full"
            if BATTERY_MODE == "to_full":
                BATTERY_PERMISSIONS = []
            elif BATTERY_MODE == "standby":
                BATTERY_PERMISSIONS = []
            elif BATTERY_MODE == "zero" and not BATTERY_PERMISSIONS:
                BATTERY_PERMISSIONS = ["charge_allowed", "discharge_allowed"]
        if "permissions" in payload:
            if BATTERY_MODE == "to_full":
                return "json:parameter-invalid-type:permissions"
            BATTERY_PERMISSIONS = list(permissions)
            BATTERY_MODE = "zero" if BATTERY_PERMISSIONS else "standby"
            BATTERY_CHARGE_TO_FULL = False
    return None

@app.route("/api/system", methods=["GET", "PUT"])
def api_v2_system():
    if request.method == "PUT":
        error = apply_v2_system_update(request.get_json(silent=True))
        if error:
            return api_v2_error(error, 400)
    return jsonify(get_v2_system())

@app.route("/api/batteries", methods=["GET", "PUT"])
def api_v2_batteries():
    if request.method == "PUT":
        error = apply_v2_battery_update(request.get_json(silent=True))
        if error:
            return api_v2_error(error, 400)
    return jsonify(get_v2_batteries())

@app.put("/api/system/identify")
def api_v2_identify():
    if DEBUG_MODE:
        print("API v2 identify requested (no physical LED on emulator)", flush=True)
    return "", 204

@app.put("/api/system/reboot")
def api_v2_reboot():
    print("API v2 reboot requested (emulator acknowledges; no hardware reboot performed)", flush=True)
    return "", 204

@app.get("/api/telegram")
def api_v2_telegram():
    return get_telegram()

def websocket_topic_data(topic, current_user):
    if topic == "device":
        return {
            "product_name": "P1 Meter",
            "product_type": "HWE-P1",
            "serial": DEVICE_SERIAL.lower(),
            "firmware_version": "6.00",
            "api_version": API_V2_VERSION,
        }
    if topic == "measurement":
        return get_v2_measurement()
    if topic == "system":
        return get_v2_system()
    if topic == "batteries":
        return get_v2_batteries()
    if topic == "user":
        with USERS_LOCK:
            users = list(V2_USERS)
        return [{"name": name, "current": name == current_user} for name in users]
    return None

def websocket_send(ws, packet):
    ws.send(json.dumps(packet, separators=(",", ":")))

@sock.route("/api/ws")
def api_v2_websocket(ws):
    if not request.is_secure:
        websocket_send(ws, {"type": "error", "data": {"message": "request:https-required"}})
        return
    api_version_header = request.headers.get("X-Api-Version")
    if api_version_header and not api_version_header.startswith("2"):
        websocket_send(ws, {"type": "error", "data": {"message": "request:api-version-not-supported"}})
        return

    websocket_send(ws, {"type": "authorization_requested", "data": {"api_version": API_V2_VERSION}})
    try:
        raw_auth = ws.receive(timeout=40)
        auth_message = json.loads(raw_auth) if raw_auth else {}
    except Exception:
        return
    if not isinstance(auth_message, dict) or auth_message.get("type") != "authorization":
        websocket_send(ws, {"type": "error", "data": {"message": "user:unauthorized"}})
        return
    current_user = v2_user_for_token(auth_message.get("data"))
    if not current_user:
        websocket_send(ws, {"type": "error", "data": {"message": "user:unauthorized"}})
        return
    websocket_send(ws, {"type": "authorized"})

    supported_topics = {"device", "user", "measurement", "system", "batteries"}
    subscriptions = set()
    last_payloads = {}
    last_poll = 0.0

    def publish(topic, force=False):
        payload = websocket_topic_data(topic, current_user)
        if payload is None:
            websocket_send(ws, {"type": "error", "data": {"message": "request:unknown-subscription"}})
            return
        comparison = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(comparison, dict):
            comparison.pop("timestamp", None)
        if force or last_payloads.get(topic) != comparison:
            websocket_send(ws, {"type": topic, "data": payload})
            last_payloads[topic] = comparison

    while True:
        try:
            raw_message = ws.receive(timeout=1)
        except Exception:
            break
        if raw_message:
            try:
                message = json.loads(raw_message)
            except (ValueError, TypeError):
                websocket_send(ws, {"type": "error", "data": {"message": "request:invalid-json"}})
                continue
            if not isinstance(message, dict) or not isinstance(message.get("type"), str):
                websocket_send(ws, {"type": "error", "data": {"message": "request:unknown-type"}})
                continue

            command = message["type"]
            topic = message.get("data") if command in {"subscribe", "unsubscribe"} else command
            if command == "subscribe":
                if not isinstance(topic, str):
                    websocket_send(ws, {"type": "error", "data": {"message": "request:unknown-subscription"}})
                    continue
                topics = supported_topics if topic == "*" else {topic}
                for selected in topics:
                    if selected not in supported_topics:
                        websocket_send(ws, {"type": "error", "data": {"message": "request:unknown-subscription"}})
                    else:
                        subscriptions.add(selected)
                        publish(selected, force=True)
            elif command == "unsubscribe":
                if isinstance(topic, str):
                    if topic == "*":
                        subscriptions.clear()
                    else:
                        subscriptions.discard(topic)
                        last_payloads.pop(topic, None)
            elif command == "identify":
                # The emulator has no physical status LED to blink.
                continue
            elif command in supported_topics:
                if command == "system" and isinstance(message.get("data"), dict):
                    error = apply_v2_system_update(message["data"])
                    if error:
                        websocket_send(ws, {"type": "error", "data": {"message": error}})
                        continue
                elif command == "batteries" and isinstance(message.get("data"), dict):
                    error = apply_v2_battery_update(message["data"])
                    if error:
                        websocket_send(ws, {"type": "error", "data": {"message": error}})
                        continue
                publish(command, force=True)
            else:
                websocket_send(ws, {"type": "error", "data": {"message": "request:unknown-type"}})

        now = time.monotonic()
        if subscriptions and now - last_poll >= 5:
            for selected in tuple(subscriptions):
                publish(selected)
            last_poll = now

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

def is_raw_p1_telegram(value):
    if not isinstance(value, str):
        return False
    normalized = value.lstrip("\ufeff \t\r\n")
    return normalized.startswith("/") and "\n" in normalized and "!" in normalized

def get_ha_telegram(entity_key):
    entity_id = options.get(entity_key)
    if not entity_id or not SUPERVISOR_TOKEN:
        return ""
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code != 200:
            return ""
        entity = response.json()
        state = entity.get("state")
        if is_raw_p1_telegram(state):
            return state
        attributes = entity.get("attributes") or {}
        for key in ("telegram", "raw_telegram", "p1_telegram"):
            value = attributes.get(key)
            if is_raw_p1_telegram(value):
                return value
        for value in attributes.values():
            if is_raw_p1_telegram(value):
                return value
    except Exception as error:
        if DEBUG_MODE:
            print(f"Could not read raw telegram from {entity_id}: {error}", flush=True)
    return ""

def extract_meter_type(raw_telegram):
    if not is_raw_p1_telegram(raw_telegram):
        return None
    for line in raw_telegram.lstrip("\ufeff \t\r\n").splitlines():
        header = line.strip()
        if header.startswith("/") and "\\" in header:
            return header
    return None

def configured_meter_type():
    meter_type = str(options.get("meter_type", DEFAULT_METER_TYPE)).strip()
    if "\r" in meter_type or "\n" in meter_type:
        return DEFAULT_METER_TYPE
    if not meter_type.startswith("/") or "\\" not in meter_type:
        return DEFAULT_METER_TYPE
    return meter_type

def gather_api_data():
    raw_telegram = get_ha_telegram("raw_telegram") if options.get("raw_telegram") else ""
    meter_type = extract_meter_type(raw_telegram) or configured_meter_type()
    meter_model = meter_type.split("\\", 1)[1].strip()

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
        "meter_model": meter_model,
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
    data["_meter_type"] = meter_type
    if extract_meter_type(raw_telegram):
        data["_raw_telegram"] = raw_telegram

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
    if request.is_secure or request.headers.get("X-Api-Version", "").startswith("2"):
        return jsonify({
            "product_name": "P1 Meter",
            "product_type": "HWE-P1",
            "serial": DEVICE_SERIAL.lower(),
            "firmware_version": "6.00",
            "api_version": API_V2_VERSION,
        })
    return jsonify({
        "product_type": "HWE-P1",
        "product_name": "P1 Meter Emulator",
        "serial": DEVICE_SERIAL,
        "firmware_version": "4.19",
        "api_version": "v1"
    })

@app.route('/api/v1/data', methods=['GET'])
def get_data():
    data = gather_api_data()
    return jsonify({key: value for key, value in data.items() if not key.startswith("_")})

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

    raw_telegram = data.get("_raw_telegram")
    if raw_telegram:
        return app.response_class(raw_telegram, mimetype="text/plain")

    meter_type = data.get("_meter_type", DEFAULT_METER_TYPE)

    lines = [
        meter_type,
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

def ensure_tls_certificate(local_ip):
    if USE_CUSTOM_TLS_CERTIFICATE:
        if not CUSTOM_TLS_CERT_FILE or not CUSTOM_TLS_KEY_FILE:
            raise ValueError("Both tls_certificate and tls_private_key must be configured")
        if not os.path.isfile(TLS_CERT_FILE) or not os.path.isfile(TLS_KEY_FILE):
            raise FileNotFoundError("Configured TLS certificate or private key was not found")
        return

    identity = f"{DEVICE_SERIAL.lower()}|{local_ip}"
    try:
        with open(TLS_CERT_IP_FILE, "r", encoding="utf-8") as marker:
            if marker.read().strip() == identity and os.path.isfile(TLS_CERT_FILE) and os.path.isfile(TLS_KEY_FILE):
                return
    except OSError:
        pass

    for path in (TLS_CERT_FILE, TLS_KEY_FILE):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cert_temp = f"{TLS_CERT_FILE}.tmp"
    key_temp = f"{TLS_KEY_FILE}.tmp"
    config_temp = f"{TLS_CERT_FILE}.cnf"
    cert_config = "\n".join([
        "[req]",
        "prompt = no",
        "distinguished_name = device_dn",
        "x509_extensions = server_cert",
        "[device_dn]",
        f"CN = appliance/p1dongle/{DEVICE_SERIAL.lower()}",
        "[server_cert]",
        "basicConstraints = critical,CA:TRUE",
        "keyUsage = critical,digitalSignature,keyEncipherment,keyCertSign",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = @alt_names",
        "[alt_names]",
        f"IP.1 = {local_ip}",
        f"DNS.1 = hwe-p1-{DEVICE_SERIAL.lower()}.local",
        "",
    ])
    try:
        with open(config_temp, "w", encoding="utf-8") as config_file:
            config_file.write(cert_config)
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
             "-keyout", key_temp, "-out", cert_temp, "-config", config_temp],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        os.chmod(key_temp, 0o600)
        os.replace(key_temp, TLS_KEY_FILE)
        os.replace(cert_temp, TLS_CERT_FILE)
        with open(TLS_CERT_IP_FILE, "w", encoding="utf-8") as marker:
            marker.write(identity)
    finally:
        for temporary in (cert_temp, key_temp, config_temp):
            try:
                os.remove(temporary)
            except OSError:
                pass

def serve_https():
    try:
        server = make_server(
            "0.0.0.0", 443, app, threaded=True,
            ssl_context=(TLS_CERT_FILE, TLS_KEY_FILE),
        )
        print("🔒 HTTPS API listening on port 443", flush=True)
        server.serve_forever()
    except OSError as error:
        print(f"❌ Could not start HTTPS server on port 443: {error}", flush=True)

def setup_mdns(ip_address):
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    properties = {
        b'api_version': API_MODE.encode('ascii'),
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

    try:
        ensure_tls_certificate(local_ip)
        threading.Thread(target=serve_https, daemon=True, name="https-api").start()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"❌ Could not prepare HTTPS certificate: {error}", flush=True)
    
    display_mac = DEVICE_SERIAL.ljust(12, '0')[:12]
    mac_format = ':'.join(display_mac[i:i+2] for i in range(0, 12, 2))
    
    print("\n" + "="*45, flush=True)
    print("🔌 HOMEWIZARD P1 EMULATOR", flush=True)
    print("="*45, flush=True)
    print(f"🌐 IP Address:    {local_ip}", flush=True)
    print(f"🏷️  MAC Address:   {mac_format}", flush=True)
    print(f"🔢 Serial Number: {DEVICE_SERIAL}", flush=True)
    print(f"🚪 Port:          80", flush=True)
    print(f"🔒 HTTPS Port:    443", flush=True)
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
