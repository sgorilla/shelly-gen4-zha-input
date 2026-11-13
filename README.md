# Shelly Gen4: a separate wall-switch input in ZHA

In detached mode, the Shelly relay can stay on while a wall switch controls
smart bulbs through an automation. That needs two separate states: the relay
output and the physical switch input.

This custom ZHA quirk adds an **Input** binary sensor from the Shelly's Zigbee
input commands. It preserves the relay entity and stock Shelly Wi-Fi management
support. It does not change detached mode, relay state, firmware, network
membership, Wi-Fi settings, or automations.

## Upstream work and status

The input-entity approach is already proposed upstream by **dw86uk** in
[zha-device-handlers PR #5417](https://github.com/zigpy/zha-device-handlers/pull/5417).
This repository is a temporary installation guide and guarded local workaround,
not a replacement for that PR or a claim to have invented the approach.

Check whether your current Home Assistant version already exposes the Input
entity before installing. Do not install this alongside another Shelly input
override. Remove the local override once the built-in implementation meets your
needs; custom quirks can mask later upstream improvements.

## Compatibility and evidence

Test environment: Home Assistant **2026.11.1**, ZHA **2.4.3**,
zha-quirks **2.4.1**, zigpy **2.4.1**, Python **3.14**. Older APIs are not supported
by this file. Recheck compatibility after upgrades.

| Zigbee model | Product | Validation |
| --- | --- | --- |
| `1` | Shelly 1 Gen4, S4SW-001X16EU | Physical input test on firmware 2.2.0 using the device-scoped precursor |
| `Mini1PM` | Shelly 1PM Mini Gen4, S4SW-001P8EU | Physical input test on firmware 2.2.1 using the device-scoped precursor |
| `1PM` | Shelly 1PM Gen4 | Synthetic regression tests; not physically tested here |
| `Mini1` | Shelly 1 Mini Gen4 | Synthetic regression tests; not physically tested here |

The published generic version is tested offline. The physical tests used the
same entity declaration in an earlier override restricted to those two devices.
Both input tests changed the Input state while the relay stayed on.

The normal matcher also requires:

- Endpoint 1: Home Automation profile `0x0104`, On/Off **server/input** cluster.
- Endpoint 2: profile `0x0104`, On/Off Switch Configuration server cluster
  `0x0007`, On/Off **client/output** cluster `0x0006`.
- Endpoint 239: Shelly profile `0xC001`, Wi-Fi Setup server cluster `0xFC02`.

Other signatures keep their existing handler. Multi-input devices such as 2PM
and non-relay devices such as EM Mini are deliberately excluded.

## Install

1. Back up your Home Assistant configuration. Download
   [`shelly_gen4_input.py`](shelly_gen4_input.py).
2. Put **only that Python file** in your existing custom-quirks directory. If you
   do not have one, create `/config/zhacustomquirks/` and put it there.
3. If needed, add the following to `configuration.yaml`. Merge it into an
   existing `zha:` section; do not create a second section or replace unrelated
   configuration. If you already use a different custom directory, keep it.

   ```yaml
   zha:
     custom_quirks_path: /config/zhacustomquirks
   ```

4. Validate the configuration, then restart **Home Assistant Core**. This briefly
   interrupts Home Assistant. Restarting the host, coordinator, or other add-ons
   is unnecessary.
5. Open the Shelly's **ZHA device page**, then its three-dot menu → **Reconfigure**.
   This binds the input endpoint to the coordinator. A Core restart alone does
   not perform this binding step.
6. Find the new **Input** binary sensor. Flip the wall switch, wait two seconds,
   and flip it back. Confirm that Input follows both changes. If you use detached
   mode, confirm that the relay remains on.

Configure detached mode separately in the Shelly interface if that is your
intended behavior. The quirk also leaves the existing input inversion and
switch-action settings alone.

## Use it in an automation

Replace the example entity names below with your own. These explicit edges avoid
triggering on an `unknown` or `unavailable` state during startup.

```yaml
alias: Toggle lights from detached Shelly input
triggers:
  - trigger: state
    entity_id: binary_sensor.example_shelly_input
    from: "off"
    to: "on"
  - trigger: state
    entity_id: binary_sensor.example_shelly_input
    from: "on"
    to: "off"
actions:
  - action: light.toggle
    target:
      entity_id: light.example_room
mode: single
```

If an existing automation already listens to the Shelly Wi-Fi input, replace its
trigger instead of creating a second automation that toggles the same lights.
Verify the new automation before disabling Wi-Fi. A working ZHA entity does not
automatically migrate an existing automation away from the Shelly integration.

## What the Input state means

The relay is endpoint 1's On/Off server cluster. The physical input sends commands
from endpoint 2's On/Off client cluster. ZHA's existing `OnOffClientCacheSync`
updates that client cache; this quirk only declares a binary sensor reading it.
There is no second command handler, which would risk processing toggle commands
twice.

This is state reconstructed from received commands, not an independently polled
physical-position measurement. In the tested ZHA version an empty cache displays
as off. Cycle the switch before relying on its initial state. Missed messages,
restarts, inversion, and firmware configured to send only `toggle` can make the
value differ from the physical switch position. Absolute `on`/`off` commands
resynchronize the cache; toggle-only commands do not establish absolute position.

## If endpoint 2 is missing

A device can retain an old saved interview that omits an input endpoint supported
by its current firmware. **Do not assume every missing endpoint is stale.**
Reconfigure binds known endpoints; it is not a complete new interview.

First confirm the actual device supports endpoint 2. With Wi-Fi temporarily
available, an advanced diagnostic is Shelly's
[`Zigbee.ReadAttr`](https://shelly-api-docs.shelly.cloud/gen2/Integrations/Zigbee/ZigbeeRPC/):
read cluster `0x0007` attributes `0x0000` (switch type) and `0x0010` (switch
actions) on endpoint 2, using the device's **current Zigbee short address** as
`dst_addr`. A successful response is evidence that endpoint exists; a timeout
does not establish that it does not. Do not substitute its Wi-Fi IP or an old
short address.

Only after verifying that signature, add a device-specific entry to
`VERIFIED_MISSING_INPUT_ENDPOINTS` near the top of the Python file:

```python
VERIFIED_MISSING_INPUT_ENDPOINTS = {
    "00:11:22:33:44:55:66:77": "1",  # example only: use your Zigbee IEEE and model
}
```

This opt-in supplies endpoint 2 only in ZHA's resolved device view, only when it
is missing, and only for that IEEE/model pair. It does not edit `zigbee.db` or the
device firmware. Restart Core, Reconfigure the device, and repeat the physical
input test. Leave the mapping empty for normally interviewed devices.

## Wi-Fi recovery and Bluetooth tracking

Shelly's [Wi-Fi Setup cluster](https://shelly-api-docs.shelly.cloud/gen2/Integrations/Zigbee/CustomClusters/WiFiSetupCluster/)
allows Wi-Fi configuration through Zigbee, and this quirk preserves its stock
handler. That recovery path requires a functioning Zigbee connection. The
published quirk does not add a Wi-Fi switch entity or exercise recovery commands.

For the [1 Gen4](https://kb.shelly.cloud/knowledge-base/shelly-1-gen4) and
[1PM Mini Gen4](https://kb.shelly.cloud/knowledge-base/shelly-1pm-mini-gen4), Shelly
documents holding the device's own control button for **five seconds** to enable
its setup access point. Connect to that AP and open `http://192.168.33.1`.
Three quick presses restart Zigbee inclusion. **Ten seconds is a factory reset**,
which is a different operation. Access to a button inside a mains wall box must
be made electrically safe; the normal wall rocker is not this button. Check the
exact model and firmware instructions before using these procedures.

Bermuda uses Bluetooth advertisements and RSSI forwarded to Home Assistant.
Shelly explicitly documents that [Bluetooth scanning is unavailable in Gen4
Zigbee mode](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/BLE/#bluetooth-scan).
Keeping Wi-Fi enabled does not restore scanning. Use a separate supported BLE
scanner for that location; this ZHA quirk cannot add a missing firmware feature.

## Rollback

Remove only `shelly_gen4_input.py` from the custom directory and restart Core.
Preserve other custom quirks. Restore any automation trigger you changed. No
device reset, firmware change, or Zigbee network migration is needed.

## Run the offline tests

Use a separate development environment, not the running Home Assistant Python
environment. Tests use synthetic device signatures and a mocked gateway; they
do not connect to a coordinator or physical device.

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -v
```

The tests check signature/model guards, explicit missing-endpoint recovery,
preservation of the original device view and management cluster, and incoming
on/off/toggle messages changing the Input exactly once without changing the
relay cache.

Licensed under [Apache-2.0](LICENSE). This project is independent of Shelly and
Home Assistant; the maintained integration belongs upstream.
