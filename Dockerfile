ARG UBUNTU_VERSION=24.04
FROM python:3.12-slim-bookworm AS certificates
FROM ubuntu:${UBUNTU_VERSION}
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/ubuntu.sources
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git sudo tini python3 python3-venv python3-pip \
    xvfb xauth x11-utils x11vnc novnc websockify openbox fonts-dejavu-core \
    dbus dbus-x11 at-spi2-core libatk-bridge2.0-0 libxtst6 libx11-6 \
    carla carla-bridge-linux64 ardour jackd2 jack-tools libgl1-mesa-dri libegl1 \
    wmctrl libasound2t64 libfreetype6 libfontconfig1 libgtk-3-0 xz-utils \
    build-essential cmake ninja-build pkg-config gdb \
    && rm -rf /var/lib/apt/lists/*
# REAPER runs directly from the extracted archive; no install script is needed.
ARG REAPER_URL=https://www.reaper.fm/files/7.x/reaper782_linux_x86_64.tar.xz
ARG REAPER_SHA256=
RUN curl --fail --location --retry 3 "$REAPER_URL" -o /tmp/reaper.tar.xz \
    && if [ -n "$REAPER_SHA256" ]; then echo "$REAPER_SHA256  /tmp/reaper.tar.xz" | sha256sum -c -; fi \
    && mkdir -p /opt/reaper \
    && tar -xJf /tmp/reaper.tar.xz --strip-components=1 -C /opt/reaper \
    && test -x /opt/reaper/REAPER/reaper \
    && ln -s /opt/reaper/REAPER/reaper /usr/local/bin/reaper \
    && rm /tmp/reaper.tar.xz
# Ubuntu 24.04 ships an unused uid-1000 account. Give bind mounts a stable uid.
RUN if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
    && groupadd --gid 1000 tester && useradd --uid 1000 --gid tester --create-home --shell /bin/bash tester \
    && printf 'tester ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/tester \
    && chmod 0440 /etc/sudoers.d/tester
ENV DISPLAY=:99 DESKTOP_SIZE=1920x1080 \
    XDG_SESSION_TYPE=x11 \
    DBUS_SESSION_BUS_ADDRESS=unix:path=/tmp/uiauto-session-bus \
    XDG_RUNTIME_DIR=/tmp/runtime-tester \
    QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 QT_SCALE_FACTOR=1 \
    QT_AUTO_SCREEN_SCALE_FACTOR=0 LIBGL_ALWAYS_SOFTWARE=1 \
    VST3_PATH=/home/tester/.vst3:/usr/lib/vst3:/usr/local/lib/vst3 \
    XA11Y_LINUX_INPUT_BACKEND=x11 XA11Y_LINUX_SCREENSHOT_BACKEND=x11 \
    XA11Y_LINUX_WINDOW_BACKEND=x11 \
    PATH=/opt/venv/bin:$PATH \
    HOLO_MODEL=holo \
    UIAUTO_HOST=carla
WORKDIR /workspaces/LinuxPilot
COPY pyproject.toml ./
COPY src ./src
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -e . \
    && chown -R tester:tester /opt/venv /workspaces/LinuxPilot
COPY docker/desktop.py /opt/uiauto/desktop.py
USER tester
RUN mkdir -p /home/tester/.vst3 /home/tester/.config /tmp/runtime-tester \
    && chmod 700 /tmp/runtime-tester
EXPOSE 6080
HEALTHCHECK --interval=10s --timeout=15s --start-period=45s --retries=3 \
    CMD linuxpilot doctor --desktop-only >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "/opt/venv/bin/python", "/opt/uiauto/desktop.py"]
CMD ["sleep", "infinity"]
