#!/bin/sh

STATE_DIR=/var/lib/tailscale
SOCKET=/var/run/tailscale/tailscaled.sock
SETTINGS="$STATE_DIR/settings.json"

mkdir -p "$STATE_DIR" /var/run/tailscale

log() {
  echo "=>" "$@"
}

log_detail() {
  echo "===>" "$@"
}

killtailscale() {
  log "Killing tailscaled"
  kill "$TAILSCALED_PID" 2>/dev/null
  exit 0
}

trap killtailscale INT TERM

# Subnet routing needs forwarding enabled in the host netns
if [ -f "$SETTINGS" ] && python3 -c "import json,sys; sys.exit(0 if json.load(open('$SETTINGS')).get('advertise_routes') else 1)" 2>/dev/null
then
  log "Subnet routes configured, enabling IP forwarding"
  sysctl -w net.ipv4.ip_forward=1 net.ipv6.conf.all.forwarding=1
fi

log "Starting tailscaled"
tailscaled \
  --statedir="$STATE_DIR" \
  --socket="$SOCKET" \
  --tun=tailscale0 \
  --port=41641 &
TAILSCALED_PID=$!

# 'status --json' prints JSON as soon as the daemon answers, even when logged out
while [ -z "$(tailscale --socket="$SOCKET" status --json 2>/dev/null)" ]
do
  log_detail "tailscaled hasn't started, waiting a second"
  if ! kill -0 "$TAILSCALED_PID" 2>/dev/null
  then
    log "tailscaled exited unexpectedly"
    exit 1
  fi
  sleep 1
done

if [ "x$TS_AUTHKEY" != "x" ]
then
  BACKEND_STATE=$(tailscale status --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('BackendState',''))")
  if [ "$BACKEND_STATE" = "NeedsLogin" ]
  then
    log "Logging in with auth key from environment"
    tailscale up --auth-key="$TS_AUTHKEY" --accept-dns=false --timeout=30s
  fi
fi

cat >/healthcheck.sh <<EOF
#!/bin/bash
[ -n "\$(tailscale status --json 2>/dev/null)" ]
EOF

chmod +x /healthcheck.sh

log "tailscale status:" "$(tailscale status 2>&1)"

# launch web interface
cd /web && python main.py &

log "Sleeping infinitely"
while true
do
  sleep 1
done
