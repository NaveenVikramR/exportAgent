#!/usr/bin/env bash
# One-time server setup for Ubuntu 24.04. Run from the cloned repo:
#   sudo bash /opt/exportagent/deploy/setup.sh
#   sudo bash /opt/exportagent/deploy/setup.sh --relogin   # replace the GHCR token
# Safe to run again: every step checks whether it is already done.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-ubuntu}"

echo "== 2 GB swap file"
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# Use swap only under memory pressure.
sysctl -q vm.swappiness=10
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf

echo "== Docker"
if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -y -q docker.io docker-compose-v2
  systemctl enable --now docker
fi
usermod -aG docker "$APP_USER"

echo "== Docker daemon log limits (also set per container in docker-compose.yml)"
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'EOF'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
EOF
  systemctl restart docker
fi

echo "== Limit the system journal to 100 MB"
mkdir -p /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/size.conf
systemctl restart systemd-journald

echo "== Log in to GitHub Container Registry (the images are private)"
# The token is read with echo off, passed to docker login on stdin, and kept only in Docker's
# credential file (/home/$APP_USER/.docker/config.json, mode 600). Run with --relogin to replace it.
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
DOCKER_CFG="$APP_HOME/.docker"
if [[ "${1:-}" == "--relogin" ]] || ! grep -q '"ghcr.io"' "$DOCKER_CFG/config.json" 2>/dev/null; then
  read -rp "GitHub username [NaveenVikramR]: " GH_USER
  GH_USER="${GH_USER:-NaveenVikramR}"
  read -rsp "GitHub token (classic, read:packages only; typing is hidden): " GH_TOKEN
  echo
  mkdir -p "$DOCKER_CFG"
  if ! printf '%s' "$GH_TOKEN" | DOCKER_CONFIG="$DOCKER_CFG" docker login ghcr.io -u "$GH_USER" --password-stdin; then
    unset GH_TOKEN
    echo "Login failed. Check the token and its read:packages scope, then run: sudo bash $0 --relogin" >&2
    exit 1
  fi
  unset GH_TOKEN
  chown -R "$APP_USER:$APP_USER" "$DOCKER_CFG"
  chmod 700 "$DOCKER_CFG"
  chmod 600 "$DOCKER_CFG/config.json"
else
  echo "Already logged in to ghcr.io (run with --relogin to replace the token)."
fi

echo "== .env"
if [[ ! -f "$DEPLOY_DIR/.env" ]]; then
  cp "$DEPLOY_DIR/.env.example" "$DEPLOY_DIR/.env"
fi
chown "$APP_USER:$APP_USER" "$DEPLOY_DIR/.env"
chmod 600 "$DEPLOY_DIR/.env"

echo "== Nightly backup at 02:30 UTC"
chmod +x "$DEPLOY_DIR/backup.sh"
cat > /etc/cron.d/exportagent-backup <<EOF
30 2 * * * $APP_USER $DEPLOY_DIR/backup.sh >> /var/log/exportagent-backup.log 2>&1
EOF
touch /var/log/exportagent-backup.log
chown "$APP_USER:$APP_USER" /var/log/exportagent-backup.log

echo
echo "Done. Next: log out and back in (so 'docker' works without sudo), then edit $DEPLOY_DIR/.env"
free -h
df -h /
