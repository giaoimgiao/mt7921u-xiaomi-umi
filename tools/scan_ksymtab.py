#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_ksymtab2.py -- rebuild the authoritative (symbol -> module CRC) map from a
raw arm64 kernel Image.  Fast version.

Anchor logic for pairing CRCs:
  ksymtab entries and kcrctab entries are two parallel arrays in the same order.
  Instead of scoring every possible offset (O(size * N_symbols)), we take a few
  already-trusted vendor CRCs, locate their 4-byte occurrences in the image, and
  derive candidate kcrctab bases from (occurrence - 4*index).  Each candidate is
  then scored against the whole trusted set, so a wrong base cannot survive.
"""
import json
import os
import struct
import sys

IMG = os.environ.get("IMG", "kernel")
NAMES = os.environ.get("NAMES", "kallsyms_names.txt")
TRUSTED = os.environ.get("TRUSTED", "crc_dict.json")
OUT = os.environ.get("OUT", "kernel_crc.json")
CACHE = os.environ.get("CACHE", "scan_cache.json")

BLOB = open(IMG, "rb").read()
N = len(BLOB)
print("[*] image %d bytes, magic@56=%r" % (N, BLOB[56:60]))

pool = set()
with open(NAMES, "r", errors="replace") as f:
    for ln in f:
        ln = ln.strip()
        if ln:
            pool.add(ln)
print("[*] name pool: %d" % len(pool))


def cstr(off):
    if off < 0 or off >= N:
        return None
    end = BLOB.find(b"\x00", off, off + 128)
    if end < 0 or end == off:
        return None
    try:
        s = BLOB[off:end].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not (2 <= len(s) <= 100):
        return None
    for ch in s:
        if not (ch.isalnum() or ch in "_.$"):
            return None
    return s if s in pool else None


def scan_entries(nameoff_field):
    """Return {F: name} for every 4-aligned F whose name_offset resolves."""
    hits = {}
    unpack = struct.unpack_from
    for F in range(0, N - nameoff_field - 4, 4):
        no = unpack("<i", BLOB, F + nameoff_field)[0]
        if -64 < no < 64:            # names are never adjacent; skip dwords
            continue
        nm = cstr(F + nameoff_field + no)
        if nm:
            hits[F] = nm
    return hits


def runs_of(hits, stride):
    out = []
    keys = sorted(hits)
    cur = []
    for F in keys:
        if cur and F == cur[-1] + stride:
            cur.append(F)
        else:
            if len(cur) >= 40:
                out.append(cur)
            cur = [F]
    if len(cur) >= 40:
        out.append(cur)
    return out


if os.path.exists(CACHE):
    cache = json.load(open(CACHE))
    hits8 = {int(k): v for k, v in cache["h8"].items()}
    hits12 = {int(k): v for k, v in cache["h12"].items()}
    print("[*] cache loaded")
else:
    print("[*] scanning for stride-8 structs ...")
    hits8 = scan_entries(4)
    print("    hits=%d" % len(hits8))
    # name_offset is the 2nd int32 in every supported layout, so one scan
    # serves both strides; only the run detection stride differs.
    hits12 = hits8
    json.dump({"h8": {str(k): v for k, v in hits8.items()},
               "h12": {str(k): v for k, v in hits12.items()}}, open(CACHE, "w"))

trusted = json.load(open(TRUSTED))
print("[*] trusted vendor CRCs: %d" % len(trusted))

final = {}
summary = []

for stride, hits in ((8, hits8), (12, hits12)):
    for run in runs_of(hits, stride):
        syms = [hits[F] for F in run]
        idx = {nm: i for i, nm in enumerate(syms)}
        known = [(idx[nm], nm, trusted[nm]) for nm in syms if nm in trusted]
        if len(known) < 5:
            print("[-] run @0x%x stride=%d entries=%d known=%d (skip)"
                  % (run[0], stride, len(syms), len(known)))
            continue
        print("[*] run @0x%x stride=%d entries=%d known=%d  first=%s"
              % (run[0], stride, len(syms), len(known), syms[0]))

        # candidate bases derived from each known CRC occurrence
        cand = {}
        for i, nm, crc in known[:400]:
            pat = struct.pack("<I", crc)
            pos = BLOB.find(pat)
            cnt = 0
            while pos >= 0 and cnt < 4:
                base = pos - 4 * i
                if base >= 0:
                    cand[base] = cand.get(base, 0) + 1
                pos = BLOB.find(pat, pos + 1)
                cnt += 1

        best = None
        for base, votes in cand.items():
            if base + 4 * len(syms) > N:
                continue
            score = 0
            for i, nm, crc in known:
                if struct.unpack_from("<I", BLOB, base + 4 * i)[0] == crc:
                    score += 1
            if best is None or score > best[0]:
                best = (score, base)
        if not best:
            print("    no candidate base")
            continue

        score, base = best
        ratio = score / len(known)
        print("    kcrctab base=0x%x  verified %d/%d (%.1f%%)"
              % (base, score, len(known), ratio * 100))
        if ratio < 0.9:
            print("    [skip] confidence too low")
            continue

        got = 0
        for i, nm in enumerate(syms):
            crc = struct.unpack_from("<I", BLOB, base + 4 * i)[0]
            if nm not in final:
                final[nm] = crc
                got += 1
        summary.append((stride, run[0], len(syms), base, score, len(known)))
        print("    added %d new symbols" % got)

json.dump(final, open(OUT, "w"), indent=0, sort_keys=True)
print("=" * 66)
print("[+] authoritative CRCs recovered: %d -> %s" % (len(final), OUT))
print("[*] trusted set coverage: %d/%d symbols present"
      % (len([k for k in trusted if k in final]), len(trusted)))

missing = [k for k in trusted if k not in final][:10]
if missing:
    print("[*] sample trusted symbols not found by image scan: %s" % missing)

for probe in ("module_layout", "printk", "cfg80211_get_channel",
              "usb_register_driver", "ieee80211_get_channel", "netif_rx",
              "kmalloc_caches", "register_netdevice"):
    v = final.get(probe)
    t = trusted.get(probe)
    print("    %-24s image=%s trusted=%s"
          % (probe, ("%08x" % v) if v is not None else "MISSING",
             ("%08x" % t) if t else "n/a"))