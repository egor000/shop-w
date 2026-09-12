"""Manual browser fault harness: delay polls and lose one submission acknowledgement.

Run after Compose starts: python tests/disrupted_proxy.py
Open http://localhost:8092. Wait for Ready, then submit while the next poll is in
flight. The first question is forwarded/accepted but its acknowledgement becomes
503. Even after the older delayed GET returns, Reconnect and retry must remain
visible. Clicking it must recover exactly one question and its saved answer.
This is a network test fixture, never part of the application deployment.
"""
import http.client
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class DisruptedProxy(BaseHTTPRequestHandler):
    lock = threading.Lock()
    lose_ack = True

    def log_message(self, format, *args):
        pass  # Do not log request bodies, cookies or URLs.

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def forward(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        connection = http.client.HTTPConnection("127.0.0.1", 8091, timeout=10)
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in {"host", "connection"}}
        connection.request(self.command, self.path, body, headers)
        upstream = connection.getresponse()
        data = upstream.read()
        status = upstream.status
        response_headers = upstream.getheaders()
        connection.close()
        if self.command == "GET" and self.path.startswith("/api/conversations/"):
            print("Holding poll response for 6 seconds", flush=True)
            time.sleep(6)
        if self.command == "POST" and self.path.endswith("/questions"):
            with self.lock:
                if type(self).lose_ack:
                    type(self).lose_ack = False
                    status = 503
                    data = b'{"detail":"Simulated lost acknowledgement"}'
                    print("Question forwarded; acknowledgement withheld", flush=True)
        self.send_response(status)
        for key, value in response_headers:
            if key.lower() not in {"content-length", "transfer-encoding", "connection"}:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


if __name__ == "__main__":
    print("Browser fault harness: http://localhost:8092", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8092), DisruptedProxy).serve_forever()
