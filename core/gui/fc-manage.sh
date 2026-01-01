#!/bin/bash

# ==========================================
# Firecracker Background & Snapshot Controller v4
# ==========================================
# This script manages a single Firecracker VM instance in the background.
# It supports starting fresh, stopping cleanly, pausing to disk (snapshot),
# resuming from a snapshot, and purging state.
#
# Usage: sudo ./fc-manage.sh [start|stop|restart|pause|resume|purge|status|tail|clean]
# ==========================================

set -e

# Make sure we are root for network ops
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (for network and KVM access)."
    echo "Try: sudo $0 $1"
    exit 1
fi

# --- Configuration ---
# Persistent workspace directory within the user's home (even when running as sudo)
# Attempt to find the real user's home directory.
if [ -n "$SUDO_USER" ]; then
    REAL_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    REAL_USER_HOME=$HOME
fi

WORKDIR="${REAL_USER_HOME}/fc-workdir"
DATA_DIR="$WORKDIR/data"

# VM Configuration
TAP_DEV="tap0"
HOST_IP="172.16.0.1"
VM_IP="172.16.0.2"
NETMASK_LEN="/24"
VCpuCount=1
MemSizeMib=512
# Fixed MAC for consistency across pauses/resumes
FC_MAC="02:FC:00:00:00:01"

# Firecracker Version
FC_VERSION="v1.7.0"

# Runtime paths
API_SOCKET="/tmp/firecracker.socket"
LOG_FILE="$WORKDIR/fc.log"
PID_FILE="$WORKDIR/fc.pid"

# Snapshot Paths
SNAPSHOT_DIR="$WORKDIR/snapshots"
MEM_FILE_PATH="$SNAPSHOT_DIR/vm.mem"
SNAPSHOT_FILE_PATH="$SNAPSHOT_DIR/vm.snap"

# Binary and Image Paths
FC_BINARY="$DATA_DIR/firecracker"
KERNEL_PATH="$DATA_DIR/vmlinux.bin"
ROOTFS_PATH="$DATA_DIR/bionic.rootfs.ext4"
# URLs
KERNEL_URL="https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin"
ROOTFS_URL="https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/rootfs/bionic.rootfs.ext4"
ARCH="$(uname -m)"

# ==========================================
# === Helper Functions ===
# ==========================================

setup_workspace() {
    mkdir -p "$WORKDIR" "$DATA_DIR" "$SNAPSHOT_DIR"
    # Ensure the real user can access these directories (useful for debugging logs without sudo)
    if [ -n "$SUDO_USER" ]; then
         chown -R "$SUDO_USER:" "$WORKDIR"
    fi

    # --- Download Firecracker Binary (Robust Method) ---
    # If it doesn't exist, OR if it exists but is accidentally a directory from a failed previous run
    if [ ! -f "$FC_BINARY" ] || [ -d "$FC_BINARY" ]; then
        # Safety cleanup if it's wrongly a directory
        if [ -d "$FC_BINARY" ]; then echo "Cleaning up corrupted binary path..."; rm -rf "$FC_BINARY"; fi

        echo "Downloading Firecracker $FC_VERSION..."
        DOWNLOAD_URL="https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VERSION}/firecracker-${FC_VERSION}-${ARCH}.tgz"

        # Use a temporary directory for extraction to handle unpredictable tar structures
        TMP_EXTRACT=$(mktemp -d -t fc-extract-XXXXXX)
        
        echo "Extracting..."
        curl -L --fail "$DOWNLOAD_URL" | tar -xz -C "$TMP_EXTRACT"
        
        # Find the actual binary file inside the extracted contents.
        # We look for a file (-type f) whose name starts with firecracker.
        FOUND_BIN=$(find "$TMP_EXTRACT" -type f -name "firecracker*" | head -n 1)

        if [ -z "$FOUND_BIN" ]; then
             echo "ERROR: Could not locate firecracker executable within downloaded archive."
             rm -rf "$TMP_EXTRACT"
             exit 1
        fi
        
        echo "Found binary: $FOUND_BIN. Moving to final location..."
        mv "$FOUND_BIN" "$FC_BINARY"
        chmod +x "$FC_BINARY"
        # Clean up temp extract dir
        rm -rf "$TMP_EXTRACT"
    fi

    # Download Kernel/Rootfs if missing
    # Added --fail to curl to stop immediately if the link is bad
    [ ! -f "$KERNEL_PATH" ] && echo "Downloading Kernel..." && curl -L --fail -o "$KERNEL_PATH" "$KERNEL_URL"
    # Check if rootfs exists and has nonzero size (sometimes failed downloads leave empty files)
    if [ ! -f "$ROOTFS_PATH" ] || [ ! -s "$ROOTFS_PATH" ]; then
         echo "Downloading Rootfs (approx 300MB)..."
         curl -L --fail -o "$ROOTFS_PATH" "$ROOTFS_URL"
    fi

    # Check KVM
    [ -w "/dev/kvm" ] || { echo "ERROR: /dev/kvm not writeable."; exit 1; }
}

