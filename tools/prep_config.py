#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_config_x2.py -- device /proc/config.gz -> .config for the vendor build tree.

Rules:
  * the running kernel's config is authoritative for everything that shapes the
    ABI (PREEMPT/SMP/MODVERSIONS/MPLS/VA_BITS/...), so it is copied verbatim;
  * the few symbols we intentionally change/force are *removed* from the copy and
    re-appended once at the end, so an earlier "# CONFIG_X is not set" line can
    never win over our value (olddefconfig honours the last assignment).
"""
import os
import re

SRC = os.environ.get("CONFIG_TXT", "config.txt")
TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TREE", ".")
DST = os.path.join(TREE, ".config")
LOCALVERSION = '"-perf-gec90c723c482"'

WANT = {
    "CONFIG_CFG80211": "m",
    "CONFIG_MAC80211": "m",
    "CONFIG_MAC80211_RC_MINSTREL": True,
    "CONFIG_MAC80211_RC_MINSTREL_HT": True,
    "CONFIG_MAC80211_RC_MINSTREL_VHT": True,
    "CONFIG_MAC80211_RC_DEFAULT_MINSTREL": True,
    "CONFIG_MAC80211_LEDS": False,
    "CONFIG_MAC80211_DEBUGFS": False,
    "CONFIG_MAC80211_MESH": False,
    "CONFIG_MAC80211_HWSIM": False,
    "CONFIG_MT76_CORE": "m",
    "CONFIG_MT76_USB": "m",
    "CONFIG_MT76_CONNAC_LIB": "m",
    "CONFIG_MT7921_COMMON": "m",
    "CONFIG_MT7921U": "m",
    "CONFIG_MT7921E": False,
    "CONFIG_MT7921S": False,
    "CONFIG_MT76_SDIO": False,
    "CONFIG_MT76x0U": False,
    "CONFIG_MT76x0_COMMON": False,
    "CONFIG_MT76x2_COMMON": False,
    "CONFIG_MT76x2E": False,
    "CONFIG_MT76x2U": False,
    "CONFIG_MT7603E": False,
    "CONFIG_MT7615_COMMON": False,
    "CONFIG_MT7615E": False,
    "CONFIG_MT7663_USB_SDIO_COMMON": False,
    "CONFIG_MT7663U": False,
    "CONFIG_MT7663S": False,
    "CONFIG_MT7915E": False,
    "CONFIG_MT76x02_LIB": False,
    "CONFIG_MT76x02_USB": False,
    "CONFIG_WANT_DEV_COREDUMP": False,
    "CONFIG_DEV_COREDUMP": False,
}

SET_RE = re.compile(r"^(CONFIG_[A-Za-z0-9_]+)=")
UNSET_RE = re.compile(r"^#\s*(CONFIG_[A-Za-z0-9_]+) is not set")

out, touched = [], set()
for ln in open(SRC, errors="replace").read().splitlines():
    if ln.startswith("CONFIG_LOCALVERSION"):
        continue
    m = SET_RE.match(ln) or UNSET_RE.match(ln)
    name = m.group(1) if m else None
    if name in WANT:
        touched.add(name)
        continue
    out.append(ln)

out.append('CONFIG_LOCALVERSION=%s' % LOCALVERSION)
out.append("# CONFIG_LOCALVERSION_AUTO is not set")
for name, v in WANT.items():
    if v is False:
        out.append("# %s is not set" % name)
    elif v is True:
        out.append("%s=y" % name)
    else:
        out.append("%s=%s" % (name, v))

open(DST, "w").write("\n".join(out) + "\n")
print("[*] .config written: %d lines (overrode %d device symbols)"
      % (len(out), len(touched)))
for n in sorted(touched):
    print("    forced: %s = %s" % (n, WANT[n]))