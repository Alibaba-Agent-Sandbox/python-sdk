#!/usr/bin/env bash
# Bring up a real, local, secret-free OpenSandbox (lifecycle server + Docker runtime)
# for live integration tests of the Easy Sandbox `opensandbox` provider plugin.
#
#   local-up.sh [up]      install (idempotent), start, wait healthy, print env
#   opensandbox-local-up.sh down      stop the server and remove every sandbox container
#   opensandbox-local-up.sh status    health + running sandbox containers
#   opensandbox-local-up.sh env       only print the `export ...` lines
#
# Verified on: Ubuntu 24.04, kernel 6.12, rootfs = overlayfs, passwordless sudo,
# no docker preinstalled (dockerd installed from the distro `docker.io` package).
#
# Tunables (environment):
#   OSB_SERVER_VERSION  PyPI version of opensandbox-server   (default 1.1.1)
#   OSB_EXECD_IMAGE     execd image injected into sandboxes   (default opensandbox/execd:latest;
#                       v1.1.0 lacks `argv` and strips line endings in /command output)
#   OSB_PORT            lifecycle server port                 (default 8080)
#   OSB_API_KEY         server API key                        (default local-dev-key; NOT a secret)
#   OSB_WORKDIR         state dir (venv, config, db, logs)    (default $XDG_CACHE_HOME/easy-sandbox/opensandbox-local)
#   OSB_WITH_EGRESS=1   also pull/enable the egress sidecar (network policy tests)
#   OSB_WITH_CODE_INTERPRETER=1  also pull opensandbox/code-interpreter (run_code tests)
set -euo pipefail

CMD="${1:-up}"
OSB_SERVER_VERSION="${OSB_SERVER_VERSION:-1.1.1}"
OSB_EXECD_IMAGE="${OSB_EXECD_IMAGE:-opensandbox/execd:latest}"
OSB_EGRESS_IMAGE="${OSB_EGRESS_IMAGE:-opensandbox/egress:v1.1.7}"
OSB_CI_IMAGE="${OSB_CI_IMAGE:-opensandbox/code-interpreter:v1.1.0}"
OSB_BASE_IMAGE="${OSB_BASE_IMAGE:-python:3.12-slim}"
OSB_PORT="${OSB_PORT:-8080}"
OSB_API_KEY="${OSB_API_KEY:-local-dev-key}"
OSB_WORKDIR="${OSB_WORKDIR:-${XDG_CACHE_HOME:-$HOME/.cache}/easy-sandbox/opensandbox-local}"
OSB_WITH_EGRESS="${OSB_WITH_EGRESS:-1}"
OSB_WITH_CODE_INTERPRETER="${OSB_WITH_CODE_INTERPRETER:-0}"
OSB_DOCKER_DATA_IMG="${OSB_DOCKER_DATA_IMG:-/var/lib/docker-loop.img}"
OSB_DOCKER_DATA_DIR="${OSB_DOCKER_DATA_DIR:-/mnt/dockerdata}"

VENV="$OSB_WORKDIR/venv"
CONFIG="$OSB_WORKDIR/server.toml"
LOG="$OSB_WORKDIR/server.log"
PIDFILE="$OSB_WORKDIR/server.pid"
export PATH="$HOME/.local/bin:$PATH"

log() { printf '[opensandbox-local] %s\n' "$*" >&2; }
SUDO=""; if [ "$(id -u)" != "0" ]; then SUDO="sudo -n"; fi

print_env() {
  cat <<EOF
export OPENSANDBOX_URL=http://127.0.0.1:${OSB_PORT}
export OPENSANDBOX_BASE_URL=http://127.0.0.1:${OSB_PORT}/v1
export OPENSANDBOX_API_KEY=${OSB_API_KEY}
export OPENSANDBOX_TEST_IMAGE=${OSB_BASE_IMAGE}
export OPENSANDBOX_CODE_IMAGE=${OSB_CI_IMAGE}
EOF
}

