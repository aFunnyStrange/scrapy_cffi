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

if redis-cli -h redis-node1 -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
  exit 0
fi

yes yes | redis-cli --cluster create \
  redis-node1:7000 \
  redis-node2:7001 \
  redis-node3:7002 \
  redis-node4:7003 \
  redis-node5:7004 \
  redis-node6:7005 \
  --cluster-replicas 1
