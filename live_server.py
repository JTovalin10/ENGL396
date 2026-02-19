#!/usr/bin/env python3
import http.server
import os
import threading
import time
import hashlib
import queue
import socketserver
from pathlib import Path

WATCH_EXTS = {'.html', '.css', '.js', '.jpg', '.jpeg', '.png', '.gif'}

RELOAD_SCRIPT = b"""<script>
(function(){
  var es = new EventSource('/--livereload--');
  es.onmessage = function(){ location.reload(); };
})();
</script>"""

clients = []
clients_lock = threading.Lock()

def get_mtime_hash():
    h = hashlib.md5()
    for p in sorted(Path('.').rglob('*')):
        if p.is_file() and p.suffix.lower() in WATCH_EXTS:
            try:
                h.update(str(p.stat().st_mtime_ns).encode())
            except OSError:
                pass
    return h.hexdigest()

def watcher_thread():
    last = get_mtime_hash()
    while True:
        time.sleep(0.4)
        current = get_mtime_hash()
        if current != last:
            last = current
            with clients_lock:
                for q in clients:
                    try:
                        q.put_nowait(True)
                    except Exception:
                        pass

class LiveReloadHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/--livereload--':
            self._sse_stream()
            return
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, 'index.html')
        if path.endswith('.html') and os.path.isfile(path):
            self._serve_html(path)
            return
        if path.endswith('.css') and os.path.isfile(path):
            self._serve_static(path, 'text/css; charset=utf-8')
            return
        super().do_GET()

    def _serve_html(self, path):
        with open(path, 'rb') as f:
            content = f.read()
        content = content.replace(b'</body>', RELOAD_SCRIPT + b'</body>', 1)
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(content))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(content)

    def _serve_static(self, path, content_type):
        with open(path, 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(content))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(content)

    def _sse_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        q = queue.Queue()
        with clients_lock:
            clients.append(q)
        try:
            while True:
                try:
                    q.get(timeout=25)
                    self.wfile.write(b'data: reload\n\n')
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with clients_lock:
                try:
                    clients.remove(q)
                except ValueError:
                    pass

    def log_message(self, format, *args):
        if '--livereload--' not in str(args[0]):
            super().log_message(format, *args)

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    threading.Thread(target=watcher_thread, daemon=True).start()
    PORT = 8000
    with socketserver.ThreadingTCPServer(('', PORT), LiveReloadHandler) as httpd:
        print(f'Starting server at http://localhost:{PORT}')
        print('Page will refresh automatically when files change.')
        print('Press Ctrl+C to stop.')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServer stopped.')
