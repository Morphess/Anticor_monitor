#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export E2E_UID="$(id -u)"
export E2E_GID="$(id -g)"
# Fixed project/file, no production env-file, no inherited Compose selection.
compose=(docker compose --project-name bordergroup-e2e-42 --env-file /dev/null -f "$PWD/compose.e2e.yaml")
exec 9>.e2e.lock
flock -n 9 || { echo 'Another local E2E run is active.' >&2; exit 1; }
mkdir -p e2e-artifacts
cleanup() {
  local status=$?
  if (( status != 0 )); then
    "${compose[@]}" logs --no-color api db > e2e-artifacts/compose.log 2>&1 || true
  fi
  # Removes ONLY this fixed disposable test project's data.
  "${compose[@]}" down --volumes --remove-orphans > /dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT
"${compose[@]}" down --volumes --remove-orphans
"${compose[@]}" build
"${compose[@]}" up -d --wait --wait-timeout 120 api
"${compose[@]}" run --rm --no-deps tests "$@"
