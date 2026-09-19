#!/usr/bin/env python3

from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

fn = sys.argv[1]

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return

        with open(fn, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/x-apple-aspen-config"
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


HTTPServer(("0.0.0.0", 8000), H).serve_forever()



