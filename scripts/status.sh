#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

docker compose ps

if docker compose ps --status running --services | grep -qx filex; then
  origin=$(grep '^FILEX_ORIGIN=' .env 2>/dev/null | cut -d= -f2- || true)
  [ -n "$origin" ] && echo "Open: $origin"
fi
