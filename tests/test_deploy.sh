#!/usr/bin/env bash
set -euo pipefail
sandbox=${1:?sandbox required}
script=${2:?deployment script required}
mkdir -p "$sandbox/bin" "$sandbox/root" "$sandbox/source/ci"
export CALL_LOG="$sandbox/calls"
export MOCK_FAIL=0
cat > "$sandbox/bin/docker" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CALL_LOG"
if [[ "$1" == inspect ]]; then
    case "$*" in
        *State.Health.Status*) [[ "$MOCK_FAIL" == 0 ]] && echo healthy || echo unhealthy ;;
        *Config.Labels*working_dir*) echo "$DEPLOY_ROOT" ;;
        *Config.Labels*) echo "$DEPLOY_ROOT/original.yml" ;;
        *) echo sha256:previous ;;
    esac
fi
MOCK
printf '#!/usr/bin/env bash\nexit 0\n' > "$sandbox/bin/sleep"
printf '#!/usr/bin/env bash\nexit 0\n' > "$sandbox/bin/flock"
chmod +x "$sandbox/bin/"*
export PATH="$sandbox/bin:$PATH"
touch "$sandbox/root/.env" "$sandbox/root/credentials.json" "$sandbox/root/token.json"
touch "$sandbox/source/Dockerfile" "$sandbox/source/ci/compose.production.yml"
sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
mkdir -p "$sandbox/root/.ci/incoming/1-$sha" "$sandbox/root/.ci/incoming/2-$sha"
tar -cf "$sandbox/root/.ci/incoming/1-$sha/release.tar" -C "$sandbox/source" .
cp "$sandbox/root/.ci/incoming/1-$sha/release.tar" "$sandbox/root/.ci/incoming/2-$sha/release.tar"
bash "$script" "$sha" 1 "$sandbox/root"
[[ $(cat "$sandbox/root/.ci/commit") == "$sha" ]]
[[ $(cat "$sandbox/root/.ci/build") == 1 ]]
if bash "$script" "$sha" 1 "$sandbox/root"; then echo 'stale build accepted'; exit 1; fi
export MOCK_FAIL=1
if bash "$script" "$sha" 2 "$sandbox/root"; then echo 'unhealthy release accepted'; exit 1; fi
[[ $(cat "$sandbox/root/.ci/build") == 1 ]]
grep -q rollback-image.yml "$CALL_LOG"
echo 'Deployment success, stale rejection and rollback tests passed'
