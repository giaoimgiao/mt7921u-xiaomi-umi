#!/system/bin/sh
# Tear the MT7921U stack down again (reverse dependency order).
# Nothing persistent is involved, so after this the phone is exactly as before.

D=/data/local/tmp/mtwifi

for m in mt7921u mt7921-common mt76-connac-lib mt76-usb mt76 mac80211; do
	printf '   %-18s ' "$m"
	rmmod "$m" 2>/dev/null && echo removed || echo "not loaded"
done

echo "--- clear firmware search path ---"
echo "" > /sys/module/firmware_class/parameters/path

echo "--- remaining mt76/mac80211 modules ---"
lsmod | grep -E 'mac80211|mt76|mt7921' || echo "   none"