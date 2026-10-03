#!/usr/bin/env bash
# Start bettercap with its REST API on, ready for bettertui to connect.
#
# Usage:  sudo ./scripts/start-bettercap.sh <iface> [user] [pass] [port]
# Example: sudo ./scripts/start-bettercap.sh wlan0 admin s3cret 8081
#
# bettercap needs root to touch the network interface. bettertui then connects
# to http://127.0.0.1:<port> with the same user/pass.
set -euo pipefail

IFACE="${1:?usage: start-bettercap.sh <iface> [user] [pass] [port]}"
USER="${2:-user}"
PASS="${3:-pass}"
PORT="${4:-8081}"

exec bettercap -iface "$IFACE" -eval "
set api.rest.address 127.0.0.1;
set api.rest.port ${PORT};
set api.rest.username ${USER};
set api.rest.password ${PASS};
net.recon on;
api.rest on
"
