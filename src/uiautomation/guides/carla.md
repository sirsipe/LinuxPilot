# Carla

Environment: Linux/X11, JACK dummy, native VST3 bundles in ~/.vst3.
Use observed names: Carla usually exposes its AT-SPI app as Carla2; plugin
editors can belong to bridge processes. Do not assume editor controls are accessible.

Discovery: Add Plugin -> Refresh -> enable VST3 -> Scan. Wait for completion,
close Refresh, enable the VST3 filter in Add Plugin, search the plugin, add once.
The gear opens the custom editor; the wrench opens generic parameters.
Qt retains hidden dialogs: selectors should include [visible="true"].
An accessibility press can remain pending while a modal dialog is open. Inspect
the new screen and operate that dialog before trying the same press again.
Close a focused editor with Alt+F4 if its close button is outside the screenshot.
Load a saved .carxp baseline for repeatable tasks. Never assume the last run's
instance is fresh. JACK dummy supplies timing, not audible output or DSP evidence.
