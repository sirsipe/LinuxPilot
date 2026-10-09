"""Generate fixed, read-only host snapshots. No model-generated code is executed."""
import json
from pathlib import Path
import uuid
import subprocess
import time


# JSON encoder for simple scalar fields; arrays/objects are built explicitly.
COMMON = r'''
local function q(value)
  local text = tostring(value):gsub('[%z\1-\31\\"]', function(c)
    if c == '"' then return '\\"' end
    if c == '\\' then return '\\\\' end
    return string.format('\\u%04x', string.byte(c))
  end)
  return '"' .. text .. '"'
end
local function number(value)
  if value ~= value or value == math.huge or value == -math.huge then return 'null' end
  return string.format('%.17g', value)
end
'''

REAPER = r'''
local tracks = {}
for ti = 0, reaper.CountTracks(0) - 1 do
  local track = reaper.GetTrack(0, ti)
  local _, track_name = reaper.GetTrackName(track)
  local plugins = {}
  for fi = 0, reaper.TrackFX_GetCount(track) - 1 do
    local _, fx_name = reaper.TrackFX_GetFXName(track, fi)
    local parameters = {}
    for pi = 0, reaper.TrackFX_GetNumParams(track, fi) - 1 do
      local _, parameter_name = reaper.TrackFX_GetParamName(track, fi, pi)
      local value = reaper.TrackFX_GetParamNormalized(track, fi, pi)
      parameters[#parameters+1] = '{"index":' .. pi .. ',"name":' .. q(parameter_name)
        .. ',"normalized":' .. number(value) .. '}'
    end
    plugins[#plugins+1] = '{"name":' .. q(fx_name) .. ',"parameters":['
      .. table.concat(parameters, ',') .. ']}'
  end
  tracks[#tracks+1] = '{"name":' .. q(track_name) .. ',"plugins":['
    .. table.concat(plugins, ',') .. ']}'
end
local body = '{"host":"reaper","token":' .. q(token) .. ',"tracks":['
  .. table.concat(tracks, ',') .. ']}'
local file = assert(io.open(output_path .. '.tmp', 'w'))
file:write(body)
file:close()
assert(os.rename(output_path .. '.tmp', output_path))
'''

ARDOUR = r'''
if type(ardour) == 'function' then
  ardour { ["type"] = "EditorAction", name = "LinuxPilot snapshot",
    description = "Read-only route and plugin inventory for the UI test harness" }
end
function factory(unused)
  return function()
    assert(Session, 'Open a session before taking a snapshot')
    local tracks = {}
    for route in Session:get_routes():iter() do
      local plugins = {}
      local fi = 0
      while true do
        local processor = route:nth_plugin(fi)
        if processor:isnil() then break end
        plugins[#plugins+1] = '{"name":' .. q(processor:display_name()) .. '}'
        fi = fi + 1
      end
      tracks[#tracks+1] = '{"name":' .. q(route:name()) .. ',"plugins":['
        .. table.concat(plugins, ',') .. ']}'
    end
    local body = '{"host":"ardour","token":' .. q(token) .. ',"tracks":['
      .. table.concat(tracks, ',') .. ']}'
    local file = assert(io.open(output_path .. '.tmp', 'w'))
    file:write(body)
    file:close()
    assert(os.rename(output_path .. '.tmp', output_path))
    print('LinuxPilot snapshot written: ' .. output_path)
  end
end
'''


def lua_string(value):
    # Lua has no JSON \u escape; use three-digit decimal escapes for controls.
    return '"' + ''.join('\\' + c if c in ('"', '\\') else
                         f'\\{ord(c):03d}' if ord(c) < 32 else c for c in str(value)) + '"'


def prepare(host, folder):
    if host not in ('ardour', 'reaper'):
        raise ValueError('Snapshots use Ardour Lua or REAPER ReaScript; Carla has no snapshot adapter')
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    output = folder / 'host-snapshot.json'
    script = folder / 'host-snapshot.lua'
    source = 'local output_path = ' + lua_string(output) + '\nlocal token = ' + lua_string(token) + '\n'
    source += COMMON + (REAPER if host == 'reaper' else ARDOUR)
    script.write_text(source)
    manifest = {'host': host, 'token': token, 'script': str(script), 'output': str(output)}
    (folder / 'script-manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def instructions(manifest):
    path = manifest['script']
    if manifest['host'] == 'reaper':
        return ('\nThe harness will capture a read-only ReaScript state snapshot when you finish. '
                'Complete the UI task normally; leave the tested plugin loaded for that check.')
    else:
        # Console execution of a trusted file avoids version-specific installation paths.
        entry = ('Open Window -> Scripting. In its Lua console execute this exact prepared command: '
                 + 'dofile(' + lua_string(path) + '); factory({})()' + '. This trusted command only '
                 'loads our read-only EditorAction and invokes it; do not change its source.')
    return ('\nAlso capture the required host state by running the prepared read-only script at '
            + path + '. ' + entry + ' It must write ' + manifest['output'] +
            '. Do not claim completion before the script has run successfully.')


def capture_reaper(manifest, timeout=15):
    if manifest['host'] != 'reaper':
        raise ValueError('Only REAPER supports this command-line capture adapter')
    from .hosts import HostSession
    current = HostSession().current()
    if not current or current['host'] != 'reaper':
        raise ValueError('REAPER snapshot requires a running harness-owned REAPER instance')
    Path(manifest['output']).unlink(missing_ok=True)
    subprocess.run(['reaper', '-nonewinst', manifest['script']], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    deadline = time.monotonic() + timeout
    while not Path(manifest['output']).is_file():
        if time.monotonic() >= deadline:
            raise RuntimeError('REAPER snapshot timed out; check startup/modal dialogs and script errors')
        time.sleep(0.1)


def verify(manifest, plugin=None):
    snapshot = json.loads(Path(manifest['output']).read_text())
    if snapshot.get('host') != manifest['host'] or snapshot.get('token') != manifest['token']:
        raise ValueError('Host snapshot is stale or belongs to another run')
    if not isinstance(snapshot.get('tracks'), list):
        raise ValueError('Host snapshot has no track inventory')
    if plugin and not any(plugin.lower() in fx['name'].lower()
                          for track in snapshot['tracks'] for fx in track['plugins']):
        raise ValueError(f'Plugin absent from host snapshot: {plugin}')
    return snapshot
