"""Start an isolated desktop; every exec/VS Code terminal shares the fixed D-Bus address."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from uiautomation.hosts import HOSTS, HostSession

children = []
logs = []
stopping = False
logdir = Path('/tmp/uiauto-logs')
logdir.mkdir(exist_ok=True)


def start(name, command, env=None, log_output=True):
    log = (logdir / f'{name}.log').open('a') if log_output else None
    if log:
        logs.append(log)
    child = subprocess.Popen(command, stdout=log,
                             stderr=subprocess.STDOUT if log_output else None, env=env)
    children.append((name, child))
    return child


def wait_for(command, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if any(p.poll() is not None for _, p in children):
            raise RuntimeError('Desktop service exited during startup; inspect /tmp/uiauto-logs')
        try:
            if subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=2).returncode == 0:
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.2)
    raise RuntimeError(f'Desktop readiness timed out: {command[0]}')


def stop(*_):
    global stopping
    stopping = True


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    runtime.mkdir(exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    Path('/tmp/uiauto-session-bus').unlink(missing_ok=True)
    start('dbus', ['dbus-daemon', '--session', '--nofork',
                   '--address=' + os.environ['DBUS_SESSION_BUS_ADDRESS']])
    wait_for(['dbus-send', '--session', '--print-reply', '--dest=org.freedesktop.DBus',
              '/org/freedesktop/DBus', 'org.freedesktop.DBus.ListNames'])
    start('xvfb', ['Xvfb', os.environ['DISPLAY'], '-screen', '0',
                   os.getenv('DESKTOP_SIZE', '1920x1080') + 'x24', '-dpi', '96', '-nolisten', 'tcp'])
    wait_for(['xdpyinfo'])
    start('openbox', ['openbox'])
    # D-Bus activates the distribution's AT-SPI service and registry on demand.
    subprocess.run(['dbus-send', '--session', '--print-reply', '--dest=org.a11y.Bus',
                    '/org/a11y/bus', 'org.freedesktop.DBus.Properties.Set',
                    'string:org.a11y.Status', 'string:IsEnabled', 'variant:boolean:true'], check=True)
    subprocess.run(['dbus-send', '--session', '--print-reply', '--dest=org.a11y.Bus',
                    '/org/a11y/bus', 'org.freedesktop.DBus.Properties.Set',
                    'string:org.a11y.Status', 'string:ScreenReaderEnabled',
                    'variant:boolean:true'], check=True)
    # Initialize the registry before Qt starts, rather than on the first agent query.
    subprocess.run(['/usr/bin/python3', '-c',
        'import dbus; s=dbus.SessionBus(); '
        'a=s.get_object("org.a11y.Bus", "/org/a11y/bus").GetAddress(dbus_interface="org.a11y.Bus"); '
        'b=dbus.bus.BusConnection(a); '
        'r=b.get_object("org.a11y.atspi.Registry", "/org/a11y/atspi/accessible/root"); '
        'r.GetChildren(dbus_interface="org.a11y.atspi.Accessible")'], check=True)
    start('jack', ['jackd', '--no-realtime', '-d', 'dummy', '-r', '48000', '-p', '1024'])
    wait_for(['jack_lsp'])
    # Only initialize new profiles: preserve settings and plugin database between sessions.
    settings = Path.home() / '.config/falkTX/Carla2.conf'
    if not settings.exists():
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text('[Engine]\nAudioDriver=JACK\nProcessMode=3\n\n'
                            '[Main]\nShowLogs=false\n')
    host = os.getenv('UIAUTO_HOST', 'carla')
    if host not in HOSTS:
        raise ValueError('UIAUTO_HOST must be carla, ardour, or reaper')
    HostSession().start(host)
    start('vnc', ['x11vnc', '-display', os.environ['DISPLAY'], '-localhost',
                  '-rfbport', '5900', '-forever', '-shared', '-nopw', '-noxdamage'])
    start('novnc', ['websockify', '--web=/usr/share/novnc', '6080', '127.0.0.1:5900'])
    wait_for(['linuxpilot', 'doctor', '--desktop-only'], seconds=30)
    start('command', sys.argv[1:] or ['sleep', 'infinity'], log_output=False)
    print(f'{host} desktop: http://localhost:6080/vnc.html?autoconnect=1&resize=scale', flush=True)
    print('Service logs: /tmp/uiauto-logs', flush=True)
    while not stopping:
        for name, proc in children:
            if proc.poll() is not None:
                if name == 'command':
                    return proc.returncode
                print(f'{name} exited ({proc.returncode}); see {logdir / (name + ".log")}',
                      file=sys.stderr, flush=True)
                return 1
        time.sleep(0.5)
    return 0


if __name__ == '__main__':
    result = 1
    try:
        result = main()
    finally:
        try:
            HostSession().stop()
        except Exception as exc:
            print(f'Host shutdown: {exc}', file=sys.stderr)
        for _, child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for _, child in reversed(children):
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
        for log in logs:
            log.close()
    sys.exit(result)
