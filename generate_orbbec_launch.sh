#!/bin/bash
set -euo pipefail

# Define the vendor ID for Orbbec devices
VID="2bc5"

# --- Parse arguments ---
DRY_RUN=0
NO_SYNC=0
ASYNC_MODE="standalone"  # default mode when --no-sync is used
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --no-sync) NO_SYNC=1 ;;
        --no-sync=*)
            NO_SYNC=1
            ASYNC_MODE="${arg#--no-sync=}"
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--no-sync[=standalone|free_run]]"
            echo "  --dry-run   Use a fake device list to walk through the flow without"
            echo "              any hardware connected (no sysfs access)."
            echo "  --no-sync   Generate an UNsynchronized config: every camera runs"
            echo "              independently, with no primary and no trigger wiring."
            echo "              Default mode is 'standalone' (color/depth synced within"
            echo "              each device). Use --no-sync=free_run for fully free run."
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--dry-run] [--no-sync[=standalone|free_run]]" >&2
            exit 1
            ;;
    esac
done

# Validate the async mode value
if [ "$NO_SYNC" -eq 1 ]; then
    case "$ASYNC_MODE" in
        standalone|free_run) ;;
        *)
            echo "Invalid --no-sync mode '$ASYNC_MODE'. Use 'standalone' or 'free_run'." >&2
            exit 1
            ;;
    esac
fi

# --- 1. Enumerate all connected Orbbec devices (serial + USB port) ---
declare -a SERIALS PORTS
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] Using a fake device list; no hardware required, no sysfs access."
    echo
    SERIALS=("CP3S34D00051" "CP3L44P00047" "CP3L44P0005Y" "CP3L44P00054")
    PORTS=("2-1.1" "2-1.2" "2-1.3" "2-1.4")
else
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
fi

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
        # Trim surrounding whitespace (parameter expansion -> safe with any input)
        name="${name#"${name%%[![:space:]]*}"}"
        name="${name%"${name##*[![:space:]]}"}"
        if [ -z "$name" ]; then
            echo "  Name cannot be empty."
            continue
        fi
        # Must be a valid ROS 2 name: starts with a letter, then letters/digits/underscores.
        # This also prevents quotes/$/backticks from breaking (or injecting into) the generated file.
        if [[ ! "$name" =~ ^[a-zA-Z][a-zA-Z0-9_]*$ ]]; then
            echo "  Invalid name '$name'. Use letters, digits and underscores only, starting with a letter."
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
# In --no-sync mode there is no primary: every camera runs independently.
primary_idx=-1
if [ "$NO_SYNC" -eq 1 ]; then
    echo "[no-sync] Asynchronous mode: every camera uses sync_mode='${ASYNC_MODE}'. No primary, no trigger wiring."
    echo
else
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
fi

# --- 4. Generate the launch file ---
OUTPUT="multi_camera_synced.launch.py"

# Confirm before overwriting an existing file
if [ -e "$OUTPUT" ]; then
    read -rp "'$OUTPUT' already exists in $(pwd). Overwrite? [y/N]: " ans
    case "$ans" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted; existing file kept."; exit 0 ;;
    esac
fi

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
    if [ "$NO_SYNC" -eq 1 ]; then
        sync_mode="$ASYNC_MODE"
    elif [ "$i" -eq "$primary_idx" ]; then
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

# LaunchDescription:
#   sync mode  -> secondaries first, primary launched last via TimerAction
#   no-sync    -> every camera launched independently (order irrelevant)
{
    echo "    ld = LaunchDescription(["
    if [ "$NO_SYNC" -eq 1 ]; then
        for i in "${!NAMES[@]}"; do
            echo "        GroupAction([cam_${i}]),"
        done
    else
        for i in "${!NAMES[@]}"; do
            if [ "$i" -eq "$primary_idx" ]; then continue; fi
            echo "        GroupAction([cam_${i}]),"
        done
        echo "        TimerAction(period=3.0, actions=[GroupAction([cam_${primary_idx}])]), # The primary camera should be launched at last"
    fi
    echo "    ])"
    echo ""
    echo "    return ld"
} >> "$OUTPUT"

echo "Launch file generated: $(pwd)/$OUTPUT"
if [ "$NO_SYNC" -eq 1 ]; then
    echo "  -> $count camera(s), async mode: ${ASYNC_MODE} (no synchronization, no primary)"
else
    echo "  -> $count camera(s), primary: ${NAMES[$primary_idx]}"
fi
echo "  Note: this file is created in the current directory. Place/install it into the"
echo "        orbbec_camera package's launch/ directory before running it."
if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] Generated from the fake device list above; verify against real hardware before use."
fi
