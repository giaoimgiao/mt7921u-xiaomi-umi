#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inventory.py <log> -- summarise what the backport still needs."""
import re
import sys
from collections import Counter

log = open(sys.argv[1] if len(sys.argv) > 1 else "/root/xiaomi/mt76_7.log",
           errors="replace").read()

syms, members, funcs, others = set(), set(), set(), Counter()

for m in re.finditer(r"error: ['\u2018]([A-Za-z_0-9]+)['\u2019] undeclared", log):
    syms.add(m.group(1))
for m in re.finditer(r"error: implicit declaration of function ['\u2018]([A-Za-z_0-9]+)", log):
    funcs.add(m.group(1))
for m in re.finditer(r"error: ['\u2018]struct ([A-Za-z_0-9 ]+)['\u2019] has no member named ['\u2018]([A-Za-z_0-9]+)", log):
    members.add("%s.%s" % (m.group(1).strip(), m.group(2)))
for line in log.splitlines():
    if "error:" in line:
        tail = line.split("error:", 1)[1].strip()
        others[re.sub(r"[0-9]+", "N", tail)[:70]] += 1

print("=== missing constants / identifiers (%d) ===" % len(syms))
for s in sorted(syms):
    print("   %s" % s)
print("=== missing struct members (%d) ===" % len(members))
for s in sorted(members):
    print("   %s" % s)
print("=== missing functions (%d) ===" % len(funcs))
for s in sorted(funcs):
    print("   %s" % s)
print("=== other error kinds ===")
for k, v in others.most_common(12):
    print("   %3d  %s" % (v, k))