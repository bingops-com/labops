#!/usr/bin/env bash
# Recover a static-site release without a Docker daemon or CI registry secret.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: CRANE_BIN=/path/to/google-crane $0 SOURCE_DIR BASE_IMAGE TARGET_IMAGE" >&2
  exit 2
fi
source_dir=$(realpath "$1")
base_image=$2
target_image=$3
crane_bin=${CRANE_BIN:-crane}
[[ "$base_image" =~ ^ghcr\.io/bingops-com/www@sha256:[a-f0-9]{64}$ ]] || { echo "Base must be a pinned www digest" >&2; exit 2; }
[[ "$target_image" == ghcr.io/bingops-com/www:* ]] || { echo "Target must be the www package" >&2; exit 2; }
"$crane_bin" mutate --help >/dev/null 2>&1 || { echo "Google go-containerregistry crane is required" >&2; exit 2; }
git -C "$source_dir" diff --quiet
git -C "$source_dir" diff --cached --quiet
git -C "$source_dir" diff --quiet HEAD origin/main
source_revision=$(git -C "$source_dir" rev-parse HEAD)
registry_user=$(gh api user --jq .login)
release_temp=$(mktemp -d)
trap 'rm -rf "$release_temp"' EXIT
export DOCKER_CONFIG="$release_temp/auth"
mkdir -m 700 "$DOCKER_CONFIG"
# Keep the credential in a pipe and temporary auth directory, never in logs.
gh auth token | "$crane_bin" auth login ghcr.io --username "$registry_user" --password-stdin
if "$crane_bin" digest "$target_image" >/dev/null 2>&1; then
  existing_revision=$("$crane_bin" config "$target_image" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision", ""))')
  [[ "$existing_revision" == "$source_revision" ]] || { echo "Refusing to replace a different immutable release" >&2; exit 1; }
  "$crane_bin" digest "$target_image"
  exit 0
fi
npm --prefix "$source_dir" run build
python3 - "$source_dir/dist" "$release_temp/site.tar.gz" <<'PY'
import gzip, io, pathlib, sys, tarfile
site = pathlib.Path(sys.argv[1])
if not (site / 'index.html').is_file():
    raise SystemExit('Missing static index.html')
with open(sys.argv[2], 'wb') as output:
    with gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as layer:
            # An opaque directory removes old static assets from lower layers.
            whiteout = tarfile.TarInfo('app/dist/.wh..wh..opq')
            whiteout.mode = 0o644
            layer.addfile(whiteout, io.BytesIO())
            for path in sorted(site.rglob('*')):
                if path.is_symlink():
                    raise SystemExit('Symlinks are not supported in the static release')
                info = layer.gettarinfo(str(path), arcname='app/dist/' + path.relative_to(site).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                info.mode = 0o755 if path.is_dir() else 0o644
                if path.is_file():
                    with path.open('rb') as content:
                        layer.addfile(info, content)
                else:
                    layer.addfile(info)
PY
"$crane_bin" mutate "$base_image" --platform linux/amd64 \
  --append "$release_temp/site.tar.gz" \
  --label "org.opencontainers.image.revision=$source_revision" \
  --label "org.opencontainers.image.source=https://github.com/bingops-com/www.bingops.com" \
  --tag "$target_image"
"$crane_bin" validate --remote "$target_image" --fast
"$crane_bin" digest "$target_image"
