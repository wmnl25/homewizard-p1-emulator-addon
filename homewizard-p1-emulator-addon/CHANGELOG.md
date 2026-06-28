# Changelog

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