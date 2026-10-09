"""Load a plugin into a disposable REAPER project and verify the Lua snapshot.

Run inside the desktop container: python scripts/check_reaper.py "VST3 plugin name"
This restarts the harness-owned host and adds a test track/plugin without saving.
No model endpoint is used. Close existing test projects before running it.
"""
import math
from pathlib import Path
import subprocess
import sys
import time

from uiautomation.cli import artifact_dir
from uiautomation.desktop import Desktop, save_observation
from uiautomation.hosts import HostSession
from uiautomation.host_scripts import capture_reaper, lua_string, prepare, verify

if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/check_reaper.py "VST3 plugin name"')
plugin = sys.argv[1]
session = HostSession()
session.start('reaper', restart=True)
session.wait_ready('reaper')
folder = artifact_dir('artifacts', 'reaper-script-check')
manifest = prepare('reaper', folder)
fixture = Path(folder).resolve() / 'fixture.lua'
fixture.write_text('''
reaper.InsertTrackAtIndex(0, true)
local track = reaper.GetTrack(0, 0)
reaper.GetSetMediaTrackInfo_String(track, "P_NAME", "UI \\"test\\" \\nline", true)
local fx = reaper.TrackFX_AddByName(track, ''' + lua_string('VST3: ' + plugin) + ''', false, -1)
assert(fx >= 0, 'VST3 plugin not discovered; scan ~/.vst3 in Preferences first')
reaper.TrackFX_Show(track, fx, 3)
dofile(''' + lua_string(manifest['script']) + ')\n')
subprocess.run(['reaper', '-nonewinst', str(fixture)], check=True, timeout=10)
# Capture runs after fixture delivery through the same instance's script queue.
capture_reaper(manifest)
snapshot = verify(manifest, plugin)
assert snapshot['tracks'][0]['name'] == 'UI "test" \nline', 'JSON escaping failed'
parameters = snapshot['tracks'][0]['plugins'][0]['parameters']
assert parameters and all(isinstance(p['normalized'], (int, float)) and
                          math.isfinite(p['normalized']) and 0 <= p['normalized'] <= 1 for p in parameters)
time.sleep(2)  # Allow the custom editor's first asynchronous paint before saving evidence.
desktop = Desktop()
try:
    observation, png = desktop.observe()
    save_observation(folder, 'editor', observation, png)
finally:
    desktop.close()
print(f'REAPER loaded {plugin}; snapshot verified {len(parameters)} normalized parameters. Evidence: {folder}')
