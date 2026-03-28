# HomeWizard P1 Emulator (Home Assistant Add-on)

This version of the emulator is specifically built to run as a **Local Add-on** directly inside Home Assistant. 

Because it runs natively within the Home Assistant environment, it is much easier to set up: you **no longer need a `.env` file** or a **Long-Lived Access Token**. It communicates securely and directly via the internal Home Assistant Supervisor. Additionally, you can configure all your sensor mappings directly through the Home Assistant UI!

## 📂 File Structure

To install this as a local add-on, you need to create a folder named `p1_emulator` inside your Home Assistant `/addons/` directory. 

Inside this folder, you need to place the following 3 files:

### 1. `config.yaml`
This file tells Home Assistant how to configure the add-on and generates the user interface for your settings.

```yaml
name: "HomeWizard P1 Emulator"
description: "Emulates a HomeWizard P1 meter based on Home Assistant sensors."
version: "1.1.0"
slug: "homewizard_p1_emulator"
init: false
arch:
  - aarch64
  - amd64
  - armhf
  - armv7
host_network: true
options:
  debug_mode: true
  device_serial: ""
  import_t1: "sensor.p1_energy_consumed_tariff_1"
  import_t2: "sensor.p1_energy_consumed_tariff_2"
  export_t1: "sensor.p1_energy_produced_tariff_1"
  export_t2: "sensor.p1_energy_produced_tariff_2"
  active_power_consumed: "sensor.p1_power_consumed"
  active_power_produced: "sensor.p1_power_produced"
  power_l1: ""
  power_l2: ""
  power_l3: ""
  voltage_l1: ""
  voltage_l2: ""
  voltage_l3: ""
  current_l1: ""
  current_l2: ""
  current_l3: ""
  short_power_drop: ""
  power_fail: ""
schema:
  debug_mode: bool
  device_serial: str?
  import_t1: str
  import_t2: str
  export_t1: str?
  export_t2: str?
  active_power_consumed: str
  active_power_produced: str?
  power_l1: str?
  power_l2: str?
  power_l3: str?
  voltage_l1: str?
  voltage_l2: str?
  voltage_l3: str?
  current_l1: str?
  current_l2: str?
  current_l3: str?
  short_power_drop: str?
  power_fail: str?