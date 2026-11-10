"""Small HTTP health endpoint for hosting platforms."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import threading


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args: object) -> None:
        pass


def start_health_server(port: int) -> threading.Thread:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health-server", daemon=True)
    thread.start()
    return thread
