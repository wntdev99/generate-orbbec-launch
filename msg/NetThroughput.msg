# Throughput of one network interface, sampled at a fixed rate.
# Read from /sys/class/net/<iface>/statistics (no root required).
std_msgs/Header header
string iface           # interface name (auto-detected egress, or configured)
uint64 rx_bytes        # cumulative received bytes
uint64 tx_bytes        # cumulative transmitted bytes
float64 rx_bps         # receive rate since last sample (bytes/sec)
float64 tx_bps         # transmit rate since last sample (bytes/sec)
