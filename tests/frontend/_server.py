import atexit
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


def frontend_url():
    override = os.environ.get("FRONT_URL")
    if override:
        return override.rstrip("/") + "/"

    frontend = Path(__file__).resolve().parents[2] / "frontend"

    class NoCacheHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(NoCacheHandler, directory=str(frontend))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    atexit.register(stop)
    return f"http://127.0.0.1:{server.server_port}/"
