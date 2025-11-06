#!/usr/bin/env python3
"""
Locust load testing file for EMQX cluster with Redis ACL integration.

This test simulates a user that:
1. Connects to Redis and creates an ACL entry
2. Connects to EMQX broker
3. Subscribes to a test topic
4. Publishes a message to that topic
5. Validates message receipt
6. Cleans up the Redis ACL entry
"""

import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import paho.mqtt.client as mqtt
import redis
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
from locust import User, task, events
from locust.exception import StopUser


# Load environment variables
load_dotenv('test/.env')

# Configuration
MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
MQTT_WORKER_PORT = int(os.getenv('MQTT_WORKER_PORT', '1884'))
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
JWT_PRIVATE_KEY_PATH = os.getenv('JWT_PRIVATE_KEY_PATH', 'config/jwt_private_key.pem')

# Load test behavior configuration
MAX_MESSAGES_PER_USER = int(os.getenv('MAX_MESSAGES_PER_USER', '20'))
MESSAGE_WAIT_TIME = float(os.getenv('MESSAGE_WAIT_TIME', '0'))  # Seconds between messages (0 = no wait)

# EMQX cluster nodes for load distribution
EMQX_NODES = [
    (MQTT_HOST, MQTT_PORT),      # Master node
    (MQTT_HOST, MQTT_WORKER_PORT) # Worker node
]

# Load JWT private key
with open(JWT_PRIVATE_KEY_PATH, 'rb') as key_file:
    JWT_PRIVATE_KEY = serialization.load_pem_private_key(
        key_file.read(),
        password=None
    )


def create_jwt_token(subject: str) -> str:
    """
    Create a JWT token with the specified subject.

    Args:
        subject: The subject claim (username)

    Returns:
        Signed JWT token as string
    """
    now_utc = datetime.now(timezone.utc)
    exp_time = now_utc + timedelta(hours=1)

    payload = {
        "user_id": 0,
        "subject": subject,
        "iss": "server",
        "exp": int(exp_time.timestamp()),
        "provId": "",
        "device": str(uuid.uuid4())
    }

    token = jwt.encode(payload, JWT_PRIVATE_KEY, algorithm="RS256")
    return token


class MQTTClient:
    """Wrapper class for MQTT client to track operations."""

    def __init__(self, client_id: str, username: str, password: str, host: str, port: int):
        self.client_id = client_id
        self.username = username
        self.host = host
        self.port = port
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.username_pw_set(username, password)

        self.connected = False
        self.subscribed = False
        self.message_received = False
        self.received_messages = []
        self.connection_time = None
        self.subscribe_time = None
        self.publish_time = None
        self.receive_time = None
        self.connection_result_code = None
        self.connection_error = None

        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish

    def _on_connect(self, client, userdata, flags, rc, properties):
        """Callback for connection events."""
        # Handle both integer and ReasonCode types (MQTT v2 API)
        rc_value = int(rc) if hasattr(rc, '__int__') else rc
        self.connection_result_code = rc_value

        if rc_value == 0:
            self.connected = True
            self.connection_time = time.time()
        else:
            self.connected = False
            # Map MQTT connection result codes to human-readable messages
            error_messages = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized",
                128: "Connection refused - unspecified error",
                129: "Connection refused - malformed packet",
                130: "Connection refused - protocol error",
                131: "Connection refused - implementation specific error",
                132: "Connection refused - unsupported protocol version",
                133: "Connection refused - client identifier not valid",
                134: "Connection refused - bad username or password",
                135: "Connection refused - not authorized",
                136: "Connection refused - server unavailable",
                137: "Connection refused - server busy",
                138: "Connection refused - banned",
                140: "Connection refused - bad authentication method",
                144: "Connection refused - topic name invalid",
                149: "Connection refused - packet too large",
                151: "Connection refused - quota exceeded",
                153: "Connection refused - payload format invalid",
                154: "Connection refused - retain not supported",
                155: "Connection refused - QoS not supported",
                156: "Connection refused - use another server",
                157: "Connection refused - server moved",
                159: "Connection refused - connection rate exceeded",
            }
            self.connection_error = error_messages.get(rc_value, f"Connection refused - error code {rc_value}")

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties):
        """Callback for subscription events."""
        if 0x80 not in granted_qos:  # 0x80 indicates subscription failure
            self.subscribed = True
            self.subscribe_time = time.time()

    def _on_message(self, client, userdata, message):
        """Callback for received messages."""
        self.received_messages.append({
            "topic": message.topic,
            "payload": message.payload.decode(),
            "timestamp": time.time()
        })
        if not self.message_received:
            self.message_received = True
            self.receive_time = time.time()

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        """Callback for publish events."""
        self.publish_time = time.time()

    def connect(self, timeout: int = 10) -> bool:
        """Connect to MQTT broker."""
        try:
            self.client.connect(self.host, self.port, timeout)
            self.client.loop_start()

            # Wait for connection
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            return self.connected
        except ConnectionRefusedError as e:
            self.connection_error = f"Connection refused by broker at {self.host}:{self.port} - {str(e)}"
            return False
        except OSError as e:
            self.connection_error = f"Network error connecting to {self.host}:{self.port} - {str(e)}"
            return False
        except Exception as e:
            self.connection_error = f"Unexpected error connecting to {self.host}:{self.port} - {type(e).__name__}: {str(e)}"
            return False

    def subscribe(self, topic: str, qos: int = 0) -> bool:
        """Subscribe to a topic."""
        if not self.connected:
            return False

        self.client.subscribe(topic, qos)

        # Wait for subscription confirmation
        start_time = time.time()
        while not self.subscribed and (time.time() - start_time) < 5:
            time.sleep(0.1)

        return self.subscribed

    def publish(self, topic: str, payload: str, qos: int = 0) -> bool:
        """Publish a message to a topic."""
        if not self.connected:
            return False

        result = self.client.publish(topic, payload, qos)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def wait_for_message(self, timeout: int = 5) -> bool:
        """Wait for a message to be received."""
        start_time = time.time()
        while not self.message_received and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        return self.message_received

    def disconnect(self):
        """Disconnect from MQTT broker."""
        self.client.loop_stop()
        self.client.disconnect()


