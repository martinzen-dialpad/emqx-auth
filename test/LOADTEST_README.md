# EMQX Cluster Load Testing with Locust

This directory contains Locust-based load tests for validating the EMQX cluster configuration.

## Overview

The load test simulates realistic MQTT client behavior with **persistent connections**:

### Connection Model

Each Locust user represents a persistent MQTT client that:

1. **Initialization** (on user start):
   - Creates a Redis ACL entry for the user
   - Establishes a **persistent MQTT connection** (distributed across master/worker nodes)
   - Subscribes to a unique test topic

2. **Continuous Operation** (while test runs):
   - Repeatedly publishes messages to the subscribed topic
   - Validates that messages are received (pub/sub loop)
   - Maintains the same connection throughout

3. **Cleanup** (on user stop):
   - Disconnects from EMQX
   - Deletes the Redis ACL entry

This model **accurately simulates real-world MQTT usage** where clients maintain long-lived connections rather than repeatedly connecting/disconnecting.

### Cluster Load Distribution

The load test automatically distributes connections across both EMQX cluster nodes:
- **Master Node**: `localhost:1883` (emqx.master)
- **Worker Node**: `localhost:1884` (emqx.worker)

Each user randomly connects to either the master or worker node during initialization, achieving approximately 50/50 load distribution. With **10 users, you'll see exactly 10 connections** (5 per node on average). You can verify the connection distribution by accessing the EMQX Dashboard at http://localhost:18083 (username: `admin`, password: `Adminadmin0`).

## Prerequisites

- Docker/Podman running the EMQX cluster stack
- Python dependencies installed via `uv sync`
- EMQX cluster running (use `make start`)

## Running Load Tests

### Option 1: Web UI Mode (Recommended for interactive testing)

```bash
make loadtest
```

This will:
- Start Locust with a web UI at http://localhost:8089
- Allow you to configure number of users and spawn rate
- Provide real-time graphs and statistics
- Let you start/stop tests interactively

**Usage:**
1. Open http://localhost:8089 in your browser
2. Set the number of users (e.g., 10)
3. Set the spawn rate (e.g., 2 users per second)
4. Click "Start swarming"
5. Monitor the real-time statistics and charts

### Option 2: Headless Mode (For automation/CI)

```bash
make loadtest-headless
```

This runs the test with pre-configured settings from [locust.conf](locust.conf):
- 10 users
- Spawn rate of 2 users/second
- 1 minute run time

### Option 3: Custom Parameters

```bash
# Run with custom settings
uv run locust -f test/locustfile.py \
  --users 50 \
  --spawn-rate 5 \
  --run-time 2m \
  --headless

# Run with specific host (if different from localhost)
uv run locust -f test/locustfile.py \
  --users 20 \
  --spawn-rate 2 \
  --run-time 1m \
  --headless

# Generate CSV reports
uv run locust -f test/locustfile.py \
  --users 100 \
  --spawn-rate 10 \
  --run-time 5m \
  --headless \
  --csv=test/results/loadtest
```

## Configuration

### Environment Variables

The load test reads configuration from `test/.env`:

```bash
# MQTT Broker Configuration
MQTT_HOST=localhost         # EMQX host
MQTT_PORT=1883             # EMQX master node port
MQTT_WORKER_PORT=1884      # EMQX worker node port

# Redis Configuration
REDIS_HOST=localhost       # Redis host
REDIS_PORT=6379            # Redis port

# Authentication
JWT_PRIVATE_KEY_PATH=config/jwt_private_key.pem

# Load Test Behavior
MAX_MESSAGES_PER_USER=20   # Maximum messages each user will send (default: 20)
MESSAGE_WAIT_TIME=0.5      # Seconds to wait between messages (default: 0.5, use 0 for no wait)
```

**Connection Distribution**: The load test will randomly distribute connections between `MQTT_HOST:MQTT_PORT` (master) and `MQTT_HOST:MQTT_WORKER_PORT` (worker) to simulate cluster load balancing.

**Message Behavior**:
- Each user sends up to `MAX_MESSAGES_PER_USER` messages, then stops
- `MESSAGE_WAIT_TIME` controls the pause between messages (0 = rapid-fire, 0.5 = one message every 500ms)
- With 10 users and MAX_MESSAGES_PER_USER=20, you'll see exactly **200 total messages** (10 users × 20 messages)

### Locust Configuration

Edit [test/locust.conf](locust.conf) to change default settings:

```ini
users = 10              # Number of concurrent MQTT clients (persistent connections)
spawn-rate = 2          # Users spawned per second
run-time = 1m          # Test duration
```

**Important**: The `users` parameter controls the number of **persistent MQTT connections**. With 10 users, you'll see exactly 10 concurrent connections maintained throughout the test.

