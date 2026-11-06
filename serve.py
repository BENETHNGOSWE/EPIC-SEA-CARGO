#!/usr/bin/env python3
"""serve.py — preview the built site exactly as the mirror's paths expect it:
docroot = the repo root, and `/` opens the built homepage.

  python3 serve.py            (port 8090, all interfaces)
"""
import http.server, socketserver, os, sys, functools

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
LANDING = "/"          # the repo root now holds the built home page, same as the live server

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # always show the latest build
        super().end_headers()
    def log_message(self, *a): pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), functools.partial(Handler, directory=ROOT)) as httpd:
    print(f"serving {ROOT} on 0.0.0.0:{PORT}  →  {LANDING}", flush=True)
    httpd.serve_forever()
