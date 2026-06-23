# Snapshot of all Orbbec USB cameras known to the monitor at a point in time.
# `devices` includes every camera seen since node start: currently connected
# ones (present=true) AND previously seen, now-disconnected ones (present=false),
# so per-camera connect/disconnect counts stay observable across unplug events.
std_msgs/Header header
uint32 count             # number of CURRENTLY connected cameras (present=true entries)
OrbbecUsbDevice[] devices
