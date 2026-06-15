# Signal of the router's WiFi WAN (uplink) link, read from the router via SSH.
# Useful on machines that are WIRED to the router (no own dBm) but whose
# internet path goes through the router's wireless uplink.
std_msgs/Header header
bool reachable           # true if the router query succeeded
string iface             # router interface queried (e.g. "sta1")
string essid             # upstream AP SSID the router is connected to
int32 signal_dbm         # uplink signal in dBm (0 if unknown)
int32 noise_dbm          # noise floor in dBm (0 if unknown)
int32 quality            # link quality numerator
int32 quality_max        # link quality denominator
float32 bitrate_mbps     # negotiated bit rate (Mbit/s)
