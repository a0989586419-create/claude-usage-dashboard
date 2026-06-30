#!/usr/bin/env python3
"""多執行緒靜態伺服器，避免瀏覽器 keep-alive 卡住單執行緒 http.server。"""
import sys, os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

os.chdir(os.path.dirname(os.path.abspath(__file__)))
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8731
ThreadingHTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler).serve_forever()
