#!/usr/bin/env python3
"""Static server for previewing the build. Avoids os.getcwd(), which the
sandbox refuses.

    python3 tools/serve.py              # localhost only, port 8777
    python3 tools/serve.py 8777 --lan   # also reachable from your phone

--lan binds every interface, so anything on your wi-fi can read this folder
while it runs. Fine at home; don't leave it up on a shared network.
"""
import functools, os, socket, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = [a for a in sys.argv[1:] if not a.startswith("-")]
PORT = int(args[0]) if args else 8777
LAN = "--lan" in sys.argv
HOST = "0.0.0.0" if LAN else "127.0.0.1"


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class H(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *a):
        sys.stderr.write("%s\n" % (fmt % a))


os.chdir(ROOT)
print("  http://127.0.0.1:%d/scaffold.html" % PORT)
if LAN:
    print("  http://%s:%d/scaffold.html   <- from your phone" % (lan_ip(), PORT))
print("  ctrl-c to stop\n")
ThreadingHTTPServer((HOST, PORT), functools.partial(H, directory=ROOT)).serve_forever()
