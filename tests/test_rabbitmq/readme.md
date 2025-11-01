## 1.single
```bash
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

## 2.cluster
1. **Production (LAN / multi-host)**

- Replace `<PUBLIC_IP>` with an accessible LAN or public IP in `docker-compose.yml`.

- All RabbitMQ instances must be on the same LAN.

2. **Single-host simulation**

- Use multiple Docker containers on the same host.

- Ports are mapped differently for each container (`5672`, `5673`, `5674`, etc.).

- Shortnames (`rabbit@rabbit1`) are used automatically.

3. **Start the cluster**
```bash 
docker compose up -d
```

**Important**: Container start does not mean the RabbitMQ nodes are fully ready.

- Each node starts rabbitmq-server in the background.

- The cluster setup (node health checks, joining master, etc.) may take **10–20 seconds** depending on your machine.

You can verify readiness by either:
```bash
# Check cluster status
docker exec -it rabbit1 rabbitmqctl cluster_status
```
or open the management UI and wait until all nodes are listed as running:
```arduino
http://localhost:15672/
```

Run the test script:
```bash
python test_rabbitmq.py
```

After testing:
```bash
docker compose down
```