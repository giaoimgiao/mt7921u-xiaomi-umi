# Findings — how the ABI and the source baseline were pinned down

Two things made this bring-up possible. Both are reusable whenever you must build
kernel modules for a vendor kernel you cannot rebuild.

---

## 1. Recovering the kernel's authoritative module-CRC table

### Problem

With `CONFIG_MODVERSIONS=y` the kernel checks every imported symbol against a
32-bit CRC that was computed *at kernel build time* by `genksyms` from the
preprocessed type text. A module built from different headers — or even with a
different compiler — gets different CRCs and is rejected with
`disagrees about version of symbol X`.

The kernel does not expose that table:

* `/proc/kallsyms` deliberately filters the `__crc_*`, `__ksymtab_*`,
  `__kcrctab_*` prefixes, so the values are simply not listed;
* `CONFIG_PROC_KCORE` is off, so there is no way to read kernel memory;
* `kptr_restrict=2`, so even addresses are hidden.

### What works

**a) Mine the modules that are already loaded.** Every vendor `.ko` carries a
`__versions` section: `(crc, name)` for everything it imports. Those modules were
accepted by this very kernel, so their CRCs are correct by construction.

```
tools/extract_versions.py   →  42 modules, 3313 entries, 1151 unique symbols
```

That is enough to *verify* a reconstruction, but not enough to *build* with
(mac80211 + mt76 need ~300 symbols, the vendor modules cover only a subset).

**b) Reconstruct the full table out of the boot image.** The `__ksymtab` array and
the `__kcrctab` array are parallel and in the same order, so pairing them requires
no symbol table:

```
entry[i] = { int value_offset; int name_offset; }   /* 4.19, 8 bytes */
name_address = &entry.name_offset + entry.name_offset
```

Because the image is loaded contiguously, the virtual base cancels out and the
test becomes a pure *file-offset* check:

```
T = F + 4 + name_offset        # must land on a valid, known symbol name
```

So `tools/scan_ksymtab.py` can locate the array and its CRC partner with nothing
but the raw `Image` (unpacked from `boot.img` with `magiskboot`) plus the symbol
names from `/proc/kallsyms`.

Identification of the CRC array is self-calibrating: candidate bases are derived
from the known-good vendor CRCs at their index positions, then each candidate is
scored against *all* known CRCs, so a wrong base cannot survive.

```
run @0x25c6cd8  stride=8  entries=12385
kcrctab base=0x25defe0    verified 1094/1094 (100.0%)
module_layout   image=eacc760d   trusted=eacc760d   ✓
```

1094 of the 1151 trusted CRCs were found by the scan and **all of them matched**;
the 57 that are "missing" are exported *by* vendor modules (audio/bolero/qca
helpers), which are correctly absent from the kernel's own table.

**c) Never trust computed CRCs on this kernel.** `genksyms` hashes the
*preprocessed* type text, which depends on the compiler's macro expansion
(`compiler-gcc.h` vs `compiler-clang.h`), so GCC and clang produce different CRCs
for identical headers. The shipped kernel was built with clang 10.0.6; building
the same `cfg80211` with GCC 13 gave a 12% agreement rate **for the same source**.
The consequence is that CRC equality can only be used to compare two builds made
with the *same* compiler — and that a computed table must never be used to load
modules. Inject the extracted table instead.

---

## 2. Finding the source baseline the kernel was actually built from

The phone reports `4.19.113`, but that says nothing about *whose* 4.19 it is. Two
candidate trees were built and compared **by exported symbol set**, which is
compiler-independent:

| tree | wireless exports | present in kernel | exported but kernel lacks | kernel exports but tree lacks |
|---|---|---|---|---|
| mainline 4.19.113 | 96 | 93 | 3 (`cfg80211_find_ie_match`, `cfg80211_find_vendor_ie`, `ieee80211_bss_get_ie`) | 5 |
| Xiaomi `umi-q-oss` | 97 | **97** | **0** | 1 (`cfg80211_send_layer2_update`) |

The clincher is not the count but *which* names: the running kernel's kallsyms
contains `cfg80211_find_elem_match`, `cfg80211_find_vendor_elem` and
`ieee80211_bss_get_elem` — the post-5.x names of those three APIs. The vendor tree
contains **both** spellings (the old ones as inline wrappers, which is why they
never appear as symbols), which is the fingerprint of a backported wireless stack.

Corroboration: building `mac80211` from mainline 4.19.113 leaves 2 unresolved
symbols, from the vendor tree **0**.

Result: the correct baseline is `MiCode/Xiaomi_Kernel_OpenSource`, branch
`umi-q-oss`, with `SUBLEVEL` set to 113 and the device's own `config.gz` so the
resulting vermagic matches byte for byte:

```
4.19.113-perf-gec90c723c482 SMP preempt mod_unload modversions aarch64
```

(`CONFIG_LOCALVERSION_AUTO=y` in the vendor config means the `-g<hash>` suffix
comes from git; hardcode it via `CONFIG_LOCALVERSION` instead.)

---

## 3. Down-porting mt76 (~5.19/6.1 era) to this mac80211

`mt7921u` only exists in trees that assume a much newer mac80211. The patch series
in `patches/` removes or replaces, in order of discovery:

| area | what was done |
|---|---|
| LED/WED | local inert `mtk_wed` stub header; WED is MMIO/PCIe-only |
| SAR | cfg80211 SAR API (5.1+) compiled out, `mt76_get_sar_power` becomes a passthrough |
| 6 GHz | band identifier never registered; station/TLV code paths removed |
| MBSSID | support code removed (5.1+ API) |
| HE caps | missing masks defined with upstream bit positions; renamed fields mapped |
| TXQ scheduling | rewritten from the 5.x pull model (`ieee80211_next_txq`) to the 4.19 push model (`drv_wake_tx_queue` + `ieee80211_tx_dequeue`), iterating vif/station txqs instead of keeping a txq list |
| RX | batched `ieee80211_rx_list()` → per-skb `ieee80211_rx_napi()` |
| hardware RX header translation | the driver *defaults to enabling it* (`MT_MDP_DCR0_RX_HDR_TRANS_EN`); with it on the firmware hands up 802.3 frames, which a 4.19 mac80211 cannot parse — it is switched off, which restores the plain 802.11 path the driver also supports |
| devcoredump / crypto / nla / of_net | missing helpers either stubbed locally or the call site removed |
| WED, PCI, SDIO, other chips | not built: this target is USB only |

Triage helper: `tools/inventory.py` turns a build log into a list of missing
constants / struct members / functions, which is how the five patch rounds were
driven instead of fixing errors one at a time.