class EMQXUser(User):
    """
    Locust user that simulates MQTT client operations with Redis ACL management.

    Each user maintains a single persistent MQTT connection and repeatedly performs
    pub/sub operations on that connection, simulating realistic MQTT client behavior.
    """

    abstract = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = None
        self.mqtt_client = None
        self.username = None
        self.acl_key = None
        self.test_topic = None
        self.messages_sent = 0  # Track number of messages sent by this user

    def _fire_event(self, request_type: str, name: str, start_time: float,
                    exception: Exception = None, response_length: int = 0,
                    response_time: int = None):
        """
        Helper method to fire Locust events for request tracking.

        Args:
            request_type: Type of request (e.g., "MQTT", "Redis")
            name: Name of the operation (e.g., "CONNECT", "PUBLISH")
            start_time: Timestamp when the operation started
            exception: Exception object if operation failed, None if successful
            response_length: Size of response in bytes (default 0)
            response_time: Custom response time in ms (calculated from start_time if not provided)
        """
        if response_time is None:
            response_time = int((time.time() - start_time) * 1000)

        events.request.fire(
            request_type=request_type,
            name=name,
            response_time=response_time,
            response_length=response_length,
            exception=exception,
            context={}
        )

    def on_start(self):
        """
        Initialize resources when user starts:
        1. Connect to Redis
        2. Create unique username and topic
        3. Create Redis ACL
        4. Connect to EMQX (persistent connection)
        5. Subscribe to topic
        """
        try:
            # Initialize Redis connection
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True
            )
            self.redis_client.ping()

            # Generate unique username and topic for this user
            self.username = f"loadtest-{uuid.uuid4().hex[:8]}"
            self.acl_key = f"mqtt_acl:{self.username}"
            self.test_topic = f"chat/test-topic/{uuid.uuid4().hex[:4]}"

            # Create Redis ACL for this user
            self._create_redis_acl()

            # Establish persistent MQTT connection
            self._connect_to_emqx()

            # Subscribe to topic (subscription persists for the connection)
            self._subscribe_to_topic()

        except Exception as e:
            print(f"Failed to initialize user {self.username if self.username else 'unknown'}: {e}")
            raise StopUser()

    def on_stop(self):
        """
        Cleanup when user stops:
        1. Disconnect MQTT client
        2. Delete Redis ACL
        3. Close Redis connection
        """
        if self.mqtt_client:
            self.mqtt_client.disconnect()

        if self.redis_client and self.acl_key:
            try:
                self.redis_client.delete(self.acl_key)
            except Exception:
                pass  # Best effort cleanup

        if self.redis_client:
            self.redis_client.close()

    @task
    def publish_and_receive(self):
        """
        Perform a pub/sub cycle on the persistent connection:
        1. Check if user has reached message limit
        2. Publish a message to the subscribed topic
        3. Validate that the message is received
        4. Wait before next message (if configured)

        This task runs repeatedly until MAX_MESSAGES_PER_USER is reached.
        """
        # Check if user has reached message limit
        if self.messages_sent >= MAX_MESSAGES_PER_USER:
            raise StopUser()  # Stop this user - they've sent their quota

        try:
            # Publish message
            self._publish_message()

            # Validate receipt
            self._validate_message_receipt()

            # Increment message counter
            self.messages_sent += 1

            # Wait before next message if configured
            if MESSAGE_WAIT_TIME > 0:
                time.sleep(MESSAGE_WAIT_TIME)

        except StopUser:
            raise  # Re-raise StopUser to properly stop the user
        except Exception as e:
            # Log error but don't stop the user - connection issues will be reported via events
            print(f"Error in publish_and_receive for {self.username}: {e}")

    def _create_redis_acl(self):
        """Create Redis ACL entry for the test user."""
        start_time = time.time()

        try:
            # Create ACL: allow pubsub (3) on the test topic
            self.redis_client.hset(self.acl_key, self.test_topic, 3)
            self._fire_event("Redis", "1. Push ACL", start_time)
        except Exception as e:
            self._fire_event("Redis", "1. Push ACL", start_time, exception=e)
            raise

    def _connect_to_emqx(self):
        """Connect to EMQX broker with JWT authentication."""
        start_time = time.time()
        selected_host = None
        selected_port = None

        try:
            # Create JWT token
            jwt_token = create_jwt_token(self.username)

            # Randomly select a node from the cluster for load distribution
            selected_host, selected_port = random.choice(EMQX_NODES)

            # Create MQTT client
            self.mqtt_client = MQTTClient(
                client_id=self.username,
                username=self.username,
                password=jwt_token,
                host=selected_host,
                port=selected_port
            )

            # Connect
            success = self.mqtt_client.connect(timeout=10)

            if not success:
                # Build detailed error message
                error_details = [
                    f"Failed to connect to EMQX at {selected_host}:{selected_port}",
                    f"Client ID: {self.username}",
                    f"Username: {self.username}",
                ]

                # Add connection result code if available
                if self.mqtt_client.connection_result_code is not None:
                    error_details.append(f"Result Code: {self.mqtt_client.connection_result_code}")

                # Add human-readable error if available
                if self.mqtt_client.connection_error:
                    error_details.append(f"Error: {self.mqtt_client.connection_error}")
                else:
                    error_details.append("Error: Connection timeout (no response from broker)")

                error_message = " | ".join(error_details)
                raise Exception(error_message)

            # Fire success event
            self._fire_event("MQTT", "2. CONNECT", start_time)
        except Exception as e:
            # Enhance exception message with context if not already detailed
            if selected_host and selected_port and "Failed to connect to EMQX" not in str(e):
                enhanced_error = f"Connection error at {selected_host}:{selected_port} for user {self.username}: {str(e)}"
                enhanced_exception = Exception(enhanced_error)
            else:
                enhanced_exception = e

            self._fire_event("MQTT", "2. CONNECT", start_time, exception=enhanced_exception)
            raise enhanced_exception

    def _subscribe_to_topic(self):
        """Subscribe to the test topic."""
        start_time = time.time()

        try:
            success = self.mqtt_client.subscribe(self.test_topic, qos=0)

            if not success:
                raise Exception(f"Failed to subscribe to {self.test_topic}")

            self._fire_event("MQTT", "3. SUBSCRIBE", start_time)
        except Exception as e:
            self._fire_event("MQTT", "3. SUBSCRIBE", start_time, exception=e)
            raise

    def _publish_message(self):
        """Publish a test message to the topic."""
        start_time = time.time()

        try:
            test_message = f"Load test message from {self.username}"
            success = self.mqtt_client.publish(self.test_topic, test_message, qos=0)

            if not success:
                raise Exception(f"Failed to publish to {self.test_topic}")

            self._fire_event("MQTT", "4. PUBLISH", start_time, response_length=len(test_message))
        except Exception as e:
            self._fire_event("MQTT", "4. PUBLISH", start_time, exception=e)
            raise

    def _validate_message_receipt(self):
        """Validate that the published message was received."""
        start_time = time.time()

        try:
            success = self.mqtt_client.wait_for_message(timeout=5)

            if not success:
                raise Exception("Did not receive published message")

            # Calculate end-to-end latency
            if self.mqtt_client.publish_time and self.mqtt_client.receive_time:
                latency = int((self.mqtt_client.receive_time - self.mqtt_client.publish_time) * 1000)
            else:
                latency = int((time.time() - start_time) * 1000)

            self._fire_event("MQTT", "5. RECEIVE", start_time, response_time=latency)
        except Exception as e:
            self._fire_event("MQTT", "5. RECEIVE", start_time, exception=e)
            raise

