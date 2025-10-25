#!/bin/sh
set -e

# Wait for other nodes to start
sleep 5

# Default values (can be overridden by environment variables)
: "${CLUSTER_PORT:=7000}"           # Redis port
: "${CLUSTER_BUS_PORT:=17000}"      # Cluster bus port

# Ensure the nodes.conf file exists
mkdir -p /usr/local/etc/redis
touch /usr/local/etc/redis/nodes.conf

# If the cluster hasn't been created yet, initialize it
if [ ! -f /tmp/cluster_created ]; then
    echo "Waiting 5s to create cluster..."
    sleep 5

    # Automatically create cluster with redis-cli --cluster create
    # Replace <PUBLIC_IP> with actual node IP, or pass via environment variable
    echo "yes" | redis-cli --cluster create \
        <PUBLIC_IP>:7000 \
        <PUBLIC_IP>:7001 \
        <PUBLIC_IP>:7002 \
        <PUBLIC_IP>:7003 \
        <PUBLIC_IP>:7004 \
        <PUBLIC_IP>:7005 \
        --cluster-replicas 1

    # Mark cluster as created
    touch /tmp/cluster_created
fi

# Start Redis server with the provided config
exec redis-server /usr/local/etc/redis/redis.conf