## What Gets Tested

### Cluster-Specific Validations

1. **Persistent Connection Management**: Validates EMQX can handle multiple long-lived concurrent connections
2. **Authentication Performance**: Tests JWT validation during connection establishment
3. **Authorization Enforcement**: Validates Redis ACL checks are performed correctly
4. **Message Routing**: Ensures pub/sub works correctly under high message throughput
5. **End-to-End Latency**: Measures time from publish to receive for each message
6. **Message Throughput**: Tests how many messages per second can be processed on persistent connections

### Metrics Reported

- **Request stats**: Success/failure rates for each operation (CONNECT, SUBSCRIBE, PUBLISH, RECEIVE)
- **Response times**: 50th, 66th, 75th, 80th, 90th, 95th, 98th, 99th, 99.9th, 99.99th, 100th percentiles
- **Requests per second**: Throughput for each operation
- **Failures**: Detailed error messages for any failures

## Interpreting Results

### Successful Test Run

A successful load test should show:
- ✅ 0% failure rate for all operations
- ✅ Consistent response times (no wild fluctuations)
- ✅ Stable RPS (requests per second) throughout the test
- ✅ End-to-end latency under acceptable threshold (typically < 100ms for local testing)

### Example Output (10 users, 15 seconds)

```
Type     Name                       # reqs      # fails  |     Avg     Min     Max  Median  |   req/s
--------|-------------------------|-----------|----------|------------|--------------------------|--------
MQTT     CONNECT                      10          0      |     106     102     114     110   |    0.72
Redis    HSET ACL                     10          0      |       4       2       8       4   |    0.72
MQTT     SUBSCRIBE                    10          0      |     100     100     101     100   |    0.72
MQTT     PUBLISH                  219527          0      |       0       0       0       0   | 15840.07
MQTT     RECEIVE                  219527          0      |       7       5      16       7   | 15840.07
--------|-------------------------|-----------|----------|------------|--------------------------|--------
         Aggregated               439084          0      |       3       0     114       0   | 31682.31
```

**Key observations**:
- **10 connections** exactly (one per user)
- **10 subscriptions** (one per user, established once)
- **219,527 pub/sub operations** on those 10 persistent connections over 15 seconds
- **~15,840 messages/sec throughput** with 0% failure rate

## Cluster Testing Tips

### Test Scenarios

1. **Baseline Performance**
   ```bash
   uv run locust -f test/locustfile.py --users 10 --spawn-rate 2 --run-time 2m --headless
   ```

2. **High Load**
   ```bash
   uv run locust -f test/locustfile.py --users 100 --spawn-rate 10 --run-time 5m --headless
   ```

3. **Stress Test**
   ```bash
   uv run locust -f test/locustfile.py --users 500 --spawn-rate 50 --run-time 10m --headless
   ```

4. **Endurance Test**
   ```bash
   uv run locust -f test/locustfile.py --users 50 --spawn-rate 5 --run-time 30m --headless
   ```

### Cluster Validation

To validate cluster load balancing behavior:

1. **Monitor both nodes**: Open EMQX dashboard at http://localhost:18083
   - Username: `admin`
   - Password: `Adminadmin0`
   - Navigate to **Cluster** → **Nodes** to see real-time connection counts per node

2. **Verify connection distribution**:
   - Start the load test: `make loadtest` or `make loadtest-headless`
   - In the EMQX dashboard, observe that connections are distributed approximately 50/50 between:
     - `emqx@emqx.master` (port 1883)
     - `emqx@emqx.worker` (port 1884)

3. **Test node failure**:
   ```bash
   # Stop worker node
   docker stop emqx.worker

   # Run load test - should continue with master only
   make loadtest-headless

   # Restart worker
   docker start emqx.worker
   ```

4. **Monitor Redis**: Watch ACL creation/deletion
   ```bash
   docker exec -it redis redis-cli MONITOR
   ```

## Troubleshooting

### Common Issues

**Issue**: Connection failures
```
Solution: Ensure EMQX cluster is running (make start)
```

**Issue**: JWT authentication failures
```
Solution: Verify jwt_private_key.pem exists in config/
```

**Issue**: Redis connection errors
```
Solution: Check Redis is accessible at localhost:6379
```

**Issue**: Subscription failures
```
Solution: Ensure ACLs are being created correctly in Redis
```

### Debug Mode

Run with verbose logging:

```bash
uv run locust -f test/locustfile.py --loglevel DEBUG --logfile test/debug.log
```

## Next Steps

- Extend tests to simulate multi-node client distribution
- Add custom shapes for ramping load patterns
- Implement cross-node message delivery tests
- Add monitoring integration (Prometheus, Grafana)
