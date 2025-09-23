#!/usr/bin/env python3
"""
Integration tests for MQTT authentication and authorization using JWT tokens.

This test suite validates:
1. Failed authentication when using empty credentials
2. Successful authentication when using valid JWT token
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


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
