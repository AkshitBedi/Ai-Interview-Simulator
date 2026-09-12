#!/usr/bin/env bash
# Configures a 2 GB swapfile on Azure Linux VM (Standard_B1s) to protect
# against OOM memory pressure from faster-whisper and MediaPipe inference.

set -euo pipefail

SWAPFILE="/swapfile"
SWAP_SIZE="2G"

if [ -f "$SWAPFILE" ]; then
    echo "Swapfile $SWAPFILE already exists. Skipping allocation."
else
    echo "Allocating $SWAP_SIZE swapfile at $SWAPFILE..."
    fallocate -l "$SWAP_SIZE" "$SWAPFILE" || dd if=/dev/zero of="$SWAPFILE" bs=1M count=2048
    chmod 600 "$SWAPFILE"
    mkswap "$SWAPFILE"
    swapon "$SWAPFILE"
    echo "Swapfile created and activated."
fi

# Persist in /etc/fstab if not present
if ! grep -qs "$SWAPFILE" /etc/fstab; then
    echo "$SWAPFILE none swap sw 0 0" >> /etc/fstab
    echo "Added swapfile to /etc/fstab for persistence across reboots."
fi

# Configure conservative swappiness (10)
sysctl vm.swappiness=10
if ! grep -qs "vm.swappiness" /etc/sysctl.conf; then
    echo "vm.swappiness=10" >> /etc/sysctl.conf
fi

echo "Swap configuration complete:"
free -h
swapon --show
