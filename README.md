# mt7921u (MT7961) Wi-Fi driver for Xiaomi Mi 10 — Android 11 / vendor kernel 4.19

Out-of-tree bring-up of a **MediaTek MT7921U / MT7961 USB Wi-Fi 6 adapter**
(`0e8d:7961`, interface class `FF/FF/FF`) on the **Xiaomi Mi 10 (umi)**, MIUI 12.5,
Android 11, running the vendor kernel:

```
Linux 4.19.113-perf-gec90c723c482 aarch64
```

The point of this repository is not "one dongle on one phone". It is the two
problems that have to be solved for *any* device whose kernel is a vendor kernel
you cannot rebuild:

1. **The kernel enforces `CONFIG_MODVERSIONS=y`.** Any module you compile must
   carry the *exact* 32-bit CRC of every symbol it imports. Without the vendor's
   build tree that table is not available anywhere in `/proc`.
2. **This kernel has no `mac80211` at all** (the vendor uses a proprietary
   Qualcomm Wi-Fi driver), and its `cfg80211` is *not* the mainline 4.19 one.
   So the driver has to be built together with a matching `mac80211`, against the
   right source baseline.

Both were solved empirically, and the method is documented so it can be reused.

---

## Status

| Item | State |
|---|---|
| Kernel ABI reverse-engineered (symbol CRC table) | done, verified 1094/1094 against vendor modules |
| Correct source baseline identified | done (Xiaomi vendor tree, not mainline) |
| `mac80211.ko` built for this kernel | done, vermagic byte-identical |
| mt76 / mt7921u down-port to 4.19 | done, 19 files patched, builds clean |
| Module stack loads on the device | **done** — 6/6 modules `rc=0`, `usbcore: registered new interface driver mt7921u` |
| Firmware download + probe | **not yet verified** |
| Scan / monitor mode / injection | **not yet verified** |

> The remaining blocker is **electrical, not software**: the phone's OTG port
> fails to bring the dongle up (`usb usb1-port1: Cannot enable`), reproducible on a
> completely pristine kernel with no modules loaded, and re-plugging can trip the
> PMIC into a reset. See [`docs/hardware-notes.md`](docs/hardware-notes.md).
> A powered USB hub (or an OTG Y-cable with power injection) is required.

---

## How it works, in one screen

```
                        ┌──────────────────────────────┐
 boot.img  ──unpack──▶  │  __ksymtab / __kcrctab        │  ← authoritative
 (magiskboot)           │  12,385 (symbol, crc) pairs   │    CRC source
                        └──────────────┬───────────────┘
                                       │  calibrate against
                        ┌──────────────▼───────────────┐
 vendor *.ko in         │  __versions sections of the   │  → 1094/1094 match
 /vendor/lib/modules    │  already-loaded modules       │     proves the method
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                            Module.symvers (crafted)
                                       │
  /proc/config.gz ──▶ .config ──▶ modules_prepare ──▶ build ──▶ insmod
                                       │
                     symbol-set diff vs kernel ──▶ which source tree?
```

Details, including the tricks that make each step work:
[`docs/findings.md`](docs/findings.md).

---

## Requirements

* Xiaomi Mi 10 (`umi`), MIUI 12.5 / Android 11, kernel `4.19.113-perf-gec90c723c482`
* unlocked bootloader + **root** (Magisk). No system partition is modified by
  anything here: modules are `insmod`-ed at runtime only.
* Build host: an aarch64 Linux environment with `gcc`, `make`, `bison`, `flex`,
  `bc`, `libssl-dev`, `libelf-dev` (~4 GB free, tree is ~1 GB)
* Adapter: MT7921U / MT7961 (`0e8d:7961`) — e.g. Alfa AWUS036AXML class of device
* Firmware blobs (not redistributed here):
  `mediatek/WIFI_RAM_CODE_MT7961_1.bin` and
  `mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin`, from
  [linux-firmware](https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git/tree/mediatek)

## Build

```sh
# 1. vendor kernel source (the device's own tree)
git clone --depth=1 -b umi-q-oss \
    https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git ~/kernel
#    NOTE: the OSS branch is 4.19.81; the shipped kernel is 4.19.113.
#    Set SUBLEVEL=113 and keep the device's own config so the ABI matches.

# 2. bring in the mt76 snapshot that supports MT7921U and patch it back to 4.19
curl -L https://github.com/openwrt/mt76/archive/refs/heads/openwrt-22.03.tar.gz \
     | tar xz -C /tmp
cp -a /tmp/mt76-openwrt-22.03 ~/kernel/drivers/net/wireless/mediatek/mt76
patch -p2 -d ~/kernel/drivers/net/wireless/mediatek/mt76 \
      < patches/mt76-4.19-backport.patch

# 3. derive .config from the *running* device, then build
python3 tools/prep_config.py           # /proc/config.gz -> .config (exact vermagic)
cd ~/kernel && make ARCH=arm64 olddefconfig modules_prepare
python3 tools/scan_ksymtab.py          # boot.img -> 12,385 authoritative CRCs
python3 tools/gen_symvers.py .         # -> Module.symvers
make ARCH=arm64 M=net/mac80211 modules
make ARCH=arm64 M=drivers/net/wireless/mediatek/mt76 modules
```

`scripts/build.sh` does all of the above end to end.
The tooling is explained in [`tools/README.md`](tools/README.md).

## Load

```sh
su -c sh scripts/mw-load.sh     # verifies enumeration, sets fw path, insmods 6 modules
su -c sh scripts/mw-unload.sh   # reverse order, restores the device state
```

Verified output on the device:

```
--- 3. load module stack (dependency order) ---
   mac80211           ok
   mt76               ok
   mt76-usb           ok
   mt76-connac-lib    ok
   mt7921-common      ok
   mt7921u            ok
```

```
# lsmod | grep -E 'mac80211|mt76|mt7921'
mt7921u           20480  0
mt7921_common     77824  1 mt7921u
mt76_connac_lib   61440  2 mt7921u,mt7921_common
mt76_usb          32768  1 mt7921u
mt76              90112  4 mt7921u,mt7921_common,mt76_connac_lib,mt76_usb
mac80211         741376  3 mt7921_common,mt76_connac_lib,mt76
```

---

## Scope and honesty notes

* The `Module.symvers` shipped in `data/` is **valid only for this exact kernel
  build** (`4.19.113-perf-gec90c723c482`, MIUI 12.5 V12.5.10.0.RJBCNXM). On a
  different ROM/OTA you must regenerate it from your own boot image — that is what
  `tools/` is for, and it takes a couple of minutes.
* The driver stack was verified to *load*; the RF path was not yet exercised
  because of the OTG power limit described above.
* Functions that this kernel cannot express are compiled out rather than faked:
  SAR power limits, the 6 GHz band, MBSSID, HE beacon-rate masks, airtime
  accounting, hardware RX header translation (see the patch for the exact list).
  For a 2.4/5 GHz USB adapter on this kernel that is a faithful reduction, not a
  crippled driver.

## Licensing

* `patches/` modifies mt76, which is `GPL-2.0` / `BSD-3-Clause-Clear` per file —
  those files keep their original licenses, and the `mac80211` side is `GPL-2.0`.
* `tools/` and `scripts/` are original work, released under the MIT license
  (`LICENSE`).
* No vendor firmware or kernel binaries are redistributed here.

## Credits

* mt76 — Felix Fietkau and contributors; OpenWrt for keeping the out-of-tree tree
* linux-firmware for the MT7961 blobs
* Xiaomi for publishing the `umi-q-oss` kernel source
