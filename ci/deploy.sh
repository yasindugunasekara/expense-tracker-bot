#!/usr/bin/env bash
set -Eeuo pipefail
sha=${1:?commit required}
build=${2:?build number required}
export DEPLOY_ROOT=${3:?deployment root required}
[[ "$sha" =~ ^[a-f0-9]{40}$ && "$build" =~ ^[0-9]+$ ]] || exit 2
[[ "$DEPLOY_ROOT" = /* && -d "$DEPLOY_ROOT" ]] || exit 2
state="$DEPLOY_ROOT/.ci"
mkdir -p "$state/releases"
exec 9>"$state/deploy.lock"
flock -w 120 9
last=0
[[ ! -f "$state/build" ]] || read -r last < "$state/build"
(( build > last )) || { echo 'Stale build rejected'; exit 3; }
release="$state/releases/$sha"
incoming="$state/incoming/$build-$sha"
mkdir -p "$release"
tar -xf "$incoming/release.tar" -C "$release"
[[ -f "$DEPLOY_ROOT/.env" && -f "$DEPLOY_ROOT/credentials.json" ]] || { echo 'Production configuration missing'; exit 4; }
mkdir -p "$DEPLOY_ROOT/gmail-state"
chmod 700 "$DEPLOY_ROOT/gmail-state"
if [[ ! -f "$DEPLOY_ROOT/gmail-state/token.json" && -f "$DEPLOY_ROOT/token.json" ]]; then
    cp "$DEPLOY_ROOT/token.json" "$DEPLOY_ROOT/gmail-state/token.json"
    chmod 600 "$DEPLOY_ROOT/gmail-state/token.json"
fi
export RELEASE_IMAGE="expense-tracker:$sha"
docker build --label "org.opencontainers.image.revision=$sha" -t "$RELEASE_IMAGE" "$release"
# Capture the exact image and configuration of the running service before replacement.
previous_image=$(docker inspect expense-tracker --format '{{.Image}}')
previous_compose=$(docker inspect expense-tracker --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
previous_root=$(docker inspect expense-tracker --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}')
printf '%s\n' "$previous_image" > "$state/previous-image"
printf '%s\n' "$previous_compose" > "$state/previous-compose"
printf '%s\n' "$previous_root" > "$state/previous-root"
# Force rollback to the captured image even for the pre-CI build-based compose file.
printf 'services:\n  expense-tracker:\n    image: %s\n' "$previous_image" > "$state/rollback-image.yml"
rollback() {
    trap - ERR INT TERM
    echo 'Deployment failed; restoring previous release'
    docker compose --project-directory "$previous_root" -p expense-tracker -f "$previous_compose" -f "$state/rollback-image.yml" up -d --no-deps --no-build expense-tracker
    echo 'Previous release restored'
}
trap 'rollback; exit 1' ERR INT TERM
compose=(docker compose --project-directory "$release" -p expense-tracker -f "$release/ci/compose.production.yml")
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-deps --no-build expense-tracker
ready=0
for attempt in {1..30}; do
    if [[ $(docker inspect expense-tracker --format '{{.State.Health.Status}}') == healthy ]] &&
       docker exec expense-tracker curl -fsS http://127.0.0.1:8000/health/db >/dev/null &&
       docker exec expense-tracker python /app/ci/check_processes.py; then
        ready=1
        break
    fi
    sleep 5
done
(( ready == 1 ))
printf '%s\n' "$sha" > "$state/commit.tmp"
printf '%s\n' "$build" > "$state/build.tmp"
mv "$state/commit.tmp" "$state/commit"
mv "$state/build.tmp" "$state/build"
trap - ERR INT TERM
printf 'DEPLOYED commit=%s build=%s image=%s\n' "$sha" "$build" "$RELEASE_IMAGE"
