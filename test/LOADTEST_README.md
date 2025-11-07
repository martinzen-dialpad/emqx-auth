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

# Cross-Node Test Behavior
ENABLE_CROSS_NODE_TEST=true   # Enable cross-node message routing tests (default: true)
CROSS_NODE_TEST_WEIGHT=1      # Task weight for cross-node tests relative to main task (default: 1)
```

**Connection Distribution**: The load test will randomly distribute connections between `MQTT_HOST:MQTT_PORT` (master) and `MQTT_HOST:MQTT_WORKER_PORT` (worker) to simulate cluster load balancing.

**Message Behavior**:
- Each user sends up to `MAX_MESSAGES_PER_USER` messages, then stops
- `MESSAGE_WAIT_TIME` controls the pause between messages (0 = rapid-fire, 0.5 = one message every 500ms)
- With 10 users and MAX_MESSAGES_PER_USER=20, you'll see exactly **200 total messages** (10 users × 20 messages)

**Cross-Node Testing**:
- When enabled, adds an additional task that explicitly tests cross-node message routing
- All users subscribe to a shared broadcast topic (`chat/broadcast/loadtest`) in addition to their unique topics
- Users randomly publish to the broadcast topic, forcing messages to route between cluster nodes
- `CROSS_NODE_TEST_WEIGHT` controls how often cross-node tests run relative to same-node tests:
  - Weight = 1 (default): ~9% of operations are cross-node (1 out of 11)
  - Weight = 5: ~33% of operations are cross-node (5 out of 15)
  - Weight = 10: ~50% of operations are cross-node (10 out of 20)
- Separate metrics track cross-node latency vs same-node latency for performance comparison

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
7. **Cross-Node Message Routing**: Explicitly validates that messages published to one node are correctly routed to subscribers on other nodes

### Metrics Reported

- **Request stats**: Success/failure rates for each operation (CONNECT, SUBSCRIBE, PUBLISH, RECEIVE, CROSS_NODE_PUBLISH, CROSS_NODE_RECEIVE)
- **Response times**: 50th, 66th, 75th, 80th, 90th, 95th, 98th, 99th, 99.9th, 99.99th, 100th percentiles
- **Requests per second**: Throughput for each operation
- **Failures**: Detailed error messages for any failures
- **Cross-Node Latency**: Separate tracking for cross-node message latency vs same-node latency

## Interpreting Results

### Successful Test Run

A successful load test should show:
- ✅ 0% failure rate for all operations
- ✅ Consistent response times (no wild fluctuations)
- ✅ Stable RPS (requests per second) throughout the test
- ✅ End-to-end latency under acceptable threshold (typically < 100ms for local testing)

### Example Output (10 users, 30 seconds, with cross-node testing)

```
Type     Name                         # reqs      # fails  |     Avg     Min     Max  Median  |   req/s
--------|----------------------------|-----------|----------|------------|--------------------------|--------
Redis    1. Push ACL                      10          0      |       5       2      12       4   |    0.33
MQTT     2. CONNECT                       10          0      |     110     105     118     110   |    0.33
MQTT     3. SUBSCRIBE                     10          0      |     102     100     108     100   |    0.33
MQTT     4. PUBLISH                      180          0      |       0       0       1       0   |    6.00
MQTT     5. RECEIVE                      180          0      |       8       6      14       8   |    6.00
MQTT     6. CROSS_NODE_PUBLISH            20          0      |       0       0       1       0   |    0.67
MQTT     7. CROSS_NODE_RECEIVE            20          0      |      12       9      18      12   |    0.67
--------|----------------------------|-----------|----------|------------|--------------------------|--------
         Aggregated                      430          0      |       4       0     118       0   |   14.33
```

**Key observations**:
- **10 connections** exactly (one per user)
- **10 subscriptions** (one per user, established once for both unique and broadcast topics)
- **180 same-node pub/sub operations** (users publishing to their own topics)
- **20 cross-node pub/sub operations** (users publishing to shared broadcast topic)
- **Cross-node latency** (~12ms avg) slightly higher than same-node latency (~8ms avg)
- **0% failure rate** for all operations including cross-node routing
- With default weight=1, ~10% of operations test cross-node routing (20/200 total messages)

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

5. **Cross-Node Stress Test** (emphasis on inter-node communication)
   ```bash
   # Set higher weight for cross-node tests (50% of operations)
   # Temporarily edit test/.env: CROSS_NODE_TEST_WEIGHT=10
   uv run locust -f test/load_test.py --users 100 --spawn-rate 10 --run-time 5m --headless
   ```
   This scenario heavily tests EMQX's cluster message routing by making half of all operations cross-node.

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

**Issue**: Cross-node test failures or high latency
```
Solution:
1. Verify both EMQX nodes are healthy and in the cluster (check dashboard)
2. Check Erlang distribution is working: docker exec -it emqx.master emqx_ctl cluster status
3. Verify nodes can communicate over port 6369 (Erlang distribution)
4. If testing on single node, disable cross-node tests: ENABLE_CROSS_NODE_TEST=false in test/.env
```

### Disabling Cross-Node Tests

If you want to test only same-node performance or are running a single-node setup, disable cross-node tests:

```bash
# Edit test/.env
ENABLE_CROSS_NODE_TEST=false
```

Or temporarily disable via command line:
```bash
ENABLE_CROSS_NODE_TEST=false uv run locust -f test/load_test.py --config test/locust.conf --headless
```

### Debug Mode

Run with verbose logging:

```bash
uv run locust -f test/locustfile.py --loglevel DEBUG --logfile test/debug.log
```

## Next Steps

- Add custom shapes for ramping load patterns
- Add network partition testing (simulate node failures)
- Implement QoS 1/2 testing for guaranteed message delivery
- Add monitoring integration (Prometheus, Grafana)
- Test retained messages across cluster nodes