setup_network() {
    echo "configuring $TAP_DEV ($HOST_IP)..."
    ip link del "$TAP_DEV" 2>/dev/null || true
    ip tuntap add dev "$TAP_DEV" mode tap
    ip addr add "${HOST_IP}${NETMASK_LEN}" dev "$TAP_DEV"
    ip link set dev "$TAP_DEV" up
}

cleanup_network() {
     echo "Removing network interface $TAP_DEV..."
    ip link del "$TAP_DEV" 2>/dev/null || true
}

# Helper to send API requests via curl to the unix socket
curl_api() {
    local method=$1
    local path=$2
    local body=$3
    # We need to capture http status code to handle errors properly
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --unix-socket "$API_SOCKET" -X "$method" \
         -H "Content-Type: application/json" \
         -d "$body" "http://localhost/$path")
    
    if [ "$HTTP_STATUS" -ge 400 ]; then
         echo "Error: API request $method $path failed with status $HTTP_STATUS"
         # Uncomment below to see the actual error message from Firecracker for debugging
         # curl -s --unix-socket "$API_SOCKET" -X "$method" -H "Content-Type: application/json" -d "$body" "http://localhost/$path"
         return 1
    fi
    return 0
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        # Check if process exists AND is actually firecracker
        if ps -p "$PID" > /dev/null && ps -p "$PID" -o comm= | grep -q "firecracker"; then
            return 0 # Running
        fi
         # Stale PID file
        rm -f "$PID_FILE"
    fi
    return 1 # Not running
}

start_firecracker_process() {
    if is_running; then echo "Firecracker is already running (PID $(cat $PID_FILE))"; exit 1; fi

    echo "Starting Firecracker process in background..."
    rm -f "$API_SOCKET"
    # Ensure log file exists and is writable
    touch "$LOG_FILE"
    if [ -n "$SUDO_USER" ]; then chown "$SUDO_USER" "$LOG_FILE"; fi

    # Start FC listening on socket, redirect logs, run in background
    # We use setsid to detach it fully from the current terminal session
    setsid "$FC_BINARY" --api-sock "$API_SOCKET" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    # Wait for socket to appear
    echo "Waiting for API socket..."
    tries=0
    while [ ! -S "$API_SOCKET" ]; do
        sleep 0.1
        tries=$((tries+1))
        if [ $tries -gt 50 ]; then
             echo "ERROR: API socket creation timed out."
             echo "--- Last 20 lines of log file ---"
             tail -n 20 "$LOG_FILE"
             echo "---------------------------------"
             kill "$PID" 2>/dev/null
             rm -f "$PID_FILE"
             exit 1
        fi
    done
    echo "Firecracker API ready at $API_SOCKET (PID $PID)"
}

stop_firecracker_process() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "Stopping Firecracker (PID $PID)..."
        # Try graceful shutdown via API first (sends Ctrl+Alt+Del to guest)
        # We don't exit on error here because if the VM is crashed, API might not respond
        curl_api PUT "actions" '{"action_type": "SendCtrlAltDel"}' || true

        # Wait for it to exit
        count=0
        while ps -p "$PID" > /dev/null; do
            sleep 0.5
            count=$((count+1))
            # Hard kill after 10 seconds if it hasn't exited
            if [ $count -gt 20 ]; then echo "Force killing..."; kill -9 "$PID"; break; fi
        done
        echo "Stopped."
    else
        echo "Firecracker is not running."
    fi
    rm -f "$PID_FILE" "$API_SOCKET"
}


# ==========================================
# === Main Commands ===
# ==========================================

cmd_start() {
    # Ensure previous instance is cleaned up if it crashed
    if ! is_running; then cleanup_network; rm -f "$API_SOCKET"; fi
    
    setup_workspace
    setup_network
    start_firecracker_process

    echo "Configuring VM via API..."
    # 1. Set Boot Source
    boot_args="console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw ip=$VM_IP::$HOST_IP:$NETMASK_LEN::eth0:off"
    curl_api PUT "boot-source" "{\"kernel_image_path\": \"$KERNEL_PATH\", \"boot_args\": \"$boot_args\"}"

    # 2. Set Rootfs Drive
    # We ensure the file is accessible by the firecracker process (running as root)
    chmod +r "$ROOTFS_PATH"
    curl_api PUT "drives/rootfs" "{\"drive_id\": \"rootfs\", \"path_on_host\": \"$ROOTFS_PATH\", \"is_root_device\": true, \"is_read_only\": false}"

    # 3. Set Network
    curl_api PUT "network-interfaces/eth0" "{\"iface_id\": \"eth0\", \"guest_mac\": \"$FC_MAC\", \"host_dev_name\": \"$TAP_DEV\"}"

    # 4. Set Machine Config (CPU/Mem)
    curl_api PUT "machine-config" "{\"vcpu_count\": $VCpuCount, \"mem_size_mib\": $MemSizeMib}"

    echo "Launching Instance..."
    curl_api PUT "actions" '{"action_type": "InstanceStart"}'

    echo "VM started in background. IP: $VM_IP"
    echo "Use '$0 tail' to see boot logs."
}

