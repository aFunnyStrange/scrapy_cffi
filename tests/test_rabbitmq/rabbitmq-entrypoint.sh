#!/bin/bash
set -e

NODE_NAME=${RABBITMQ_NODENAME}
MASTER_NODE=${CLUSTER_MASTER:-rabbit1}
EXTERNAL_IP=${EXTERNAL_IP:-}

echo "Node: $NODE_NAME"
echo "Master node: $MASTER_NODE"

# Use longnames if EXTERNAL_IP is provided
if [ -n "$EXTERNAL_IP" ]; then
    export RABBITMQ_USE_LONGNAME=true
    export RABBITMQ_NODENAME="rabbit@${EXTERNAL_IP}"
fi

# Start RabbitMQ server in background
rabbitmq-server &

# Wait for RabbitMQ app to start
echo "Waiting for RabbitMQ app to start..."
until rabbitmqctl node_health_check >/dev/null 2>&1; do
    sleep 2
done

# Join cluster if not master
if [ "$NODE_NAME" != "rabbit@$MASTER_NODE" ]; then
    echo "Joining cluster rabbit@$MASTER_NODE..."
    until rabbitmqctl -n rabbit@$MASTER_NODE node_health_check >/dev/null 2>&1; do
        sleep 2
    done

    rabbitmqctl stop_app
    rabbitmqctl reset
    rabbitmqctl join_cluster rabbit@$MASTER_NODE
    rabbitmqctl start_app
fi

# Keep container running
wait
