# data/

Two derived tables, both regenerable in a couple of minutes with `tools/`.
They are included so that a Mi 10 on the *same ROM* does not have to redo the
extraction step.

| file | what it is | provenance |
|---|---|---|
| `kernel_crc.json` | 12,385 `symbol -> crc32` pairs = the running kernel's own `__kcrctab`, i.e. the exact values `CONFIG_MODVERSIONS` enforces | extracted from the `Image` inside `boot.img` (MIUI 12.5 V12.5.10.0.RJBCNXM, kernel `4.19.113-perf-gec90c723c482`) by `tools/scan_ksymtab.py`; verified **1094/1094** against the CRC values mined from the 42 already-loaded vendor modules |
| `vendor_module_crcs.json` | 1,151 `symbol -> crc32` pairs mined from the `__versions` section of `/vendor/lib/modules/*.ko` | `tools/extract_versions.py`; these modules were accepted by this very kernel, so they are trusted by construction |

## Regenerate

```sh
# on the device
zcat /proc/config.gz > config.txt
awk '{print $3}' /proc/kallsyms | sort -u > kallsyms_names.txt
mkdir vendor_ko && cp /vendor/lib/modules/*.ko vendor_ko/     # needs root
dd if=/dev/block/by-name/boot of=boot.img                      # needs root
magiskboot unpack boot.img            # -> kernel (raw arm64 Image)

# on the build host
KO_DIR=vendor_ko python3 tools/extract_versions.py
IMG=kernel NAMES=kallsyms_names.txt python3 tools/scan_ksymtab.py
```

`scan_ksymtab.py` prints its own confidence line; if it does not say
`verified N/N (100.0%)`, do not use the output.

## Warning

`kernel_crc.json` is bound to **one kernel build**. A ROM update changes the
kernel, which invalidates every CRC in this file. Regenerate it from the new
`boot.img`; loading a stale table will be rejected by the kernel (or worse,
accepted with a mismatched ABI).
