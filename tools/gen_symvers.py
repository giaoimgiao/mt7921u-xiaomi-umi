#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_symvers.py <tree-root> -- write Module.symvers from the authoritative CRC
table extracted out of the running kernel image."""
import json
import os
import sys

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TREE", ".")
OUT = TREE + "/Module.symvers"
crc = json.load(open(os.environ.get("CRC_JSON", "kernel_crc.json")))

with open(OUT, "w") as f:
    for name in sorted(crc):
        f.write("0x%08x\t%s\tvmlinux\tEXPORT_SYMBOL\n" % (crc[name], name))

print("[+] %d symbols -> %s" % (len(crc), OUT))