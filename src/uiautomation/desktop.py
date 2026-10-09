import json
import time
from collections import deque
import subprocess
import sys

import xa11y

from .hosts import x11_windows


class Desktop:
    def __init__(self):
        xa11y.set_default_timeout(3)
        self.input = xa11y.input_sim()
        self.shot = None
        self.pending = []
        self.worker_outcomes = deque(maxlen=12)

    def observe(self):
        self.reap()
        self.shot = xa11y.screenshot()
        apps = []
        for app in xa11y.App.list():
            entry = {'name': app.name, 'pid': app.pid}
            try:
                # Limit traversal itself, not just the rendered string. Plugin tables
                # can expose thousands of rows and make a full dump very expensive.
                queue = deque([(app.as_element(), 0)])
                nodes = []
                while queue and len(nodes) < 120:
                    element, depth = queue.popleft()
                    node = {'depth': depth, 'role': element.role,
                            'name': (element.name or '')[:200],
                            'visible': element.visible, 'enabled': element.enabled}
                    if node['role'] in ('window', 'dialog') and not node['visible']:
                        continue
                    bounds = element.bounds
                    if bounds:
                        node['bounds'] = [bounds.x, bounds.y, bounds.width, bounds.height]
                    if node['role'] in ('text_field', 'text_area', 'slider', 'spin_button', 'combo_box'):
                        node['value'] = (element.value or '')[:200]
                    nodes.append(node)
                    if depth < 5:
                        children = element.children()
                        remaining = max(0, 120 - len(nodes) - len(queue))
                        queue.extend((child, depth + 1) for child in children[:remaining])
                        if len(children) > remaining:
                            entry['truncated'] = True
                entry['tree'] = nodes
                if queue:
                    entry['truncated'] = True
            except xa11y.XA11yError as exc:
                entry['error'] = str(exc)
            apps.append(entry)
        observation = {'image_width': self.shot.width, 'image_height': self.shot.height,
                       'apps': apps, 'x11_windows': x11_windows(),
                       'semantic_outcomes': list(self.worker_outcomes)}
        return observation, self.shot.to_png()

    def point(self, x, y):
        if self.shot is None:
            raise ValueError('Capture a screenshot before coordinate actions')
        if not (0 <= x < self.shot.width and 0 <= y < self.shot.height):
            raise ValueError('Coordinates are outside the current screenshot')
        return self.shot.image_to_desktop(x, y)

    def perform(self, a):
        action = a['action']
        if action in ('press', 'focus', 'set_value', 'set_numeric_value'):
            # Qt can keep a synchronous AT-SPI action call open throughout a modal
            # dialog. Let the agent observe and close it while that call is pending.
            self.reap()
            if len(self.pending) >= 3:
                raise ValueError('Three semantic actions are pending; close the dialog with pixel/key input')
            worker = subprocess.Popen([sys.executable, '-m', 'uiautomation.action_worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            worker.requested_action = a
            try:
                stdout, stderr = worker.communicate(json.dumps(a), timeout=1)
            except subprocess.TimeoutExpired:
                self.pending.append(worker)
                return 'Accessibility call pending; inspect next screenshot before acting again'
            if worker.returncode:
                raise RuntimeError(stderr.strip() or stdout.strip())
        elif action == 'click':
            self.input.click(self.point(a['x'], a['y']), button=a['button'], count=a['count'])
        elif action == 'drag':
            self.input.drag(self.point(a['x'], a['y']), self.point(a['to_x'], a['to_y']),
                            duration=0.3)
        elif action == 'scroll':
            self.input.scroll(self.point(a['x'], a['y']), dx=a['dx'], dy=a['dy'])
        elif action == 'type_text':
            self.input.type_text(a['text'])
        elif action == 'key':
            self.input.chord(a['key'], held=a['held']) if a['held'] else self.input.press(a['key'])
        elif action == 'wait':
            time.sleep(a['seconds'])
        elif action != 'finish':
            raise ValueError('Unsupported desktop action')

    def reap(self):
        for worker in self.pending[:]:
            if worker.poll() is not None:
                stdout, stderr = worker.communicate()
                self.worker_outcomes.append({'action': worker.requested_action,
                    'result': 'Accessibility call completed; verify UI effect' if worker.returncode == 0
                    else 'Accessibility call failed: ' + (stderr.strip() or stdout.strip())})
                self.pending.remove(worker)

    def close(self):
        for worker in self.pending:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.communicate()
        self.pending.clear()


def save_observation(folder, name, observation, png):
    (folder / f'{name}.png').write_bytes(png)
    (folder / f'{name}.json').write_text(json.dumps(observation, indent=2))
