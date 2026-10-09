"""OpenAI-compatible HTTP client, using the same wire format as the verified curl."""
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from .protocol import action_schema


def load_env(path=Path('.env')):
    """Load simple KEY=value entries without shell evaluation or overwriting exports."""
    if path.is_file():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or not key.strip().replace('_', '').isalnum():
                raise ValueError(f'Invalid environment entry in {path}')
            os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


@dataclass
class Model:
    base_url: str
    api_key: str
    name: str
    max_tokens: int = 2048
    timeout: float = 120
    structured: bool = False

    @classmethod
    def from_env(cls, structured=False, role='actor'):
        prefixes = {'actor': ('UIAUTO_MODEL', 'HOLO'),
                    'planner': ('UIAUTO_PLANNER',),
                    'knowledge': ('UIAUTO_KNOWLEDGE', 'UIAUTO_PLANNER', 'UIAUTO_MODEL', 'HOLO')}
        if role not in prefixes:
            raise ValueError('Unknown model role')
        prefix = next((p for p in prefixes[role] if os.getenv(p + '_BASE_URL')), prefixes[role][0])
        base = os.getenv(prefix + '_BASE_URL', '').rstrip('/')
        if urllib.parse.urlparse(base).scheme not in ('http', 'https'):
            raise ValueError(f'Set {prefix}_BASE_URL to your OpenAI-compatible /v1 endpoint')
        key = os.getenv(prefix + '_API_KEY', '') or os.getenv('APIKEY', '')
        if not key:
            raise ValueError(f'Set {prefix}_API_KEY in .env (APIKEY also works)')
        name = os.getenv(prefix + '_MODEL', 'holo' if prefix == 'HOLO' else '')
        if not name:
            raise ValueError(f'Set {prefix}_MODEL to the served model alias')
        return cls(base, key, name,
                   int(os.getenv(prefix + '_MAX_TOKENS', '2048')),
                   float(os.getenv(prefix + '_TIMEOUT', '120')), structured)

    def request(self, messages, actions=True):
        body = {'model': self.name, 'messages': messages, 'max_tokens': self.max_tokens,
                'temperature': 0.1}
        if self.structured and actions:
            body['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'desktop_action', 'strict': True, 'schema': action_schema()}}
        request = urllib.request.Request(self.base_url + '/chat/completions',
            data=json.dumps(body).encode(), headers={
                'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json',
                # Some model proxies reject urllib's default User-Agent with HTTP 403.
                'User-Agent': 'uiautomation/0.1', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Don't echo an upstream body: proxies may echo request headers/secrets.
            if exc.code == 403:
                raise RuntimeError('Model endpoint returned HTTP 403; check HOLO_BASE_URL, '
                                   'credentials, and proxy access rules. A successful GET /models '
                                   'does not verify POST /chat/completions access') from None
            raise RuntimeError(f'Model endpoint returned HTTP {exc.code}; check endpoint, '
                               'credentials, model alias, and structured-output support') from None
        except urllib.error.URLError:
            raise RuntimeError('Cannot reach model endpoint; check networking and HOLO_BASE_URL') from None
        if not result.get('choices'):
            raise ValueError('Model returned no choices')
        return result


def observation_message(text, png):
    return {'role': 'user', 'content': [
        {'type': 'text', 'text': text},
        {'type': 'image_url', 'image_url': {
            'url': 'data:image/png;base64,' + base64.b64encode(png).decode()}}]}
