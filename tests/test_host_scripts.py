import json
from pathlib import Path
import tempfile
import unittest

from uiautomation.host_scripts import lua_string, prepare, verify


class HostScriptTests(unittest.TestCase):
    def test_stale_and_other_host_snapshots_cannot_pass(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = prepare('reaper', root)
            output = Path(manifest['output'])
            for values in ({'token': 'old'}, {'host': 'ardour'}):
                output.write_text(json.dumps({'host': 'reaper', 'token': manifest['token'],
                                             'tracks': [], **values}))
                with self.assertRaisesRegex(ValueError, 'stale'):
                    verify(manifest)

    def test_plugin_presence_is_checked_in_host_inventory(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = prepare('reaper', root)
            Path(manifest['output']).write_text(json.dumps({'host': 'reaper', 'token': manifest['token'],
                'tracks': [{'name': 'Test', 'plugins': [{'name': 'VST3: Example Plugin'}]}]}))
            self.assertEqual(len(verify(manifest, 'example')['tracks']), 1)
            with self.assertRaisesRegex(ValueError, 'absent'):
                verify(manifest, 'Missing')

    def test_lua_string_handles_paths_without_code_interpolation(self):
        self.assertEqual(lua_string('a"b\\c\n'), '"a\\"b\\\\c\\010"')
        self.assertEqual(lua_string('ä'), '"ä"')
