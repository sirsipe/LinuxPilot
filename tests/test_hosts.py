import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from uiautomation.hosts import HOSTS, HostSession, host_visible, x11_windows


class HostTests(unittest.TestCase):
    def test_reaper_without_accessibility_is_visible(self):
        observation = {'apps': [], 'x11_windows': [
            {'class': 'REAPER.REAPER', 'name': 'Unsaved - REAPER'}]}
        self.assertTrue(host_visible('reaper', observation))
        self.assertFalse(host_visible('ardour', observation))

    def test_real_wmctrl_layout_preserves_title_and_bounds(self):
        result = Mock(stdout='0x01000026 0 757 82 120 1024 768 REAPER.REAPER desktop REAPER v7.82 - EVALUATION LICENSE\n')
        with patch('uiautomation.hosts.subprocess.run', return_value=result):
            windows = x11_windows()
        self.assertEqual(windows[0]['pid'], 757)
        self.assertEqual(windows[0]['bounds'], [82, 120, 1024, 768])
        self.assertEqual(windows[0]['name'], 'REAPER v7.82 - EVALUATION LICENSE')

    def test_missing_wmctrl_does_not_break_observation(self):
        with patch('uiautomation.hosts.subprocess.run', side_effect=FileNotFoundError):
            self.assertEqual(x11_windows(), [])

    def test_stale_pid_is_never_terminated(self):
        with tempfile.TemporaryDirectory() as root:
            session = HostSession(root)
            session.state_path.write_text(json.dumps({'pid': 123, 'identity': 'old', 'host': 'reaper'}))
            with patch('uiautomation.hosts.process_identity', return_value='reused'), \
                 patch('uiautomation.hosts.os.killpg') as kill:
                self.assertIsNone(session.current())
                session.stop()
                kill.assert_not_called()

    def test_unmanaged_daw_is_not_closed_or_competed_with(self):
        with tempfile.TemporaryDirectory() as root:
            session = HostSession(root)
            with patch('uiautomation.hosts.shutil.which', return_value='/usr/bin/ardour'), \
                 patch('uiautomation.hosts.x11_windows', return_value=[
                     {'class': 'REAPER.REAPER', 'name': 'Unsaved', 'pid': 999}]), \
                 patch('uiautomation.hosts.subprocess.Popen') as launch, \
                 patch('uiautomation.hosts.os.killpg') as kill:
                with self.assertRaisesRegex(RuntimeError, 'Unmanaged reaper'):
                    session.start('ardour')
                launch.assert_not_called()
                kill.assert_not_called()

    def test_project_must_exist_and_remains_one_argument(self):
        with tempfile.TemporaryDirectory() as root, patch('uiautomation.hosts.shutil.which', return_value='/bin/reaper'):
            project = Path(root) / 'a project.rpp'
            with self.assertRaises(ValueError):
                HOSTS['reaper'].command(project)
            project.touch()
            self.assertEqual(HOSTS['reaper'].command(project), ['/bin/reaper', str(project)])

    def test_owned_plugin_bridge_does_not_block_switching_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            session = HostSession(root)
            current = {'host': 'carla', 'pid': 100, 'identity': 'start'}
            with patch.object(session, 'current', return_value=current), \
                 patch.object(session, 'stop') as stop, \
                 patch('uiautomation.hosts.shutil.which', return_value='/usr/bin/ardour'), \
                 patch('uiautomation.hosts.x11_windows', return_value=[
                     {'class': 'carla-bridge.Carla', 'name': 'Plugin editor', 'pid': 200}]), \
                 patch('uiautomation.hosts.os.getpgid', return_value=100), \
                 patch('uiautomation.hosts.subprocess.Popen', return_value=Mock(pid=300)), \
                 patch('uiautomation.hosts.process_identity', return_value='new'):
                state = session.start('ardour')
                self.assertEqual(state['host'], 'ardour')
                stop.assert_called_once()
