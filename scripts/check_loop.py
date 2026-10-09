"""Exercise the real HTTP/action/observation loop against Carla with a local model stub.

Run inside the desktop container with Carla idle and no dialogs open.
No Runpod request or real credential is used.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess
import threading

import xa11y

app = xa11y.App.find(lambda a: 'carla' in a.name.lower())
before = {w.name for w in app.windows() if w.visible}
calls = []
actions = [
    {'action': 'press', 'app': app.name, 'selector': 'button[name*="Add Plugin"][visible="true"]',
     'reason': 'Exercise an accessibility action'},
    {'action': 'key', 'key': 'Escape', 'held': [], 'reason': 'Exercise native input'},
    {'action': 'finish', 'status': 'passed', 'summary': 'Dialog opened and closed',
     'evidence': 'Stub verified accessible window changes after both actions',
     'reason': 'All deterministic UI checks passed'},
]


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        index = len(calls)
        calls.append(body)
        current = {w.name for w in app.windows() if w.visible}
        image_parts = [p for m in body['messages'] if isinstance(m['content'], list)
                       for p in m['content'] if p['type'] == 'image_url']
        condition = len(image_parts) == 1 and self.path == '/v1/chat/completions'
        condition = condition and (index != 1 or bool(current - before))
        condition = condition and (index != 2 or not (current - before))
        if not condition or index >= len(actions):
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'choices': [{'message': {
            'role': 'assistant', 'content': json.dumps(actions[index])}}]}).encode())


server = HTTPServer(('127.0.0.1', 0), Stub)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    result = subprocess.run(['linuxpilot', 'run', 'Open then close Add Plugin', '--max-steps', '3'],
        env={**os.environ, 'HOLO_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1',
             'HOLO_API_KEY': 'local-test-key', 'HOLO_MODEL': 'holo'})
    assert result.returncode == 0, f'Agent loop failed with code {result.returncode}'
    assert len(calls) == 3, f'Expected three observations, got {len(calls)}'
    print('Real desktop + HTTP agent loop passed (local stub; no Holo quality claim).')
finally:
    server.shutdown()
    thread.join()
    server.server_close()
