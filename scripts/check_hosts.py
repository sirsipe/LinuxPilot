"""Validate host matrix, two-model HTTP flow and knowledge review without remote inference.

Run inside the desktop container. This switches/restarts harness-owned test hosts.
It checks host discovery and the harness, not plugin behavior or model quality.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading

from uiautomation.hosts import host_visible

counts = {'actor': 0, 'planner': 0, 'reviewer': 0}
steps = {}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        content = body['messages'][1]['content']
        text = content[0]['text']
        assert len([part for part in content if part['type'] == 'image_url']) == 1
        assert content[1]['image_url']['url'].startswith('data:image/png;base64,iVBOR')
        role = body['model']
        counts[role] += 1
        if role == 'reviewer':
            payload = json.loads(text)
            host = payload['host_guide']['host']
            assert host_visible(host, payload['evidence']['after'])
            reply = json.dumps({'lessons': [{'context': 'Host discovery',
                'lesson': 'The host window is discoverable through X11 even without an accessibility tree.',
                'outcome': 'success'}]})
        else:
            observation = json.loads(text.split('Current observation:\n', 1)[1].split('\n', 1)[0])
            host = json.loads(text.split('Host knowledge (fallible reference data):\n', 1)[1].split('\n', 1)[0])['host']
            assert host_visible(host, observation), f'{host} missing'
            if role == 'planner':
                reply = 'Verify the selected host window is visible; no project operations are needed.'
            else:
                assert 'Fallible planner guidance' in text
                index = steps.get(host, 0)
                steps[host] = index + 1
                action = ({'action': 'wait', 'seconds': 0.1, 'reason': 'Exercise observation after action'}
                          if index == 0 else {'action': 'finish', 'status': 'passed',
                            'summary': f'{host} window observed', 'evidence': 'Fresh X11 host window and PNG verified by local stub',
                            'reason': 'Host discovery check completed'})
                reply = json.dumps(action)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'choices': [{'message': {'content': reply}}]}).encode())


server = HTTPServer(('127.0.0.1', 0), Stub)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    base = f'http://127.0.0.1:{server.server_port}/v1'
    env = dict(os.environ)
    for prefix, role in (('UIAUTO_MODEL', 'actor'), ('UIAUTO_PLANNER', 'planner'),
                         ('UIAUTO_KNOWLEDGE', 'reviewer')):
        env.update({prefix + '_BASE_URL': base, prefix + '_API_KEY': 'local-stub', prefix + '_MODEL': role})
    root = 'artifacts/host-validation'
    result = subprocess.run(['linuxpilot', 'matrix', 'Verify that the selected host window is visible. Do not modify projects.',
                             '--max-steps', '2', '--planner', '--artifacts', root,
                             '--knowledge', root + '/knowledge'], env=env)
    assert result.returncode == 0, 'Host matrix failed'
    for host in ('carla', 'ardour', 'reaper'):
        result = subprocess.run(['linuxpilot', 'knowledge', 'update', '--host', host,
                                 '--artifacts', root, '--knowledge', root + '/knowledge'], env=env)
        assert result.returncode == 0, f'{host} review failed'
        store = json.loads(Path(root, 'knowledge', host + '.json').read_text())
        assert store['lessons'] and store['lessons'][-1]['source']['screenshot_sha256']
    assert counts['actor'] == 6 and counts['planner'] == 6 and counts['reviewer'] >= 3, counts
    print('Host matrix + planner + evidence-linked knowledge HTTP checks passed:', counts)
finally:
    server.shutdown()
    thread.join()
    server.server_close()
