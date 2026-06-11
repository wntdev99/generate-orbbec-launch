#!/bin/bash
set -euo pipefail

# Define the vendor ID for Orbbec devices
VID="2bc5"

# --- 1. Enumerate all connected Orbbec devices (serial + USB port) ---
declare -a SERIALS PORTS
for dev in /sys/bus/usb/devices/*; do
    [ -e "$dev/idVendor" ] || continue
    [ "$(cat "$dev/idVendor")" == "$VID" ] || continue
    serial=$(cat "$dev/serial" 2>/dev/null || true)
    [ -n "$serial" ] || continue
    busid=$(basename "$dev")

    # Skip duplicate serials (a device may expose multiple sysfs nodes)
    dup=0
    for s in "${SERIALS[@]:-}"; do
        if [ "$s" == "$serial" ]; then dup=1; break; fi
    done
    if [ "$dup" -eq 1 ]; then continue; fi

    SERIALS+=("$serial")
    PORTS+=("$busid")
done

count=${#SERIALS[@]}
if [ "$count" -eq 0 ]; then
    echo "No Orbbec (VID $VID) devices found. Check the connections and try again." >&2
    exit 1
fi

echo "Detected $count Orbbec camera(s):"
for i in "${!SERIALS[@]}"; do
    printf "  [%d] serial=%s  usb_port=%s\n" "$i" "${SERIALS[$i]}" "${PORTS[$i]}"
done
echo

# --- 2. Interactively assign a name to each detected camera ---
declare -a NAMES
declare -A NAME_SEEN
for i in "${!SERIALS[@]}"; do
    while true; do
        printf "Camera [%d]  serial=%s  usb_port=%s\n" "$i" "${SERIALS[$i]}" "${PORTS[$i]}"
        read -rp "  Enter a name for this camera (e.g. front_camera): " name
        name=$(echo "$name" | xargs)  # trim surrounding whitespace
        if [ -z "$name" ]; then
            echo "  Name cannot be empty."
            continue
        fi
        if [ -n "${NAME_SEEN[$name]:-}" ]; then
            echo "  Name '$name' is already used. Choose another."
            continue
        fi
        NAMES+=("$name")
        NAME_SEEN[$name]=1
        break
    done
done
echo

# --- 3. Select the PRIMARY camera (software_triggering) ---
echo "Which camera is the PRIMARY (software_triggering)? The rest use hardware_triggering."
for i in "${!NAMES[@]}"; do
    printf "  [%d] %s  (serial=%s)\n" "$i" "${NAMES[$i]}" "${SERIALS[$i]}"
done
while true; do
    read -rp "Enter the index of the primary camera: " primary_idx
    if [[ "$primary_idx" =~ ^[0-9]+$ ]] && [ "$primary_idx" -ge 0 ] && [ "$primary_idx" -lt "$count" ]; then
        break
    fi
    echo "  Invalid index. Enter a number between 0 and $((count - 1))."
done
echo

# --- 4. Generate the launch file ---
OUTPUT="multi_camera_synced.launch.py"

cat > "$OUTPUT" << 'EOF'
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    package_dir = get_package_share_directory('orbbec_camera')
    launch_file_dir = os.path.join(package_dir, 'launch')
    config_file_dir = os.path.join(package_dir, 'config')
    config_file_path = os.path.join(config_file_dir, 'camera_params.yaml')

EOF

# One IncludeLaunchDescription block per camera
for i in "${!NAMES[@]}"; do
    if [ "$i" -eq "$primary_idx" ]; then
        sync_mode="software_triggering"
    else
        sync_mode="hardware_triggering"
    fi
    cat >> "$OUTPUT" << EOF
    cam_${i} = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_file_dir, 'gemini_330_series.launch.py')
        ),
        launch_arguments={
            'camera_name': '${NAMES[$i]}',
            'usb_port': '${PORTS[$i]}',
            'device_num': '${count}',
            'sync_mode': '${sync_mode}',
            'config_file_path': config_file_path
        }.items()
    )

EOF
done

# LaunchDescription: secondaries first, primary launched last via TimerAction
{
    echo "    ld = LaunchDescription(["
    for i in "${!NAMES[@]}"; do
        if [ "$i" -eq "$primary_idx" ]; then continue; fi
        echo "        GroupAction([cam_${i}]),"
    done
    echo "        TimerAction(period=3.0, actions=[GroupAction([cam_${primary_idx}])]), # The primary camera should be launched at last"
    echo "    ])"
    echo ""
    echo "    return ld"
} >> "$OUTPUT"

echo "Launch file '$OUTPUT' has been generated for $count camera(s) (primary: ${NAMES[$primary_idx]})."
