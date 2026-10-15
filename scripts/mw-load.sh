#!/system/bin/sh
# Bring up the MT7921U USB Wi-Fi stack on this device.
#
# Safety contract:
#   * loads from /data/local/tmp only, nothing outside /data/ or /sdcard is touched
#   * no boot-time hook, no Magisk module, no init.rc change -> disappears on reboot
#   * aborts early if the adapter is not properly enumerated, so we never feed a
#     half-enumerated device into the driver
#
# Run:  su -c sh /data/local/tmp/mtwifi/mw-load.sh

D=/data/local/tmp/mtwifi
DEV=/sys/bus/usb/devices/1-1

echo "--- 1. adapter presence ---"
if [ ! -e "$DEV/idVendor" ]; then
	echo "!! adapter not on the USB bus yet."
	echo "   fix the OTG power chain first (powered hub / better cable), then retry."
	exit 1
fi
echo "   vendor=$(cat $DEV/idVendor) product=$(cat $DEV/idProduct)"

echo "--- 2. firmware search path (runtime module parameter) ---"
echo "$D/fw" > /sys/module/firmware_class/parameters/path
cat /sys/module/firmware_class/parameters/path

echo "--- 3. load module stack (dependency order) ---"
for m in mac80211 mt76 mt76-usb mt76-connac-lib mt7921-common mt7921u; do
	printf '   %-18s ' "$m"
	insmod "$D/$m.ko" && echo ok || { echo FAILED; exit 1; }
done

echo "--- 4. keep the link awake (a suspended dongle drops off the bus) ---"
echo -1 > "$DEV/power/autosuspend_delay_ms" 2>/dev/null
echo on > "$DEV/power/control" 2>/dev/null

echo "--- 5. result ---"
sleep 3
dmesg | grep -iE 'mt7921|mt76|ieee80211|phy[0-9]|firmware' | tail -15
echo "--- netdevs ---"
ls /sys/class/net/ | tr '\n' ' '; echo
echo "--- wireless phys ---"
ls /sys/class/ieee80211/ 2>/dev/null | tr '\n' ' '; echo