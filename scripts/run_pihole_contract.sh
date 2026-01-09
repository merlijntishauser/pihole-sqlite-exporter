#!/bin/sh
set -eu

TAGS="${PIHOLE_TAGS:-latest}"
CONTAINER_BASE_NAME="${PIHOLE_CONTAINER_NAME:-pihole-contract}"
FTL_DB="${PIHOLE_FTL_DB:-.ci-pihole-FTL.db}"
GRAVITY_DB="${PIHOLE_GRAVITY_DB:-.ci-gravity.db}"
PYTEST="${PYTEST_BIN:-.venv/bin/pytest}"

cleanup() {
  if [ -n "${RUNNING_CONTAINER:-}" ]; then
    docker rm -f "$RUNNING_CONTAINER" >/dev/null 2>&1 || true
  fi
  rm -f "$FTL_DB" "$GRAVITY_DB" "$FTL_DB-shm" "$FTL_DB-wal"
}
trap cleanup EXIT

for tag in $TAGS; do
  image="pihole/pihole:$tag"
  container_name="${CONTAINER_BASE_NAME}-${tag}"
  RUNNING_CONTAINER="$container_name"

  docker rm -f "$container_name" >/dev/null 2>&1 || true

  docker run -d --name "$container_name" \
    --cap-add=NET_ADMIN \
    -e TZ=UTC \
    -e WEBPASSWORD=admin \
    -e FTLCONF_LOCAL_IPV4=127.0.0.1 \
    "$image" >/dev/null

  for i in $(seq 1 30); do
    if docker exec "$container_name" test -f /etc/pihole/pihole-FTL.db && \
       docker exec "$container_name" test -f /etc/pihole/gravity.db; then
      break
    fi
    sleep 2
  done

  docker exec "$container_name" test -f /etc/pihole/pihole-FTL.db
  docker exec "$container_name" test -f /etc/pihole/gravity.db

  docker cp "$container_name":/etc/pihole/pihole-FTL.db "$FTL_DB"
  docker cp "$container_name":/etc/pihole/gravity.db "$GRAVITY_DB"

  PIHOLE_CONTRACT=1 PIHOLE_FTL_DB="$FTL_DB" PIHOLE_GRAVITY_DB="$GRAVITY_DB" "$PYTEST" \
    tests/test_contract_pihole.py

  docker rm -f "$container_name" >/dev/null 2>&1 || true
  RUNNING_CONTAINER=""
  rm -f "$FTL_DB" "$GRAVITY_DB" "$FTL_DB-shm" "$FTL_DB-wal"
done
