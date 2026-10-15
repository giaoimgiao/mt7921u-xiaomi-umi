#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_versions.py
Extract module version (CRC) tables from ELF .ko objects.

Rationale: with CONFIG_MODVERSIONS=y the running kernel only accepts a module
whose __versions entries match its own kcrctab byte-for-byte. Modules that are
already shipped by the vendor have been accepted by this very kernel, so their
__versions tables are an authoritative (symbol -> crc32) reference set.

Layout parsed (64-bit LE, kernel 4.19):
    struct modversion_info { unsigned long crc; char name[56]; }  -> 64 bytes
"""
import json
import os
import struct
import sys

KO_DIR = os.environ.get("KO_DIR", "vendor_ko")
OUT_JSON = os.environ.get("OUT_JSON", "crc_dict.json")
OUT_TXT = os.environ.get("OUT_TXT", "crc_dict.txt")
MODULE_NAME_LEN = 56
ENTRY_SIZE = 8 + MODULE_NAME_LEN  # 64


def read_elf_sections(path):
    """Return (sections, sec_names) using raw ELF64 parsing (no external deps)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"\x7fELF":
        raise ValueError("not ELF")
    if data[4] != 2:  # ELFCLASS64
        raise ValueError("not ELF64")
    if data[5] != 1:  # little endian
        raise ValueError("not LE")
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3E)[0]
    if e_shoff == 0 or e_shnum == 0:
        raise ValueError("no section headers")

    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        name, stype, flags, addr, offset, size = struct.unpack_from("<IIQQQQ", data, off)
        secs.append({"name_off": name, "type": stype, "addr": addr,
                     "offset": offset, "size": size})

    # string table for section names
    strtab = secs[e_shstrndx]
    stroff = strtab["offset"]

    def get_name(n):
        end = data.index(b"\x00", stroff + n)
        return data[stroff + n:end].decode("utf-8", "replace")

    names = [get_name(s["name_off"]) for s in secs]
    return data, secs, names


def main():
    files = sorted(f for f in os.listdir(KO_DIR) if f.endswith(".ko"))
    if not files:
        print("[!] no .ko found in %s" % KO_DIR)
        return 1

    crc = {}          # symbol -> crc
    owner = {}        # symbol -> first ko that carries it
    vermagic = {}
    per_file = {}
    n_entries_total = 0

    for fn in files:
        path = os.path.join(KO_DIR, fn)
        try:
            data, secs, names = read_elf_sections(path)
        except Exception as e:
            print("[!] %-28s parse fail: %s" % (fn, e))
            continue

        vers = None
        modinfo = None
        for s, n in zip(secs, names):
            if n == "__versions":
                vers = s
            elif n == ".modinfo":
                modinfo = s

        # vermagic proves this object belongs to the running kernel ABI
        vm = ""
        if modinfo:
            blob = data[modinfo["offset"]:modinfo["offset"] + modinfo["size"]]
            for part in blob.split(b"\x00"):
                if part.startswith(b"vermagic="):
                    vm = part[9:].decode("utf-8", "replace")
        vermagic[fn] = vm

        if not vers or vers["size"] == 0:
            per_file[fn] = 0
            continue

        cnt = vers["size"] // ENTRY_SIZE
        per_file[fn] = cnt
        n_entries_total += cnt

        base = vers["offset"]
        for i in range(cnt):
            off = base + i * ENTRY_SIZE
            crc_val = struct.unpack_from("<Q", data, off)[0]
            raw = data[off + 8: off + 8 + MODULE_NAME_LEN]
            nm = raw.split(b"\x00")[0].decode("utf-8", "replace")
            if not nm:
                continue
            if nm not in crc:
                crc[nm] = crc_val & 0xFFFFFFFF
                owner[nm] = fn

    with open(OUT_JSON, "w") as f:
        json.dump(crc, f, indent=0, sort_keys=True)

    with open(OUT_TXT, "w") as f:
        f.write("# symbol\tcrc32\tsource_ko\n")
        for k in sorted(crc):
            f.write("%s\t%08x\t%s\n" % (k, crc[k], owner[k]))

    print("=" * 62)
    print("modules parsed        : %d" % len(files))
    print("__versions entries    : %d" % n_entries_total)
    print("unique symbols (dict) : %d" % len(crc))
    print("=" * 62)

    # ABI sanity: do all vendor modules agree on vermagic?
    uniq_vm = {}
    for fn, vm in vermagic.items():
        uniq_vm.setdefault(vm, []).append(fn)
    print("vermagic variants: %d" % len(uniq_vm))
    for vm, fl in uniq_vm.items():
        print("  [%d ko] %s" % (len(fl), vm))

    print("=" * 62)
    for prefix in ("cfg80211_", "ieee80211_", "mac80211", "nl80211_", "wiphy",
                   "regulatory", "module_layout", "usb_", "netif_", "skb_"):
        hit = [k for k in crc if k.startswith(prefix)]
        print("  %-14s %5d symbols in dict" % (prefix, len(hit)))

    print("=" * 62)
    print("top 8 richest modules (by __versions count):")
    for fn, c in sorted(per_file.items(), key=lambda kv: -kv[1])[:8]:
        print("  %-28s %6d" % (fn, c))

    return 0


if __name__ == "__main__":
    sys.exit(main())
