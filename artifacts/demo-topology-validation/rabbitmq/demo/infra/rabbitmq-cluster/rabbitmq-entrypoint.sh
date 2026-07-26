#!/usr/bin/env bash
set -euo pipefail

NODE_NAME="${RABBITMQ_NODENAME:?RABBITMQ_NODENAME is required}"
MASTER_NODE="${CLUSTER_MASTER:-rabbit1}"
MASTER_NODENAME="rabbit@${MASTER_NODE}"

rabbitmq-server &
pid="$!"

# `ping` only proves the Erlang VM is alive. Joining while the Rabbit
# application is still booting can terminate the node with exit 69.
until rabbitmq-diagnostics -q check_running >/dev/null 2>&1; do
  sleep 2
done

if [[ "${NODE_NAME}" != "${MASTER_NODENAME}" ]]; then
  until rabbitmq-diagnostics -q -n "${MASTER_NODENAME}" check_running >/dev/null 2>&1; do
    sleep 2
  done
  rabbitmqctl stop_app
  rabbitmqctl reset
  rabbitmqctl join_cluster "${MASTER_NODENAME}"
  rabbitmqctl start_app
  rabbitmqctl await_startup
fi

wait "${pid}"
