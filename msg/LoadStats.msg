# Live statistics for a load_generator / load_sink node.
# Published periodically while idle or running.
std_msgs/Header header
string job_id          # active job id ('' when idle)
string mode            # ros_pub | tcp | udp | iperf3 | sink | idle
string target          # resolved host/ip, or 'ros_topic' for ros_pub, or listen spec for sink
bool running           # true while a job/sink is actively moving bytes
float64 tx_bps         # transmit rate over last sample (bytes/sec)
float64 rx_bps         # receive rate over last sample (bytes/sec)
uint64 bytes_total     # cumulative bytes for the current job (tx for generator, rx for sink)
uint64 msgs_total      # cumulative messages/datagrams/segments
uint32 errors          # cumulative error count for the current job
string detail          # free-form note (engine summary, last error, iperf3 result, ...)
