#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=linuxpilot:local
container=linuxpilot-desktop
viewer_port=${DESKTOP_PORT:-6080}
case "${1:-}" in
  build)
    build_args=()
    if [[ -n ${REAPER_URL:-} ]]; then build_args+=(--build-arg "REAPER_URL=$REAPER_URL"); fi
    if [[ -n ${REAPER_SHA256:-} ]]; then build_args+=(--build-arg "REAPER_SHA256=$REAPER_SHA256"); fi
    docker build "${build_args[@]}" -t "$image" .
    ;;
  up)
    mkdir -p artifacts plugins projects
    env_args=()
    if [[ -f .env ]]; then env_args=(--env-file .env); fi
    host_args=()
    if [[ -n ${2:-} ]]; then host_args=(-e "UIAUTO_HOST=$2"); fi
    docker run -d --name "$container" --shm-size=1g "${host_args[@]}" \
      -p "127.0.0.1:$viewer_port:6080" "${env_args[@]}" \
      --mount "type=bind,src=$PWD,dst=/workspaces/LinuxPilot" \
      --mount "type=bind,src=$PWD/plugins,dst=/home/tester/.vst3,readonly" \
      --mount "type=volume,src=carla-uiauto-config,dst=/home/tester/.config" \
      "$image"
    for attempt in {1..60}; do
      state=$(docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' "$container")
      if [[ "$state" == 'running healthy' ]]; then
        echo "Desktop ready: http://localhost:$viewer_port/vnc.html?autoconnect=1&resize=scale"
        exit 0
      fi
      if [[ "$state" != running* ]]; then
        docker logs "$container"
        exit 1
      fi
      sleep 1
    done
    echo 'Desktop did not become healthy within 60 seconds; inspect scripts/desktop.sh logs.' >&2
    exit 1
    ;;
  down) docker stop "$container"; docker rm "$container" ;;
  shell) docker exec -it "$container" bash ;;
  exec) shift; docker exec -i "$container" "$@" ;;
  logs) docker logs "$container" ;;
  *) echo 'Usage: scripts/desktop.sh {build|up [carla|ardour|reaper]|down|shell|exec COMMAND...|logs}'; exit 2 ;;
esac
