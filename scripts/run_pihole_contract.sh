#!/bin/sh
set -eu

IMAGE="${PIHOLE_IMAGE:-pihole/pihole:latest}"
CONTAINER_NAME="${PIHOLE_CONTAINER_NAME:-pihole-contract}"
FTL_DB="${PIHOLE_FTL_DB:-.ci-pihole-FTL.db}"
GRAVITY_DB="${PIHOLE_GRAVITY_DB:-.ci-gravity.db}"
PYTEST="${PYTEST_BIN:-.venv/bin/pytest}"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

docker run -d --name "$CONTAINER_NAME" \
  --cap-add=NET_ADMIN \
  -e TZ=UTC \
  -e WEBPASSWORD=admin \
  -e FTLCONF_LOCAL_IPV4=127.0.0.1 \
  "$IMAGE" >/dev/null

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -f "$FTL_DB" "$GRAVITY_DB" "$FTL_DB-shm" "$FTL_DB-wal"
}
trap cleanup EXIT

for i in $(seq 1 30); do
  if docker exec "$CONTAINER_NAME" test -f /etc/pihole/pihole-FTL.db && \
     docker exec "$CONTAINER_NAME" test -f /etc/pihole/gravity.db; then
    break
  fi
  sleep 2
done

docker exec "$CONTAINER_NAME" test -f /etc/pihole/pihole-FTL.db
docker exec "$CONTAINER_NAME" test -f /etc/pihole/gravity.db

docker cp "$CONTAINER_NAME":/etc/pihole/pihole-FTL.db "$FTL_DB"
docker cp "$CONTAINER_NAME":/etc/pihole/gravity.db "$GRAVITY_DB"

PIHOLE_CONTRACT=1 PIHOLE_FTL_DB="$FTL_DB" PIHOLE_GRAVITY_DB="$GRAVITY_DB" "$PYTEST" tests/test_contract_pihole.py
