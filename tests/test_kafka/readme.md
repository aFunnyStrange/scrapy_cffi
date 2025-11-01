## 1.single
```bash
docker run -d --name kafka \
  -p 9092:9092 \
  -e KAFKA_ENABLE_KRAFT=yes \
  -e KAFKA_CFG_PROCESS_ROLES=broker,controller \
  -e KAFKA_CFG_NODE_ID=1 \
  -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
  -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
  -e KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://localhost:9092 \
  -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  bitnami/kafka:3.7
```

## 2.cluster

#### 2.1 Start the cluster

```bash
docker compose up -d
docker ps
```

#### 2.2 Enter a broker container and test connection
```bash
docker exec -it kafka1 bash
cd /opt/kafka/bin
./kafka-broker-api-versions.sh --bootstrap-server localhost:9092
```

#### 2.3 Stop and clean up the cluster
```bash
docker compose down
```

**Important Notes**:

Unlike RabbitMQ or Redis, Kafka clients must connect **directly to each broker's** `ADVERTISED_LISTENERS`:

- Each Kafka broker must be reachable by the client (publicly accessible if client is outside the LAN).

- Kafka clients **cannot** use a single public entry point to access the whole cluster like Redis Sentinel or RabbitMQ cluster.

- To simulate a single public entry point, you would need additional components like a **load balancer, proxy, or Kafka REST Proxy**.



**Comparison with RabbitMQ / Redis**
| Feature | Kafka | RabbitMQ / Redis |
| ------- | ----- | ---------------- |
| Single public endpoint | ❌ Not supported | ✅ Supported |
| Client aware of nodes	| ✅ Client must know all brokers | ❌ Client connects to entry node / sentinel |
| Broker visibility	| Each broker must be reachable	Internal | cluster handles routing |