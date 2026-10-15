#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diff_exports.py <Module.symvers ...>

Two independent questions, deliberately separated:

1. symbol SET  -- compiler independent. If our build exports exactly the names
   the running kernel exports (and none it lacks), the source revision matches.
2. CRC values  -- compiler dependent (genksyms hashes preprocessed type text, so
   gcc vs clang differ). Only meaningful when the compiler matches.
"""
import json
import os
import sys

crc = json.load(open(os.environ.get("KERNEL_CRC", "kernel_crc.json")))
kernel_syms = set(crc)


def load(path):
    out = {}
    for ln in open(path, errors="replace"):
        p = ln.rstrip("\n").split("\t")
        if len(p) < 2:
            continue
        try:
            out[p[1]] = int(p[0], 16)
        except ValueError:
            pass
    return out


for path in sys.argv[1:]:
    exp = load(path)
    names = set(exp)
    pref = [n for n in names if n.startswith(("cfg80211_", "ieee80211_"))]
    kpref = [n for n in kernel_syms if n.startswith(("cfg80211_", "ieee80211_"))]

    print("=" * 72)
    print("file                          : %s" % path)
    print("exports (all)                 : %d" % len(names))
    print("wireless-prefixed exports     : %d   (kernel has %d)"
          % (len(pref), len(kpref)))
    print("  same name & in kernel       : %d" % len([n for n in pref if n in kernel_syms]))
    print("  exported but kernel lacks   : %d  %s"
          % (len([n for n in pref if n not in kernel_syms]),
             sorted(n for n in pref if n not in kernel_syms)[:6]))
    print("  kernel exports but we lack  : %d  %s"
          % (len([n for n in kpref if n not in names]),
             sorted(n for n in kpref if n not in names)[:6]))

    known = [n for n in exp if n in crc]
    same = [n for n in known if exp[n] == crc[n]]
    print("CRC: comparable=%d identical=%d (%.1f%%)"
          % (len(known), len(same), 100.0 * len(same) / max(1, len(known))))
    if len(known) - len(same):
        print("  first mismatches: %s" % sorted(set(known) - set(same))[:6])