"""Deterministic Ollama stand-in inside the isolated E2E network only."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if os.environ.get("BORDERGROUP_E2E") != "1":
    raise SystemExit("This server is only for isolated synthetic E2E tests")

release = threading.Event()
release.set()
started = threading.Event()
fail_response = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        elif self.path == "/state":
            self.reply(200, {"started": started.is_set()})
        else:
            self.reply(404, {})

    def do_POST(self):
        global fail_response
        length = int(self.headers.get("Content-Length", 0))
        if length > 1024 * 1024:
            self.reply(413, {})
            return
        self.rfile.read(length)
        if self.path == "/hold":
            fail_response = False
            started.clear()
            release.clear()
            self.reply(200, {})
        elif self.path == "/fail":
            fail_response = True
            release.set()
            self.reply(200, {})
        elif self.path == "/release":
            release.set()
            self.reply(200, {})
        elif self.path == "/api/chat":
            started.set()
            if not release.wait(20):
                self.reply(503, {"error": "Test did not release the response"})
                return
            if fail_response:
                self.reply(503, {"error": "Synthetic model failure"})
                return
            self.reply(200, {"message": {"content": "SYNTHETIC ANALYSIS: training matches the measure"}})
        else:
            self.reply(404, {})


ThreadingHTTPServer(("0.0.0.0", 11434), Handler).serve_forever()
