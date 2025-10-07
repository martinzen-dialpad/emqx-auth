#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

class AuthHandler(BaseHTTPRequestHandler):

    def respond(self, status_code: int, response):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())


    def do_POST(self):
        # Get content length, defaulting to 0 if not present
        content_length = int(self.headers.get('Content-Length', 0))
        webhook_name = self.headers.get('vernemq-hook', '[NONE]')

        # Read request body if present
        request_body = self.rfile.read(content_length) if content_length > 0 else b'{}'

        try:
            data = json.loads(request_body)
        except json.JSONDecodeError:
            data = {}

        # Log the request
        print(f"Received {self.path}, webhook: '{webhook_name}'. request with data: {data}")

        if webhook_name == 'auth_on_register_m5':
            password = data['password']
            username = data['username']
            print(f'Client connecting: user "{username}", password: "{password}"')
            if (username is None or password is None):
                self.respond(200, {"result": {"error": "not_allowed"}})
                return

        self.respond(200, {'result': 'ok'})

    def log_message(self, format, *args):
        # Custom logging
        print(f"{self.address_string()} - {format % args}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT'))
    server_address = ('', port)
    httpd = HTTPServer(server_address, AuthHandler)
    print(f'Auth server running on port {port}...')
    httpd.serve_forever()
