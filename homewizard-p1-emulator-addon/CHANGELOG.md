# Changelog

## 2.0.1
- 🛠️ Fixed: Mount the Home Assistant `/ssl` directory inside the add-on so configured TLS certificate and private-key paths are accessible to the HTTPS server.

## 2.0.0
- ✨ Added: Simultaneous API v1 and v2 support, including bearer-token pairing, measurement, system, telegram, and battery endpoints, HTTPS, and WebSocket.
- ✨ Added: Home Assistant ingress Web UI for pairing and device/measurement status.
- ✨ Added: Optional raw-telegram sensor input; the telegram header supplies the meter model, with a configurable `/ISK5\2M550E-1013` fallback.
- 🔒 Added: Configurable TLS certificate and private-key paths for Home Assistant v2 pairing; API v1 remains the default discovery preference.
- ⚠️ Note: The generated self-signed certificate is for direct testing only. Home Assistant's built-in v2 client requires a certificate chain trusted by Home Assistant. Reboot and identify actions are acknowledged but cannot affect physical hardware.

## 1.3.0
- ✨ Added: `/api/v1/telegram` endpoint with DSMR-formatted readings and CRC-16 checksum.

## 1.2.0
- ✨ Added: HomeWizard-compatible API version and CORS response headers.
- ✨ Added: Device ID, active tariff, aggregate current, and tariff-2 totals to the data response.
- ✨ Added: Official gas meter identifier fields and the external gas meter entry.

## 1.1.0
- ✨ Added: 100% complete endpoint parity with the official HomeWizard P1 API.
- ✨ Added: Support for Combined Power Totals (`total_power_import_kwh` and `total_power_export_kwh`).
- ✨ Added: Line frequency support (`active_frequency_hz`).
- ✨ Added: Voltage sags and swells tracking for all 3 phases.
- ✨ Added: Peak demand tracking support (Belgian capacity tariff fields).
- ✨ Added: Legacy external gas meter support (`total_gas_m3`).
- 🛠️ Fixed: Adjusted power failure output names to match official HomeWizard API spec (`any_power_fail_count` and `long_power_fail_count`).

## 1.0.12
- ✨ Added: Support for extended optional schema sensors (T3/T4 tariffs, L2/L3 phases, power failures, and short power drops).

- 🔧 Improved: Dynamic API payload generation conditionally includes extra phases and tariffs only when configured.

- 🔧 Improved: L1 voltage and current now prioritize real UI sensor data over hardcoded or calculated fallbacks.

## 1.0.11
- 🛠️  Fix: fix power_produced and power_consumed input to kwh to avoid guessing

## 1.0.10
- ✨ Added: /api/v1/system route

## 1.0.9
- 🔧 Improved: expand debug mode

## 1.0.8
- 🛠️  Fix: Enable allow_name_change=True to prevent zeroconf._exceptions.NonUniqueNameException

## 1.0.7
- ✅ Restored: MAC Address and mDNS local name in startup logs.

## 1.0.6
- 🔧 Improved: added port 80 conflict detection to main.py
- 🔧 Improved: Graceful shutdown of mDNS services.

## 1.0.5
- ✅ Fixed: Default sensor entities restored in configuration.

## 1.0.4
- ✅ Fixed: Supervisor schema validation errors in config.yaml.
- ✅ Added: Multi-language support (EN, NL, DE, FR, ES).
- ✅ Added: Professional P1 Emulator icon for the Add-on Store.
- 🔧 Improved: mDNS/ZeroConf discovery for faster detection by Zendure SolarFlow.
- 🔧 Fix: Folder structure corrected for Home Assistant Add-on Store compatibility.
- 🔧 Improved: Error handling when fetching sensor data via the internal API.

## 1.0.3
- ✨ New: Support for additional P1 fields (3-phase voltage and current).
- 📝 Docs: Updated README.md with installation and setup instructions.

## 1.0.1
- 🛠️ Stability: Improvements to the Flask server and mDNS advertisements.

## 1.0.0
- 🚀 Initial stable release of the HomeWizard P1 Emulator.
- 📡 Support: mDNS / ZeroConf (Bonjour) discovery.
- 🔌 Integration: Real-time sensor data via Home Assistant Internal API.
