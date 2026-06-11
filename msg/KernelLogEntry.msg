# A single camera/USB-related kernel log line, sourced from the systemd journal.
std_msgs/Header header   # header.stamp = time the line was published
uint8 priority           # syslog priority: 0=emerg 1=alert 2=crit 3=err 4=warning 5=notice 6=info 7=debug
string priority_label     # human-readable priority (e.g. "warning")
uint64 realtime_us        # kernel __REALTIME_TIMESTAMP, microseconds since epoch (0 if unknown)
string message            # the kernel log text
string matched_keyword    # the configured keyword that matched (lowercased)
