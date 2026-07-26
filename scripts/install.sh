#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Desktop or Docker Engine first." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    date +%s | shasum -a 256 | awk '{print $1}'
  fi
}

replace_value() {
  key=$1
  value=$2
  tmp=".env.tmp.$$"
  awk -v key="$key" -v value="$value" '
    BEGIN { done = 0 }
    $0 ~ "^" key "=" {
      print key "=" value
      done = 1
      next
    }
    { print }
    END {
      if (!done) print key "=" value
    }
  ' .env > "$tmp"
  mv "$tmp" .env
}

grep -q '^FILEX_SECRET_KEY=change-me-filex-secret$' .env && replace_value FILEX_SECRET_KEY "$(secret)"
grep -q '^FILEX_ASSET_SIGNING_SECRET=change-me-asset-signing-secret$' .env && replace_value FILEX_ASSET_SIGNING_SECRET "$(secret)"
grep -q '^POSTGRES_PASSWORD=change-me-postgres-password$' .env && replace_value POSTGRES_PASSWORD "$(secret)"
grep -q '^RABBITMQ_DEFAULT_PASS=change-me-rabbitmq-password$' .env && replace_value RABBITMQ_DEFAULT_PASS "$(secret)"

if grep -q '^FILEX_BOOTSTRAP_PASSWORD=change-me-before-first-start$' .env; then
  echo "Edit .env and set FILEX_BOOTSTRAP_PASSWORD before first start." >&2
  exit 2
fi

mkdir -p data/uploads data/logs data/postgres data/rabbitmq data/redis data/ollama

docker compose config >/dev/null
docker compose pull
docker compose up -d

echo "FileX is starting."
echo "Open: $(grep '^FILEX_ORIGIN=' .env | cut -d= -f2-)"
echo "Status: ./scripts/status.sh"
