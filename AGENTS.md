# LinuxPilot

LinuxPilot provides AI-driven Linux desktop automation. Its current use case is
native Linux VST3 plugin UI testing in Carla, Ardour, and REAPER.

## Project layout

- Python implementation: `src/uiautomation/` (the internal module name remains).
- Primary CLI: `linuxpilot`; `uiauto` remains a compatibility alias.
- Desktop: Docker/Dev Container with Xvfb, Openbox, xa11y, JACK dummy and noVNC.
- Container workspace: `/workspaces/LinuxPilot`; host folder naming is independent.
- Host guides: `src/uiautomation/guides/`; learned knowledge: `knowledge/`.
- Prompted tasks: `tasks/` (local only, never commit); evidence and reports: `artifacts/`.
- The Codex VS Code extension is configured in the Dev Container.

## Configuration and validation

Read `README.md` and `.env.example` for supported commands and model configuration.
Keep API keys out of logs and reports. Existing `HOLO_*` and `UIAUTO_*` environment
variables remain supported. Preserve the historical `carla-uiauto-config` Docker
volume name so existing host settings and scan caches continue to load.

Run `python -m unittest discover -s tests -v` in the container. Local desktop
integration checks are in `scripts/check_loop.py`, `scripts/check_hosts.py`, and
`scripts/check_reaper.py`; these operate on harness-owned test hosts. They use
local stub models or fixed scripts, not remote inference. Model pass assessments
and screenshots alone do not establish DSP correctness. Learned advice is
tentative and must retain its artifact provenance.
