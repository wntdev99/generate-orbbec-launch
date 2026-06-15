#!/bin/bash
# Setup helper for the generate_orbbec_launch package.
#   - installs dependencies (rosdep + optional system tools: ethtool, pyudev)
#   - builds the package with colcon
#   - (optional) sets up an SSH key to the router for wifi_wan_monitor
#
# Usage: scripts/setup.sh [--no-deps] [--no-build] [--wifi-key [user@host]] [-h]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG_NAME="generate_orbbec_launch"

DO_DEPS=1
DO_BUILD=1
DO_WIFI_KEY=0
WIFI_TARGET="root@192.168.34.1"

while [ $# -gt 0 ]; do
    case "$1" in
        --no-deps)  DO_DEPS=0 ;;
        --no-build) DO_BUILD=0 ;;
        --wifi-key)
            DO_WIFI_KEY=1
            # optional "user@host" argument right after the flag
            if [ $# -gt 1 ] && [ "${2#-}" = "$2" ]; then WIFI_TARGET="$2"; shift; fi
            ;;
        -h|--help)
            echo "Usage: scripts/setup.sh [--no-deps] [--no-build] [--wifi-key [user@host]]"
            echo "  --no-deps          skip dependency installation"
            echo "  --no-build         skip colcon build"
            echo "  --wifi-key [tgt]   set up an SSH key to the router (default root@192.168.34.1)"
            echo "                     so wifi_wan_monitor can read the WiFi WAN dBm (no password stored)"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
    shift
done

# Locate the colcon workspace root (package is expected at <ws>/src/<pkg>)
SRC_DIR="$(cd "$PKG_DIR/.." && pwd)"
if [ "$(basename "$SRC_DIR")" = "src" ]; then
    WS_DIR="$(cd "$SRC_DIR/.." && pwd)"
else
    WS_DIR=""
fi

echo "[setup] package   : $PKG_DIR"
echo "[setup] workspace : ${WS_DIR:-<not a <ws>/src/$PKG_NAME layout>}"

# --- dependencies ---
if [ "$DO_DEPS" -eq 1 ]; then
    echo "[setup] installing dependencies..."
    if command -v rosdep >/dev/null 2>&1; then
        sudo rosdep init 2>/dev/null || true
        rosdep update || true
        rosdep install --from-paths "$PKG_DIR" --ignore-src -y \
            || echo "[setup] WARN: rosdep reported issues; continuing"
    else
        echo "[setup] rosdep not found; skipping (install python3-rosdep for automatic deps)"
    fi
    # Extra system tools used by the monitor nodes (not ROS packages)
    if command -v apt-get >/dev/null 2>&1; then
        PKGS=""
        command -v ethtool >/dev/null 2>&1 || PKGS="$PKGS ethtool"
        python3 -c "import pyudev" 2>/dev/null || PKGS="$PKGS python3-pyudev"
        if [ -n "$PKGS" ]; then
            echo "[setup] apt installing:$PKGS"
            sudo apt-get update -qq && sudo apt-get install -y $PKGS \
                || echo "[setup] WARN: apt install failed; install manually:$PKGS"
        else
            echo "[setup] ethtool + python3-pyudev already present"
        fi
    fi
fi

# --- build ---
if [ "$DO_BUILD" -eq 1 ]; then
    if [ -z "$WS_DIR" ]; then
        echo "[setup] ERROR: not a colcon workspace; skipping build." >&2
        echo "        Place this package at <workspace>/src/$PKG_NAME and re-run." >&2
    else
        echo "[setup] building $PKG_NAME in $WS_DIR ..."
        ( cd "$WS_DIR" && colcon build --packages-select "$PKG_NAME" )
        echo "[setup] build done. Source it with:"
        echo "         source $WS_DIR/install/setup.bash"
    fi
fi

# --- optional: SSH key to the router for wifi_wan_monitor ---
if [ "$DO_WIFI_KEY" -eq 1 ]; then
    echo "[setup] setting up SSH key for wifi_wan_monitor -> $WIFI_TARGET"
    KEY="$HOME/.ssh/id_ed25519"
    [ -f "$KEY" ] || ssh-keygen -t ed25519 -N "" -f "$KEY"
    echo "[setup] copying public key (you will be asked for the router password once)"
    ssh-copy-id -i "${KEY}.pub" "$WIFI_TARGET"
    echo "[setup] testing key-based login..."
    ssh -o BatchMode=yes -o ConnectTimeout=6 "$WIFI_TARGET" 'echo ROUTER_KEY_OK' \
        || echo "[setup] WARN: key login test failed"
fi

echo "[setup] complete."
