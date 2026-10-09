# Ardour

Environment: Ubuntu repository build (version depends on base image), X11,
JACK dummy at 48 kHz, native Linux VST3 bundles in ~/.vst3.
First launch can show welcome/configuration dialogs, session creation, and
Audio/MIDI Setup. Choose JACK for this environment. A visible setup dialog is
not a ready session. Create test sessions only under projects/ when task permits.

Ardour loads plugins on a track/bus processor list. Create the appropriate audio
or MIDI track for the plugin, open its processor/plugin chooser, search for the
plugin and insert it once. An instrument generally needs a MIDI track. Double
click the inserted processor to open its editor. Distinguish generic controls
from a plugin's own custom editor. Use actual observed menu/control labels;
versions and keyboard maps vary. Plugin Manager supports discovery/scan inspection.
GTK may expose host controls through AT-SPI; canvas/plugin controls may require pixels.

Lua: EditorAction scripts run in the GUI thread; real-time Session/DSP scripts
are unsuitable for file I/O or setup. Window -> Scripting opens the script console.
Edit -> Scripted Actions -> Manage assigns scripts to action slots. User scripts
live in ~/.config/ardour<major>/scripts. Use only trusted prepared scripts specified
by the task; never write arbitrary model-generated Lua through the console.
The prepared read-only LinuxPilot snapshot script writes route and plugin names
to a run-specific JSON file and prints its path in the console. It does not
validate audio or modify the session. Use the exact prepared command in the task.

Sources: https://manual.ardour.org/lua-scripting/
https://manual.ardour.org/working-with-plugins/plugin-manager/
