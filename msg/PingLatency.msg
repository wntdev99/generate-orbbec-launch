# One latency sample to a target, published at a fixed rate (default 1 Hz).
std_msgs/Header header
string target          # ping target, e.g. "8.8.8.8"
bool valid             # true if a reply arrived within timeout_sec
float32 rtt_ms         # round-trip time in ms; NaN when invalid (no reply / down)
uint32 outage_count    # running number of outages since node start
