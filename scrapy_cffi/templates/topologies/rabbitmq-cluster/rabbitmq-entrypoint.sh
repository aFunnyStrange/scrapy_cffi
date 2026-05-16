#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${RABBITMQ_NODENAME:?RABBITMQ_NODENAME is required}"
MASTER_NODE="${CLUSTER_MASTER:-rabbit1}"
MASTER_NODENAME="rabbit@${MASTER_NODE}"

rabbitmq-server &
pid="$!"

until rabbitmq-diagnostics -q ping >/dev/null 2>&1; do
  sleep 2
done

if [[ "${NODE_NAME}" != "${MASTER_NODENAME}" ]]; then
  until rabbitmq-diagnostics -q -n "${MASTER_NODENAME}" ping >/dev/null 2>&1; do
    sleep 2
  done
  rabbitmqctl stop_app
  rabbitmqctl reset
  rabbitmqctl join_cluster "${MASTER_NODENAME}"
  rabbitmqctl start_app
fi

wait "${pid}"
