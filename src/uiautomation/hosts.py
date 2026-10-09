"""Host launch and X11 discovery, including applications without AT-SPI trees."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time


@dataclass(frozen=True)
class Host:
    name: str
    executable: str
    project_env: str
    window_token: str

    def command(self, project=None):
        executable = shutil.which(self.executable)
        if not executable:
            raise ValueError(f'{self.executable} is unavailable; rebuild the desktop image')
        project = project or os.getenv(self.project_env)
        if project and not Path(project).exists():
            raise ValueError(f'Host project does not exist: {project}')
        return [executable] + ([str(Path(project).resolve())] if project else [])


HOSTS = {h.name: h for h in (
    Host('carla', 'carla', 'CARLA_PROJECT', 'carla'),
    Host('ardour', 'ardour', 'ARDOUR_PROJECT', 'ardour'),
    Host('reaper', 'reaper', 'REAPER_PROJECT', 'reaper'),
)}


def x11_windows():
    """wmctrl exposes titles/classes/PIDs even when custom UIs have no AT-SPI."""
    try:
        result = subprocess.run(['wmctrl', '-lpGx'], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return []
    windows = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 9)
        if len(fields) != 10:
            continue
        try:
            windows.append({'id': fields[0], 'pid': int(fields[2]),
                            'bounds': [int(v) for v in fields[3:7]],
                            'class': fields[7], 'name': fields[9]})
        except ValueError:
            continue
    return windows


def host_visible(name, observation):
    token = HOSTS[name].window_token
    return (any(token in a['name'].lower() for a in observation['apps']) or
            any(token in w['class'].lower()
                for w in observation.get('x11_windows', [])))


def process_identity(pid):
    try:
        # The command name can contain spaces/parentheses. Field 22 is starttime.
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, IndexError):
        return None


class HostSession:
    """Only terminate processes launched by this harness, never arbitrary DAWs."""
    def __init__(self, root=None):
        self.root = Path(root or os.getenv('UIAUTO_RUNTIME', '/tmp/uiauto-hosts'))
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / 'host.json'

    def current(self):
        if not self.state_path.exists():
            return None
        state = json.loads(self.state_path.read_text())
        if process_identity(state['pid']) != state['identity']:
            return None
        return state

    def stop(self):
        state = self.current()
        if state:
            try:
                os.killpg(state['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 10
            while process_identity(state['pid']) == state['identity']:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Host did not exit; close its save dialog before switching')
                time.sleep(0.1)
        self.state_path.unlink(missing_ok=True)

    def start(self, name, project=None, restart=False):
        host = HOSTS[name]
        command = host.command(project)
        current = self.current()
        if current and current['host'] == name and not restart:
            if project:
                raise ValueError('Use --restart to open a project in an already running host')
            return current
        owned_pid = current['pid'] if current else None
        def belongs_to_session(window):
            if owned_pid is None or window['pid'] <= 0:
                return False
            try:
                return os.getpgid(window['pid']) == owned_pid
            except ProcessLookupError:
                return False
        for candidate in HOSTS:
            windows = [w for w in x11_windows()
                       if HOSTS[candidate].window_token in w['class'].lower()
                       and not belongs_to_session(w)]
            if windows:
                raise RuntimeError(f'Unmanaged {candidate} window is open; close it before launching a host')
        self.stop()
        env = dict(os.environ)
        # Carla/Ardour distribution launchers need distro Python and libraries.
        env['PATH'] = '/usr/bin:/bin:' + env['PATH']
        logdir = Path('/tmp/uiauto-logs')
        logdir.mkdir(exist_ok=True)
        with (logdir / f'{name}.log').open('a') as log:
            child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                     env=env, start_new_session=True)
        identity = process_identity(child.pid)
        if identity is None:
            raise RuntimeError(f'{name} exited at launch; inspect {logdir / (name + ".log")}')
        state = {'host': name, 'pid': child.pid, 'identity': identity,
                 'command': command, 'project': project or os.getenv(host.project_env)}
        self.state_path.write_text(json.dumps(state, indent=2))
        return state

    def wait_ready(self, name, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.current()
            if not state or state['host'] != name:
                raise RuntimeError(f'{name} exited; inspect /tmp/uiauto-logs/{name}.log')
            windows = [w for w in x11_windows() if 'initializing' not in w['name'].lower()]
            if host_visible(name, {'apps': [], 'x11_windows': windows}):
                return state
            time.sleep(0.2)
        raise RuntimeError(f'{name} did not show a window within {timeout}s')
