# Published once per outage, right after the link recovers.
# An outage = first failed probe (no reply within timeout) until the next reply.
std_msgs/Header header
string target
float32 duration_sec   # how long the outage lasted (first failure -> recovery)
uint32 outage_count    # which outage this is (running count since node start)
