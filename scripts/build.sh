#!/bin/sh
# build.sh — end-to-end build of mac80211 + the mt76/mt7921u stack for the
# Xiaomi Mi 10 (umi) vendor kernel 4.19.113-perf-gec90c723c482.
#
# Inputs you must supply (see README.md):
#   WORK=<workdir>          scratch directory (a few GB)
#   CONFIG_TXT=config.txt   zcat /proc/config.gz, pulled from the device
#   KALLSYMS=kallsyms.txt   awk '{print $3}' /proc/kallsyms | sort -u
#   IMAGE=kernel            the raw Image unpacked from boot.img (magiskboot unpack)
#   TREE=<kernel tree>      MiCode/Xiaomi_Kernel_OpenSource @ umi-q-oss
#
# Nothing here touches the device; loading is scripts/mw-load.sh.

set -e

: "${WORK:=$PWD/work}"
: "${CONFIG_TXT:=$PWD/config.txt}"
: "${KALLSYMS:=$PWD/kallsyms.txt}"
: "${IMAGE:=$PWD/kernel}"
: "${TREE:=$WORK/kernel}"
: "${MT76_URL:=https://github.com/openwrt/mt76/archive/refs/heads/openwrt-22.03.tar.gz}"

HERE=$(cd "$(dirname "$0")/.." && pwd)
export IMG="$IMAGE" NAMES="$KALLSYMS" OUT="$WORK/kernel_crc.json"
export TRUSTED="$WORK/crc_dict.json" CONFIG_TXT

mkdir -p "$WORK"

echo "== 1/6 trusted CRCs from the shipped modules =="
if [ ! -f "$WORK/crc_dict.json" ]; then
	if [ -n "$KO_DIR" ]; then
		OUT_JSON="$WORK/crc_dict.json" OUT_TXT="$WORK/crc_dict.txt" \
			python3 "$HERE/tools/extract_versions.py"
	else
		echo "   set KO_DIR=<copy of /vendor/lib/modules> and re-run" >&2
		exit 1
	fi
fi

echo "== 2/6 authoritative CRC table from the kernel image =="
python3 "$HERE/tools/scan_ksymtab.py"

echo "== 3/6 kernel tree =="
if [ ! -d "$TREE" ]; then
	git clone --depth=1 -b umi-q-oss \
		https://github.com/MiCode/Xiaomi_Kernel_OpenSource.git "$TREE"
fi
# the shipped kernel is 4.19.113 while the OSS branch is 4.19.81: align the
# release string so the module vermagic matches the device byte for byte
sed -i 's/^SUBLEVEL = 81$/SUBLEVEL = 113/' "$TREE/Makefile"
sed -i 's|^CC\t\t= \$(PYTHON) \$(srctree)/scripts/gcc-wrapper.py \$(REAL_CC)|CC\t\t= $(REAL_CC)|' \
	"$TREE/Makefile" || true
sed -i 's/^PYTHON\t\t= python$/PYTHON\t\t= python3/' "$TREE/Makefile" || true
sed -i 's|-Werror||' "$TREE/scripts/gcc-wrapper.py" 2>/dev/null || true

echo "== 4/6 mt76 snapshot + backport patch =="
if [ ! -d "$WORK/mt76-src" ]; then
	curl -L "$MT76_URL" | tar xz -C "$WORK"
	mv "$WORK"/mt76-openwrt-22.03 "$WORK/mt76-src"
fi
rm -rf "$TREE/drivers/net/wireless/mediatek/mt76"
cp -a "$WORK/mt76-src" "$TREE/drivers/net/wireless/mediatek/mt76"
( cd "$TREE/drivers/net/wireless/mediatek/mt76" && \
  patch -p2 < "$HERE/patches/mt76-4.19-backport.patch" )

echo "== 5/6 .config, Module.symvers, prepare =="
python3 "$HERE/tools/prep_config.py" "$TREE"
( cd "$TREE" && make ARCH=arm64 olddefconfig && make ARCH=arm64 modules_prepare -j"$(nproc)" )
python3 "$HERE/tools/gen_symvers.py" "$TREE"

echo "== 6/6 build =="
( cd "$TREE" && make ARCH=arm64 M=net/mac80211 modules -j"$(nproc)" )
# mac80211 exports have to be visible to the mt76 build
cat "$TREE/net/mac80211/Module.symvers" >> "$TREE/Module.symvers"
( cd "$TREE" && make ARCH=arm64 M=drivers/net/wireless/mediatek/mt76 modules -j"$(nproc)" )

echo
echo "artifacts:"
echo "  $TREE/net/mac80211/mac80211.ko"
find "$TREE/drivers/net/wireless/mediatek/mt76" -name '*.ko' | sort
echo
echo "check vermagic before loading:"
echo "  strings <file>.ko | grep vermagic="
echo "expected: 4.19.113-perf-gec90c723c482 SMP preempt mod_unload modversions aarch64"