# tools/

Five small scripts. Together they answer the two questions that gate any
out-of-tree module on a vendor kernel: *what ABI does this kernel want?* and
*which source tree does it come from?*

All of them run with plain `python3` (no external packages).

| script | input | output |
|---|---|---|
| `extract_versions.py` | vendor `.ko` files (e.g. `/vendor/lib/modules/*.ko`) | `crc_dict.json` — trusted `(symbol, crc)` pairs mined from `__versions` |
| `scan_ksymtab.py` | raw kernel `Image` + `/proc/kallsyms` names + `crc_dict.json` | `kernel_crc.json` — **the authoritative table**, calibrated and verified against the trusted set |
| `diff_exports.py` | two `Module.symvers` files | symbol-set and CRC comparison vs the kernel — tells you if your tree is the right one |
| `gen_symvers.py <tree>` | `kernel_crc.json` | `<tree>/Module.symvers` that modpost will embed verbatim |
| `prep_config.py` | `/proc/config.gz` from the device | `.config` with the exact vermagic, plus the target module options |
| `inventory.py <build.log>` | a compiler log | grouped list of missing constants / struct members / functions |

## Order of operations

```sh
# on the device
zcat /proc/config.gz                 > config.txt
awk '{print $3}' /proc/kallsyms | sort -u > kallsyms_names.txt
magiskboot unpack boot.img           # gives you the raw 'kernel' Image

# on the build host
python3 extract_versions.py          # mine the shipped modules
python3 scan_ksymtab.py              # reconstruct + verify the CRC table
python3 prep_config.py               # .config for the target kernel
python3 gen_symvers.py <tree>        # Module.symvers for the build
python3 diff_exports.py <tree>/net/wireless/Module.symvers   # sanity check
```

## Two things that bite people

* **Do not use CRCs computed by your own compiler.** `genksyms` hashes
  preprocessed type text, and the kernel headers expand differently under GCC and
  clang. If the shipped kernel was built with clang and you build with GCC, even a
  byte-identical header gives a different CRC. Always inject the *extracted* table.
* **A `Module.symvers` is valid for exactly one kernel build.** Any OTA that
  changes the kernel invalidates it; regenerate from the new boot image.

## Calibration trick used by `scan_ksymtab.py`

`__ksymtab` and `__kcrctab` are parallel arrays, but neither is named in a raw
`Image` (no section headers). The pairing is found by:
1. scanning for entries whose `name_offset` resolves to a known symbol name, using
   the fact that in a contiguous image the base address cancels out
   (`name_file_off = entry_off + 4 + name_offset`);
2. taking the trusted vendor CRCs, looking at their *index* inside the run, and
   deriving candidate CRC-array bases from `(occurrence - 4 * index)`;
3. scoring every candidate against the whole trusted set — a wrong base cannot
   survive that, and the winner prints its own confidence
   (`verified 1094/1094`).