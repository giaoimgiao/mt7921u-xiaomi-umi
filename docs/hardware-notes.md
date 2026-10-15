# Hardware notes — the OTG power wall (read this before blaming the driver)

On the Mi 10 the driver stack loads, the driver registers, and then nothing
happens, because **the dongle never makes it onto the USB bus**. This is worth
documenting because it looks exactly like a driver bug and is not one.

## Signature

```
[  100.968169] usb usb1-port1: Cannot enable. Maybe the USB cable is bad?
[  101.850962] usb usb1-port1: Cannot enable. Maybe the USB cable is bad?
[  103.056082] usb usb1-port1: Cannot enable. Maybe the USB cable is bad?
[  103.940200] usb usb1-port1: Cannot enable. Maybe the USB cable is bad?
```

with, a moment earlier:

```
[  100.644698] usb 1-1: new high-speed USB device number 85 using xhci-hcd
```

Meaning: the dongle *is* there and pulls D+ (the controller sees it), but the port
cannot complete the reset/enable sequence. On this Qualcomm platform the port then
gives up:

```
usb usb1-port1: attempt power cycle
usb usb1-port1: unable to enumerate USB device
msm-dwc3 a600000.ssusb: DWC3 in low power mode
```

## Why this is definitely not the driver

* The same `Cannot enable` sequence reproduces on a **freshly booted, pristine
  kernel with zero modules loaded**.
* The first occurrence predates the module load by ~10 minutes
  (`t=99755` vs `t=100344` in the same boot): the port was already failing before
  any of this code existed on the device.
* Nothing is bound to the failing port, so no driver probe can have run; there is
  also no `console-ramoops` in `pstore`, i.e. no kernel oops — the reset that a
  re-plug can trigger is a PMIC/power protection event, not a software crash.

## What the numbers say

| observation | value |
|---|---|
| negotiated speed | USB 2.0 (`bcdUSB 480`) |
| OTG role | `extcon: USB-HOST=1`, Type-C `data_role=host`, `power_role=source` |
| host current budget | USB 2.0 host = **500 mA** by spec |
| MT7921U inrush | MT7961-class parts pull well above that during firmware boot |

The dongle works fine on a PC. On the phone, VBUS sags during inrush, the port
fails to enable, and a re-plug can collapse the rail hard enough to reset the SoC.

## Mitigations, in order of success rate

1. **Powered USB hub** between phone and dongle (own PSU). This is the fix.
2. **OTG Y-cable with power injection** (5 V into VBUS, diode-isolated so the
   phone is not back-fed).
3. A shorter / lower-resistance OTG adapter and cable — the kernel's own hint.
4. A lower-power adapter. Any MT7612U / MT7612U-class or RTL88xx-class dongle
   needs far less inrush and will very likely enumerate on this port directly.
   The `mac80211.ko` built here is reusable for those; only the corresponding
   mt76 sub-driver has to be enabled.

## Do not

* Do not hot-plug repeatedly while the port is reporting `Cannot enable` — each
  attempt stresses the PMIC, and one of them is what resets the phone.
* Do not assume a software "port reset" exists: with the port already failed the
  port device is gone from sysfs, and Type-C role switching does nothing through a
  C-to-A OTG adapter without PD.

## If you want to keep the link up once it enumerates

```sh
echo -1 > /sys/bus/usb/devices/1-1/power/autosuspend_delay_ms
echo on > /sys/bus/usb/devices/1-1/power/control
```

(`scripts/mw-load.sh` does this automatically.) A dongle that autosuspends tends
to drop off the bus on an already marginal port.