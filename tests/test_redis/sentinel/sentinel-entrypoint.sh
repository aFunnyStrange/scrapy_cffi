#!/bin/sh
set -e

# Create necessary directories for Redis and temporary files
mkdir -p /usr/local/etc/redis
mkdir -p /tmp

# Default Sentinel port (can be overridden by environment variable)
: "${SENTINEL_PORT:=26379}"

# Wait until the master node is reachable
until redis-cli -h "$MASTER_HOST" ping >/dev/null 2>&1; do
    echo "Waiting for master $MASTER_HOST..."
    sleep 1
done

# Resolve MASTER_HOST to an IP address before starting Sentinel
MASTER_IP=$(getent hosts "$MASTER_HOST" | awk '{ print $1 }')

if [ -z "$MASTER_IP" ]; then
    echo "Failed to resolve $MASTER_HOST"
    exit 1
fi

echo "Resolved $MASTER_HOST to $MASTER_IP"
echo "Master $MASTER_IP is up, starting sentinel..."

# Generate sentinel.conf dynamically
cat > /usr/local/etc/redis/sentinel.conf <<EOF
# Working directory for Sentinel
dir /tmp

# Monitor the master node with name 'mymaster', quorum = 2
sentinel monitor mymaster ${MASTER_IP} 6379 2

# Time in milliseconds to consider master down
sentinel down-after-milliseconds mymaster 5000

# Failover timeout in milliseconds
sentinel failover-timeout mymaster 10000

# Number of replicas to sync in parallel during failover
sentinel parallel-syncs mymaster 1
EOF

# Start Redis in Sentinel mode
exec redis-server /usr/local/etc/redis/sentinel.conf --sentinel --port ${SENTINEL_PORT}
