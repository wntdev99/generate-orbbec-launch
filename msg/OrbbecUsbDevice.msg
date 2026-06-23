# A single Orbbec USB camera as seen on the USB bus (read from sysfs).
string serial            # device serial number ("" if unreadable)
string product           # USB product string
string usb_port          # sysfs bus id, e.g. "3-9" (matches the orbbec usb_port launch arg)
string device_path       # full sysfs path, e.g. "/sys/bus/usb/devices/3-9"
string id_vendor         # 4-hex vendor id, e.g. "2bc5"
string id_product        # 4-hex product id
uint32 speed_mbps        # negotiated link speed in Mbit/s (e.g. 480, 5000)
string usb_generation    # human-readable, e.g. "USB 3.2 Gen1 (5 Gbps)"
string bcd_usb           # bcdUSB / sysfs "version" field, e.g. "3.10"
bool below_usb3          # true if 0 < speed_mbps < 5000 (likely bandwidth-limited link)
bool present             # true if currently on the bus; false = last-known snapshot of a now-disconnected camera
uint32 connect_count     # times (re)connected since node start (0 if present since start)
uint32 disconnect_count  # times disconnected since node start
# NOTE: when present=false the link fields (speed_mbps, usb_generation, below_usb3)
#       are last-known values; only present/connect_count/disconnect_count are live.