cmd_stop() {
    stop_firecracker_process
    cleanup_network
}

cmd_pause() {
    if ! is_running; then echo "VM not running."; exit 1; fi
    echo "Pausing VM and creating snapshot..."

    # 1. Pause VM
    curl_api PATCH "vm/state" '{"state": "Paused"}'

    # 2. Create Snapshot files
    rm -f "$MEM_FILE_PATH" "$SNAPSHOT_FILE_PATH"
    # Ensure snapshot directory is writable by root
    mkdir -p "$SNAPSHOT_DIR"
    curl_api PUT "snapshot/create" "{\"mem_file_path\": \"$MEM_FILE_PATH\", \"snapshot_path\": \"$SNAPSHOT_FILE_PATH\"}"
    echo "Snapshot saved to $SNAPSHOT_DIR"

    # 3. Kill process and clean network
    stop_firecracker_process
    cleanup_network
    echo "VM paused and stopped. State saved."
}

cmd_resume() {
    if is_running; then echo "VM already running."; exit 1; fi
    if [ ! -f "$SNAPSHOT_FILE_PATH" ]; then echo "No snapshot found at $SNAPSHOT_FILE_PATH"; exit 1; fi

    # Ensure previous instance network is cleaned up
    cleanup_network

    # Ensure binary exists if resume is run on a fresh machine
    setup_workspace
    setup_network
    start_firecracker_process

    echo "Loading snapshot..."
    # 1. Load snapshot data
    curl_api PUT "snapshot/load" "{\"mem_file_path\": \"$MEM_FILE_PATH\", \"snapshot_path\": \"$SNAPSHOT_FILE_PATH\"}"

    # 2. Resume VM execution
    curl_api PATCH "vm/state" '{"state": "Resumed"}'

    echo "VM resumed successfully. IP: $VM_IP"
}

cmd_purge() {
    echo "--- Purging VM State ---"
    # 1. Stop the VM if it's running (cmd_stop handles running checks and network cleanup)
    cmd_stop

    # 2. Delete Snapshot files
    if [ -d "$SNAPSHOT_DIR" ]; then
        echo "Removing snapshot files from $SNAPSHOT_DIR..."
        rm -f "$MEM_FILE_PATH" "$SNAPSHOT_FILE_PATH"
    fi

    echo "VM state and snapshots have been removed. The next 'start' will boot fresh."
}

cmd_status() {
    if is_running; then
        PID=$(cat "$PID_FILE")
        echo "Status: RUNNING (PID $PID)"
        echo "Host IP: $HOST_IP, VM IP: $VM_IP"
        echo "Log file: $LOG_FILE"
    else
        echo "Status: STOPPED"
    fi
    if [ -f "$SNAPSHOT_FILE_PATH" ]; then echo "Snapshot available: Yes ($SNAPSHOT_FILE_PATH)"; else echo "Snapshot available: No"; fi
}

cmd_clean() {
    if is_running; then echo "Cannot clean while running. Stop it first."; exit 1; fi
    echo "WARNING: This will delete downloaded images and Firecracker binary."
    echo "Cleaning up workspace $WORKDIR..."
    # Don't delete the whole workdir, just data and snapshots
    rm -rf "$DATA_DIR" "$SNAPSHOT_DIR" "$LOG_FILE" "$PID_FILE"
    echo "Done."
}


# ==========================================
# === Command Dispatch ===
# ==========================================
# Ensure absolute path to self for recursive calls (like in restart)
SELF_PATH=$(realpath "$0")

case "$1" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_stop; sleep 2; "$SELF_PATH" start ;;
    pause)   cmd_pause ;;
    resume)  cmd_resume ;;
    purge)   cmd_purge ;;
    status)  cmd_status ;;
    clean)   cmd_clean ;;
    tail)    tail -f "$LOG_FILE" ;;
    *)
        echo "Usage: sudo $0 [start|stop|restart|pause|resume|purge|status|clean|tail]"
        exit 1
        ;;
esac