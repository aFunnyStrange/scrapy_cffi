#!/bin/sh
set -eu

NODES="redis-node1:7000 redis-node2:7001 redis-node3:7002 redis-node4:7003 redis-node5:7004 redis-node6:7005"
for node in $NODES; do
  host="${node%:*}"
  port="${node#*:}"
  until redis-cli -h "$host" -p "$port" ping >/dev/null 2>&1; do
    sleep 1
  done
done

if ! redis-cli -h redis-node1 -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
  yes yes | redis-cli --cluster create \
    redis-node1:7000 \
    redis-node2:7001 \
    redis-node3:7002 \
    redis-node4:7003 \
    redis-node5:7004 \
    redis-node6:7005 \
    --cluster-replicas 1
fi

# Slot assignment returns before gossip has converged and replicas have adopted
# their roles. Do not let `docker compose up --wait` release the crawler until
# the cluster is actually writable.
attempt=0
until redis-cli -h redis-node1 -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Redis Cluster did not reach cluster_state:ok" >&2
    exit 1
  fi
  sleep 1
done

# Keep the one-shot initializer alive so Compose `up --wait` can model it as a
# healthy dependency instead of treating a successful exit as a failed service.
exec tail -f /dev/null
