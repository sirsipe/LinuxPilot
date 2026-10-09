# REAPER

Environment: official Linux x86_64 archive extracted under /opt/reaper, executable
/opt/reaper/REAPER/reaper; no installer. Settings normally live in ~/.config/REAPER.
The evaluation/license dialog may appear on startup. Wait for the legitimate
evaluation continuation control to enable and then dismiss it. Never alter license
files or bypass the delay. First launch may need audio configuration: choose JACK
for the running dummy engine (Options -> Preferences -> Audio -> Device).

Plugin discovery: Options -> Preferences -> Plug-ins -> VST, ensure ~/.vst3 is in
the scan paths and rescan if necessary. REAPER may scan automatically at startup.
Create a track, open its FX button/browser, search for the plugin, and add once.
The FX chain can embed the editor or float it. Distinguish the plugin's custom UI
from generic parameter controls. Host/editor widgets may have no AT-SPI tree;
use screenshot, X11 window titles/classes, and keyboard input. Do not invent selectors.
Use saved .rpp baselines for repeatability. Shortcuts depend on focus and keymap.

ReaScript Lua is embedded. Actions -> Show action list -> ReaScript Load adds a
trusted .lua script; select it and Run. ReaScript: run... can run a script directly.
The prepared LinuxPilot snapshot script is read-only and writes track plugin
names, parameter names and normalized values to a run-specific JSON file. The
harness can run it automatically in the existing REAPER instance. It does not prove
audible behavior. Scripts must be explicitly provided by the task; do not generate
arbitrary code while running a screenshot task.

Sources: https://www.reaper.fm/sdk/reascript/reascript.php
https://www.reaper.fm/sdk/reascript/reascripthelp.html