healthy() { curl -fsS -m 3 "http://127.0.0.1:${OSB_PORT}/health" >/dev/null 2>&1; }

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    log "installing docker.io (apt)"
    $SUDO apt-get update -qq
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io iptables >/dev/null
  fi
  if docker info >/dev/null 2>&1; then return; fi

  # A container rootfs on an overlayfs-backed / cannot use overlay2 ("invalid argument"):
  # put Docker's data-root on a loop-mounted ext4 image and disable the containerd snapshotter.
  if ! mountpoint -q "$OSB_DOCKER_DATA_DIR" 2>/dev/null; then
    log "creating loop-mounted ext4 data-root at $OSB_DOCKER_DATA_DIR"
    [ -f "$OSB_DOCKER_DATA_IMG" ] || { $SUDO truncate -s 20G "$OSB_DOCKER_DATA_IMG"; $SUDO mkfs.ext4 -q -F "$OSB_DOCKER_DATA_IMG"; }
    $SUDO mkdir -p "$OSB_DOCKER_DATA_DIR"
    $SUDO mount -o loop "$OSB_DOCKER_DATA_IMG" "$OSB_DOCKER_DATA_DIR"
  fi
  $SUDO mkdir -p /etc/docker
  echo "{\"data-root\":\"$OSB_DOCKER_DATA_DIR\",\"storage-driver\":\"overlay2\",\"features\":{\"containerd-snapshotter\":false}}" \
    | $SUDO tee /etc/docker/daemon.json >/dev/null

  if ! $SUDO docker info >/dev/null 2>&1; then
    log "starting dockerd (no systemd available)"
    mkdir -p "$OSB_WORKDIR"
    ( $SUDO nohup dockerd >"$OSB_WORKDIR/dockerd.log" 2>&1 & )
    for _ in $(seq 1 40); do $SUDO docker info >/dev/null 2>&1 && break; sleep 1; done
  fi
  $SUDO docker info >/dev/null 2>&1 || { log "dockerd failed to start; see $OSB_WORKDIR/dockerd.log"; exit 1; }
  # The server (running as the current user) talks to /var/run/docker.sock directly.
  $SUDO chmod 666 /var/run/docker.sock
}

ensure_server() {
  mkdir -p "$OSB_WORKDIR"
  if ! command -v uv >/dev/null 2>&1; then
    log "installing uv"
    python3 -m pip install --user -q uv 2>/dev/null || python3 -m pip install --user -q --break-system-packages uv
  fi
  if [ ! -x "$VENV/bin/opensandbox-server" ] || ! "$VENV/bin/python" -c "import importlib.metadata as m,sys; sys.exit(0 if m.version('opensandbox-server')=='$OSB_SERVER_VERSION' else 1)" 2>/dev/null; then
    log "installing opensandbox-server==$OSB_SERVER_VERSION into $VENV"
    uv venv "$VENV" --python 3.12 -q
    uv pip install -q --python "$VENV/bin/python" "opensandbox-server==$OSB_SERVER_VERSION"
  fi
}

write_config() {
  cat >"$CONFIG" <<EOF
[server]
host = "127.0.0.1"
port = ${OSB_PORT}
api_key = "${OSB_API_KEY}"
max_sandbox_timeout_seconds = 86400

[runtime]
type = "docker"
execd_image = "${OSB_EXECD_IMAGE}"

[store]
type = "sqlite"
path = "${OSB_WORKDIR}/opensandbox.db"

[docker]
network_mode = "bridge"

[ingress]
mode = "direct"
EOF
  if [ "$OSB_WITH_EGRESS" = "1" ]; then
    cat >>"$CONFIG" <<EOF

[egress]
image = "${OSB_EGRESS_IMAGE}"
mode = "dns"
EOF
  fi
}

pull_images() {
  local imgs=("$OSB_EXECD_IMAGE" "$OSB_BASE_IMAGE")
  [ "$OSB_WITH_EGRESS" = "1" ] && imgs+=("$OSB_EGRESS_IMAGE")
  [ "$OSB_WITH_CODE_INTERPRETER" = "1" ] && imgs+=("$OSB_CI_IMAGE")
  for i in "${imgs[@]}"; do
    docker image inspect "$i" >/dev/null 2>&1 || { log "pulling $i"; docker pull -q "$i" >/dev/null; }
  done
}

start_server() {
  if healthy; then log "server already healthy on :${OSB_PORT}"; return; fi
  log "starting opensandbox-server on 127.0.0.1:${OSB_PORT}"
  ( nohup "$VENV/bin/opensandbox-server" --config "$CONFIG" >"$LOG" 2>&1 & echo $! >"$PIDFILE" )
  for _ in $(seq 1 60); do healthy && break; sleep 1; done
  healthy || { log "server did not become healthy; tail of $LOG:"; tail -n 30 "$LOG" >&2; exit 1; }
}

stop_server() {
  if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi
  pkill -f "opensandbox-server --config $CONFIG" 2>/dev/null || true
  ids=$(docker ps -aq --filter "name=sandbox-" 2>/dev/null || true)
  [ -n "$ids" ] && docker rm -f $ids >/dev/null 2>&1 || true
}

case "$CMD" in
  up)
    ensure_docker
    ensure_server
    write_config
    pull_images
    start_server
    log "READY  (api key header: OPEN-SANDBOX-API-KEY: ${OSB_API_KEY})"
    print_env
    ;;
  down) stop_server; log "stopped" ;;
  status)
    if healthy; then echo "healthy: $(curl -s http://127.0.0.1:${OSB_PORT}/version)"; else echo "not running"; fi
    docker ps --filter "name=sandbox-" --format '{{.Names}} {{.Image}} {{.Status}}' 2>/dev/null || true ;;
  env) print_env ;;
  *) echo "usage: $0 [up|down|status|env]" >&2; exit 2 ;;
esac
