#!/bin/sh
set -e

mkdir -p /usr/local/etc/redis /tmp
: "${SENTINEL_PORT:=26379}"

until redis-cli -h "$MASTER_HOST" ping >/dev/null 2>&1; do
  echo "Waiting for master $MASTER_HOST..."
  sleep 1
done

MASTER_IP="$(getent hosts "$MASTER_HOST" | awk '{ print $1 }')"
[ -n "$MASTER_IP" ] || { echo "Failed to resolve $MASTER_HOST"; exit 1; }

cat > /usr/local/etc/redis/sentinel.conf <<EOF
dir /tmp
sentinel monitor mymaster ${MASTER_IP} 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
sentinel parallel-syncs mymaster 1
EOF

exec redis-server /usr/local/etc/redis/sentinel.conf --sentinel --port ${SENTINEL_PORT}
