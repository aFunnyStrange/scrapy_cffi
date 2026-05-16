#!/bin/sh
set -eu

NODES="host.docker.internal:7000 host.docker.internal:7001 host.docker.internal:7002 host.docker.internal:7003 host.docker.internal:7004 host.docker.internal:7005"
for node in $NODES; do
  host="${node%:*}"
  port="${node#*:}"
  until redis-cli -h "$host" -p "$port" ping >/dev/null 2>&1; do
    sleep 1
  done
done

if redis-cli -h host.docker.internal -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
  exit 0
fi

yes yes | redis-cli --cluster create \
  host.docker.internal:7000 \
  host.docker.internal:7001 \
  host.docker.internal:7002 \
  host.docker.internal:7003 \
  host.docker.internal:7004 \
  host.docker.internal:7005 \
  --cluster-replicas 1
