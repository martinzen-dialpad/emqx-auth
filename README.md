# EMQX authentication + authorization demo

This repo implements a proof of concept demo'ing EMQX's auth capabilities. It's currently configured to first validate JWT authentication via the `config/emqx_auth_jwt.conf` configuration file and then enforcing client-based authorization via Redis-based ACLs.

# Setup

## Service creation

Run `docker compose up` or `podman compose up`. This will start a Redis container and a dependent EMQX container and also push some test ACLs into the Redis instance:

```sh
HSET mqtt_acl:server chat/+/0 3
HSET mqtt_acl:a chat/a/0 3
HSET mqtt_acl:b chat/b/0 3
```

> NOTE #1: the last element in the ACL definition is as follows:
> - 1: subscribe
> - 2: publish
> - 3: pubsub

The EMQX default credentials are as follows (password can be changed in `.env`):

> - username: admin
> - password: Adminadmin0

Feel free to modify/expand these ACLs if you want to test a different set of use cases (more clients, different topic names, etc).



## MQTT client setup

You can use a client MQTT client library or a UI-based tool like [MQTTX](https://mqttx.app) to interact with the EMQX container.

Once you install an MQTT client, setup the connections for the clients you want to test, making sure the client names match the ACLs being pushed into Redis.

## MQTT connection

Use the key pair `jwt_public_key.pem`/`jwt_private_key.pem` to issue JWTs for your clients (by using a JWT library or a service like [jwt.io](https://www.jwt.io/)).

The body of the JWT should look something like this:

```json
{
  "user_id": 50736477,
  "subject": "<username>",
  "iss": "Server",
  "exp": 1767225600,
  "iat": 1757521062,
  "provId": 50212706,
  "device": "2a54ab61-73d1-4232-ab0d-bbc34200c52b"
}
```

Once it's encoded just pass the JWT in the `password` field inside the MQTT connection and the JWT's `subject` field value as username in the MQTT connection.

The EMQX container is configured to use the public key to validate the signature of the JWTs it receives during connection.

### MQTT pub/sub

Once a client connection is established try subscribing and/or publishing to the topics that the client is authorized to interact with in the ACLs you pushed to Redis.

## Testing

This repository includes a comprehensive integration test suite that validates MQTT authentication and authorization functionality. The tests cover:

- **Authentication**: JWT token validation and connection handling
- **Authorization**: ACL-based topic access control for different users
- **Message Delivery**: End-to-end message flow between multiple clients

### Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package manager
- Docker or Podman for running the MQTT container stack

### Running Tests

The test suite uses a simple Makefile workflow:

```bash
# 1. Start the MQTT container stack (EMQX + Redis)
make start

# 2. Run the integration tests
make test

# 3. Tear down the MQTT container stack
make stop
```

The test suite includes:
- Failed authentication with empty credentials
- Successful authentication with valid JWT tokens
- Server authorization for multiple topic subscriptions
- User authorization with publish/subscribe operations
- Multi-client message delivery validation

Test results include detailed output showing JWT token generation, connection status, and step-by-step validation of each operation.
