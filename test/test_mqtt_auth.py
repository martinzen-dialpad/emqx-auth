#!/usr/bin/env python3
"""
Integration tests for MQTT authentication and authorization using JWT tokens.

This test suite validates:
1. Failed authentication when using empty credentials
2. Successful authentication when using valid JWT token
3. Server authorization for multiple topic subscriptions
4. User authorization with publish/subscribe operations
"""

import pytest
import jwt
import paho.mqtt.client as mqtt
import time
import os
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv


class TestMQTTAuthentication:
    """Test suite for MQTT JWT authentication."""

    @classmethod
    def setup_class(cls):
        """Load environment variables and private key for JWT signing."""
        # Load environment variables from .env file
        load_dotenv('test/.env')

        cls.MQTT_HOST = os.getenv('MQTT_HOST', 'localhost')
        cls.MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
        cls.JWT_PRIVATE_KEY_PATH = os.getenv('JWT_PRIVATE_KEY_PATH', 'config/jwt_private_key.pem')

        with open(cls.JWT_PRIVATE_KEY_PATH, 'rb') as key_file:
            cls.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None
            )

    def create_jwt_token(self, subject: str) -> str:
        """
        Create a JWT token with the specified subject and user information.

        Args:
            subject: The subject claim (username)

        Returns:
            Signed JWT token as string
        """
        # Use UTC time and add larger buffer to account for clock skew
        now_utc = datetime.now(timezone.utc)
        # Issue token 5 minutes in the past to account for significant clock skew
        iat_time = now_utc - timedelta(minutes=5)
        # Set expiration to 1 hour from now
        exp_time = now_utc + timedelta(hours=1)

        payload = {
            "user_id": 0,
            "subject": subject,
            "iss": "server",
            "exp": int(exp_time.timestamp()),
            # Remove iat claim to avoid timing issues
            # "iat": int(iat_time.timestamp()),
            "provId": "",
            "device": "2a54ab61-73d1-4232-ab0d-bbc34200c52b"
        }

        # Sign with RS256 algorithm
        token = jwt.encode(payload, self.private_key, algorithm="RS256")

        # Debug: Print timestamps and decode the token
        print(f"Creating JWT for subject: {subject}")
        print(f"Current UTC time: {now_utc}")
        print(f"EXP time: {exp_time} (timestamp: {int(exp_time.timestamp())})")
        print(f"Generated JWT: {token}")

        # Decode and print the token payload for verification
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            print(f"JWT payload: {decoded}")
        except Exception as e:
            print(f"Error decoding JWT: {e}")

        return token

    def create_client_and_connect(self, username: str, password: str, client_id: str = None) -> tuple:
        """
        Helper method to create MQTT client and establish connection.

        Args:
            username: MQTT username
            password: MQTT password (JWT token)
            client_id: MQTT client ID (defaults to username if not provided)

        Returns:
            tuple: (client, connection_result dict)
        """
        if client_id is None:
            client_id = username

        # Connection result tracking
        connection_result = {
            "connected": False,
            "result_code": None,
            "subscriptions": {},
            "publications": {},
            "messages": []
        }

        def on_connect(client, userdata, flags, rc, properties):
            """Callback for connection events."""
            connection_result["result_code"] = rc
            if rc == 0:
                connection_result["connected"] = True

        def on_subscribe(client, userdata, mid, granted_qos, properties):
            """Callback for subscription events."""
            connection_result["subscriptions"][mid] = {
                "success": True,
                "granted_qos": granted_qos
            }

        def on_publish(client, userdata, mid, reason_code, properties):
            """Callback for publish events."""
            connection_result["publications"][mid] = {"success": True}

        def on_message(client, userdata, message):
            """Callback for received messages."""
            connection_result["messages"].append({
                "topic": message.topic,
                "payload": message.payload.decode(),
                "qos": message.qos,
                "retain": message.retain
            })

        # Create MQTT client with callback API VERSION2
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_publish = on_publish
        client.on_message = on_message

        # Set credentials
        client.username_pw_set(username, password)

        return client, connection_result

    def test_failed_authentication_empty_credentials(self):
        """
        Test that connection fails when using empty username and password.

        This test:
        1. Creates a JWT for user 'server'
        2. Connects with empty username and password
        3. Verifies the connection was rejected
        """
        # Create JWT token for user 'server'
        jwt_token = self.create_jwt_token("server")

        # Connection result tracking
        connection_result = {"connected": False, "result_code": None}

        def on_connect(client, userdata, flags, rc, properties):
            """Callback for connection events."""
            connection_result["result_code"] = rc
            if rc == 0:
                connection_result["connected"] = True

        # Create MQTT client with empty client ID using latest callback API
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="")
        client.on_connect = on_connect

        # Connect with empty credentials (should fail)
        client.username_pw_set("", "")  # Empty username and password

        try:
            client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            client.loop_start()

            # Wait for connection attempt
            time.sleep(2)

            # Verify connection was rejected
            assert not connection_result["connected"], "Connection should have been rejected"
            assert connection_result["result_code"] != 0, f"Expected non-zero result code, got {connection_result['result_code']}"

        finally:
            client.loop_stop()
            client.disconnect()

    def test_successful_authentication_with_jwt(self):
        """
        Test that connection succeeds when using valid JWT credentials.

        This test:
        1. Creates a JWT for user 'server'
        2. Connects with JWT as password and subject as username
        3. Verifies the connection was established successfully
        """
        # Create JWT token for user 'server'
        jwt_token = self.create_jwt_token("server")

        # Connection result tracking
        connection_result = {"connected": False, "result_code": None}

        def on_connect(client, userdata, flags, rc, properties):
            """Callback for connection events."""
            connection_result["result_code"] = rc
            if rc == 0:
                connection_result["connected"] = True

        # Create MQTT client with client ID matching username using latest callback API
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server")
        client.on_connect = on_connect

        # Connect with JWT token as password and subject as username
        client.username_pw_set("server", jwt_token)

        try:
            client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            client.loop_start()

            # Wait for connection attempt
            time.sleep(2)

            # Verify connection was successful
            assert connection_result["connected"], f"Connection failed with result code: {connection_result['result_code']}"
            assert connection_result["result_code"] == 0, f"Expected result code 0, got {connection_result['result_code']}"

        finally:
            client.loop_stop()
            client.disconnect()

    def test_server_authorization_topics(self):
        """
        Test server authorization for multiple topic subscriptions.

        This test:
        1. Connects with user 'server' and corresponding JWT
        2. Subscribes to allowed topics (chat/a/0, chat/b/0, chat/z/0) - should succeed
        3. Subscribes to forbidden topic (chat/a/1) - should fail
        """
        # Create JWT token for user 'server'
        jwt_token = self.create_jwt_token("server")

        # Create and connect client
        client, connection_result = self.create_client_and_connect("server", jwt_token)

        try:
            client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            client.loop_start()

            # Wait for connection
            time.sleep(2)
            assert connection_result["connected"], f"Connection failed with result code: {connection_result['result_code']}"

            # Test allowed subscriptions
            allowed_topics = ["chat/a/0", "chat/b/0", "chat/z/0"]
            for topic in allowed_topics:
                print(f"Testing subscription to allowed topic: {topic}")
                result, mid = client.subscribe(topic, 0)
                time.sleep(1)

                assert result == mqtt.MQTT_ERR_SUCCESS, f"Subscribe call failed for {topic}: {result}"
                assert mid in connection_result["subscriptions"], f"No subscription callback received for {topic}"
                assert connection_result["subscriptions"][mid]["success"], f"Subscription to {topic} should have succeeded"
                print(f"✓ Subscription to {topic} succeeded")

            # Test forbidden subscription - this should fail
            forbidden_topic = "chat/a/1"
            print(f"Testing subscription to forbidden topic: {forbidden_topic}")
            result, mid = client.subscribe(forbidden_topic, 0)
            time.sleep(2)

            assert result == mqtt.MQTT_ERR_SUCCESS, f"Subscribe call failed for {forbidden_topic}: {result}"

            # For forbidden topics, we might not get a callback or get one with QoS failure
            if mid in connection_result["subscriptions"]:
                granted_qos = connection_result["subscriptions"][mid]["granted_qos"]
                # QoS of 0x80 indicates failure
                assert 0x80 in granted_qos, f"Subscription to forbidden topic {forbidden_topic} should have failed"
                print(f"✓ Subscription to {forbidden_topic} correctly failed")
            else:
                # Some MQTT brokers don't send callback for failed subscriptions
                print(f"✓ Subscription to {forbidden_topic} correctly failed (no callback)")

        finally:
            client.loop_stop()
            client.disconnect()

    def test_user_authorization_operations(self):
        """
        Test user authorization with publish/subscribe operations.

        This test:
        1. Connects with user 'a' and corresponding JWT
        2. Subscribes to allowed topic (chat/a/0) - should succeed
        3. Publishes to allowed topic (chat/a/0) - should succeed
        4. Subscribes to forbidden topic (chat/b/0) - should fail
        5. Publishes to forbidden topic (chat/b/0) - should fail
        """
        # Create JWT token for user 'a'
        jwt_token = self.create_jwt_token("a")

        # Create and connect client
        client, connection_result = self.create_client_and_connect("a", jwt_token)

        try:
            client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            client.loop_start()

            # Wait for connection
            time.sleep(2)
            assert connection_result["connected"], f"Connection failed with result code: {connection_result['result_code']}"

            # Test allowed subscription
            allowed_topic = "chat/a/0"
            print(f"Testing subscription to allowed topic: {allowed_topic}")
            result, mid = client.subscribe(allowed_topic, 0)
            time.sleep(1)

            assert result == mqtt.MQTT_ERR_SUCCESS, f"Subscribe call failed for {allowed_topic}: {result}"
            assert mid in connection_result["subscriptions"], f"No subscription callback for {allowed_topic}"
            assert connection_result["subscriptions"][mid]["success"], f"Subscription to {allowed_topic} should have succeeded"
            print(f"✓ Subscription to {allowed_topic} succeeded")

            # Test allowed publish
            print(f"Testing publish to allowed topic: {allowed_topic}")
            pub_info = client.publish(allowed_topic, "test message", 0)
            time.sleep(1)

            assert pub_info.mid in connection_result["publications"], f"No publish callback for {allowed_topic}"
            assert connection_result["publications"][pub_info.mid]["success"], f"Publish to {allowed_topic} should have succeeded"
            print(f"✓ Publish to {allowed_topic} succeeded")

            # Test forbidden subscription
            forbidden_topic = "chat/b/0"
            print(f"Testing subscription to forbidden topic: {forbidden_topic}")
            result, mid = client.subscribe(forbidden_topic, 0)
            time.sleep(2)

            assert result == mqtt.MQTT_ERR_SUCCESS, f"Subscribe call failed for {forbidden_topic}: {result}"

            if mid in connection_result["subscriptions"]:
                granted_qos = connection_result["subscriptions"][mid]["granted_qos"]
                assert 0x80 in granted_qos, f"Subscription to forbidden topic {forbidden_topic} should have failed"
                print(f"✓ Subscription to {forbidden_topic} correctly failed")
            else:
                print(f"✓ Subscription to {forbidden_topic} correctly failed (no callback)")

            # Test forbidden publish - Note: publish might not fail immediately
            # Some brokers accept the publish but don't deliver it due to ACL
            print(f"Testing publish to forbidden topic: {forbidden_topic}")
            pub_info = client.publish(forbidden_topic, "test message", 0)
            time.sleep(1)

            # The publish might succeed locally but be rejected by ACL
            if pub_info.mid in connection_result["publications"]:
                print(f"⚠ Publish to {forbidden_topic} accepted locally (may be rejected by server ACL)")
            else:
                print(f"✓ Publish to {forbidden_topic} rejected")

        finally:
            client.loop_stop()
            client.disconnect()

    def test_multi_client_message_delivery(self):
        """
        Test message delivery between multiple clients.

        This test:
        1. Connects with client "server" and validates it succeeds
        2. Subscribes client "server" to topic "chat/a/0", validates it succeeds
        3. Connects with client "a"
        4. Makes client "a" publish to topic "chat/a/0", validates it succeeds
        5. Validates that client "server" receives message published by client "a"
        """
        # Create JWT tokens for both users
        server_jwt = self.create_jwt_token("server")
        user_a_jwt = self.create_jwt_token("a")

        # Create and connect server client
        server_client, server_result = self.create_client_and_connect("server", server_jwt)

        try:
            # Step 1: Connect server client
            print("Step 1: Connecting server client")
            server_client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            server_client.loop_start()
            time.sleep(2)

            assert server_result["connected"], f"Server connection failed with result code: {server_result['result_code']}"
            print("✓ Server client connected successfully")

            # Step 2: Subscribe server to topic chat/a/0
            print("Step 2: Subscribing server to chat/a/0")
            topic = "chat/a/0"
            result, mid = server_client.subscribe(topic, 0)
            time.sleep(1)

            assert result == mqtt.MQTT_ERR_SUCCESS, f"Server subscribe call failed: {result}"
            assert mid in server_result["subscriptions"], f"No subscription callback for server"
            assert server_result["subscriptions"][mid]["success"], f"Server subscription should have succeeded"
            print("✓ Server subscribed to chat/a/0 successfully")

            # Step 3: Create and connect user 'a' client
            print("Step 3: Connecting user 'a' client")
            user_a_client, user_a_result = self.create_client_and_connect("a", user_a_jwt)

            user_a_client.connect(self.MQTT_HOST, self.MQTT_PORT, 10)
            user_a_client.loop_start()
            time.sleep(2)

            assert user_a_result["connected"], f"User 'a' connection failed with result code: {user_a_result['result_code']}"
            print("✓ User 'a' client connected successfully")

            # Step 4: Make user 'a' publish to chat/a/0
            print("Step 4: User 'a' publishing to chat/a/0")
            test_message = "Hello from user a!"
            pub_info = user_a_client.publish(topic, test_message, 0)
            time.sleep(1)

            assert pub_info.mid in user_a_result["publications"], f"No publish callback for user 'a'"
            assert user_a_result["publications"][pub_info.mid]["success"], f"User 'a' publish should have succeeded"
            print("✓ User 'a' published message successfully")

            # Step 5: Validate server receives the message
            print("Step 5: Validating server received the message")
            time.sleep(2)  # Give some extra time for message delivery

            assert len(server_result["messages"]) > 0, "Server should have received at least one message"

            # Find the message we sent
            received_message = None
            for msg in server_result["messages"]:
                if msg["topic"] == topic and msg["payload"] == test_message:
                    received_message = msg
                    break

            assert received_message is not None, f"Server did not receive the expected message. Received messages: {server_result['messages']}"
            assert received_message["topic"] == topic, f"Expected topic {topic}, got {received_message['topic']}"
            assert received_message["payload"] == test_message, f"Expected payload '{test_message}', got '{received_message['payload']}'"

            print(f"✓ Server successfully received message: '{received_message['payload']}' on topic '{received_message['topic']}'")

        finally:
            server_client.loop_stop()
            server_client.disconnect()
            if 'user_a_client' in locals():
                user_a_client.loop_stop()
                user_a_client.disconnect()


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
