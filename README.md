# LinuxPilot

AI-driven Linux desktop automation, starting with VST3 plugin UI testing in
**Carla, Ardour, and REAPER**. Give it a task; it uses screenshots, accessibility
information, and host knowledge to operate the desktop and save test evidence.

## Quick start with VS Code

You need Docker, VS Code with the **Dev Containers** extension, and an
OpenAI-compatible vision model endpoint. Inference runs at your endpoint; no local
GPU is required.

1. Clone the repository and create your local configuration:

   ```bash
   git clone https://github.com/sirsipe/LinuxPilot.git
   cd LinuxPilot
   cp .env.example .env
   ```

2. Edit `.env` with your endpoint, model name, and API key:

   ```dotenv
   UIAUTO_MODEL_BASE_URL=https://your-endpoint/v1
   UIAUTO_MODEL_MODEL=your-vision-model
   UIAUTO_MODEL_API_KEY=your-api-key
   UIAUTO_MODEL_COORDINATE_SPACE=normalized
   ```

   Use `pixels` for models that return screenshot pixel coordinates instead of
   normalized 0–1000 coordinates. See [.env.example](.env.example) for all options.

3. Put your native Linux VST3 bundles in `plugins/`, for example
   `plugins/MyPlugin.vst3/Contents/x86_64-linux/MyPlugin.so`.

4. Open the folder in VS Code and run **Dev Containers: Reopen in Container**.
   The image includes all three hosts and starts Carla by default.

5. In VS Code's **Ports** panel, open port **6080** and visit
   `/vnc.html?autoconnect=1&resize=scale` to see the desktop. In the container
   terminal, check the setup and try a task:

   ```bash
   linuxpilot doctor --desktop-only
   linuxpilot smoke
   linuxpilot doctor
   linuxpilot run "Open Carla's Add Plugin dialog and verify it is visible." --dry-run
   linuxpilot run "Open Carla's Add Plugin dialog and verify it is visible."
   ```

`smoke` checks Carla without a model. `doctor` also checks your vision endpoint.
`--dry-run` proposes one action without clicking or typing.

## Test your plugin

Scan and load your plugin in the selected host first. For Carla, use
**Add Plugin → Refresh**, enable **VST3**, scan, then add the plugin.

```bash
linuxpilot run "Open the editor of MyPlugin in Carla, select the Init preset, and verify its name. Do not save any files."
```

Switch hosts and run a task:

```bash
linuxpilot run --host ardour --launch-host "Create one empty audio track and verify it is visible."
linuxpilot run --host reaper --launch-host "Create one empty track and verify it is visible."
```

Switching hosts closes the previous test session. Run one test at a time.
Screenshots and reports are saved under `artifacts/`; review them to confirm the
result. These are UI tests; screenshots do not verify audio or DSP correctness.

For longer prompts, create your own local file under `tasks/`:

```bash
linuxpilot run --task-file tasks/my-test.txt --max-steps 60
linuxpilot matrix --task-file tasks/my-test.txt --max-steps 60
```

`matrix` runs the task sequentially in Carla, Ardour, and REAPER, restarting each
host. Tasks, credentials, plugin bundles, saved projects, and generated evidence
stay local and are excluded from Git.

## Improve future runs

Host guides are included automatically. Review past runs to add tentative lessons:

```bash
linuxpilot knowledge update --host reaper --artifacts artifacts
linuxpilot knowledge show --host reaper
```

For a separate reasoning model, configure `UIAUTO_PLANNER_*` in `.env` and add
`--planner` to your run. Use `linuxpilot run --help` for additional checks and options.

## Docker without VS Code

After cloning, configuring `.env`, and adding plugins:

```bash
scripts/desktop.sh build
scripts/desktop.sh up                 # or: up ardour / up reaper
scripts/desktop.sh shell
```

Open [the desktop](http://localhost:6080/vnc.html?autoconnect=1&resize=scale), then
run the same `linuxpilot` commands in the container shell. Stop it from your host:

```bash
scripts/desktop.sh down
```

Ardour comes from Ubuntu repositories. REAPER runs from its downloaded archive;
update the `REAPER_URL` build argument in [Dockerfile](Dockerfile), or export it
when running `scripts/desktop.sh build`.
