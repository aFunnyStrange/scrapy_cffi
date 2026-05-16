#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${RABBITMQ_NODENAME:?RABBITMQ_NODENAME is required}"
MASTER_NODE="${CLUSTER_MASTER:-rabbit1}"
MASTER_NODENAME="rabbit@${MASTER_NODE}"

echo "[entrypoint] node=${NODE_NAME} master=${MASTER_NODENAME}"

rabbitmq-server &
pid="$!"

echo "[entrypoint] waiting for local RabbitMQ to become healthy..."
until rabbitmq-diagnostics -q ping >/dev/null 2>&1; do
  sleep 2
done

if [[ "${NODE_NAME}" != "${MASTER_NODENAME}" ]]; then
  echo "[entrypoint] waiting for master ${MASTER_NODENAME}..."
  until rabbitmq-diagnostics -q -n "${MASTER_NODENAME}" ping >/dev/null 2>&1; do
    sleep 2
  done

  # Join is idempotent enough for local test restarts.
  rabbitmqctl stop_app
  rabbitmqctl reset
  rabbitmqctl join_cluster "${MASTER_NODENAME}"
  rabbitmqctl start_app
fi

wait "${pid}"
