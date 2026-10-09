from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from uiautomation.model import Model, load_env, observation_message


class ModelTests(unittest.TestCase):
    def test_compatible_request_contains_one_image_and_auth(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured['path'] = self.path
                captured['auth'] = self.headers['Authorization']
                captured['user_agent'] = self.headers['User-Agent']
                if captured['user_agent'].startswith('Python-urllib/'):
                    self.send_error(403)
                    return
                captured['body'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"ok"}}]}')

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            client = Model(f'http://127.0.0.1:{server.server_port}/v1', 'test-secret', 'holo')
            client.request([observation_message('test', b'png')])
            self.assertEqual(captured['path'], '/v1/chat/completions')
            self.assertEqual(captured['auth'], 'Bearer test-secret')
            self.assertEqual(captured['user_agent'], 'uiautomation/0.1')
            body = captured['body']
            self.assertEqual(body['model'], 'holo')
            self.assertNotIn('tools', body)
            self.assertNotIn('response_format', body)
            content = body['messages'][0]['content']
            self.assertEqual(content[1]['image_url']['url'], 'data:image/png;base64,cG5n')
        finally:
            server.shutdown()
            worker.join()
            server.server_close()

    def test_env_file_is_data_and_exports_win(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'HOLO_MODEL': 'exported'}):
            path = Path(directory) / '.env'
            path.write_text('HOLO_MODEL=file\nTEST_LITERAL=$(touch /tmp/nope)\n')
            load_env(path)
            self.assertEqual(os.environ['HOLO_MODEL'], 'exported')
            self.assertEqual(os.environ['TEST_LITERAL'], '$(touch /tmp/nope)')

    def test_missing_key_fails_without_request(self):
        with patch.dict(os.environ, {'HOLO_BASE_URL': 'https://example.com/v1'}, clear=True):
            with self.assertRaises(ValueError):
                Model.from_env()

    def test_roles_select_separate_models_without_mixing_credentials(self):
        values = {'HOLO_BASE_URL': 'https://legacy/v1', 'HOLO_API_KEY': 'legacy-key',
                  'UIAUTO_MODEL_BASE_URL': 'https://vision/v1', 'UIAUTO_MODEL_API_KEY': 'vision-key',
                  'UIAUTO_MODEL_MODEL': 'vision', 'UIAUTO_PLANNER_BASE_URL': 'https://planner/v1',
                  'UIAUTO_PLANNER_API_KEY': 'planner-key', 'UIAUTO_PLANNER_MODEL': 'reasoner'}
        with patch.dict(os.environ, values, clear=True):
            actor = Model.from_env()
            planner = Model.from_env(role='planner')
            reviewer = Model.from_env(role='knowledge')
            self.assertEqual((actor.name, actor.api_key), ('vision', 'vision-key'))
            self.assertEqual((planner.name, planner.api_key), ('reasoner', 'planner-key'))
            self.assertEqual(reviewer.base_url, planner.base_url)

    def test_missing_planner_configuration_does_not_silently_use_holo(self):
        with patch.dict(os.environ, {'HOLO_BASE_URL': 'https://legacy/v1', 'HOLO_API_KEY': 'key'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'UIAUTO_PLANNER_BASE_URL'):
                Model.from_env(role='planner')
