"""Read-only Games release gate; no third-party packages or cluster access."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


class ReleaseError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def extract_pins(application, values):
    chart = re.findall(
        r"(?m)^[ \t]+- repoURL: https://github\.com/bingops-com/games\.git\n"
        r"[ \t]+targetRevision: ([0-9a-f]{40})\n[ \t]+path: chart[ \t]*$",
        application,
    )
    image = re.findall(
        r"(?m)^  repository: ghcr\.io/bingops-com/games\n"
        r"  tag: sha-([0-9a-f]{40})[ \t]*$",
        values,
    )
    if len(chart) != 1 or len(image) != 1 or chart[0] != image[0]:
        raise ReleaseError("Games chart and image must share one explicit commit pin.")
    return chart[0]


def fetch_json(url, headers=None, allow_blob_redirect=False):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ReleaseError("Release verification response is too large.")
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        if error.code == 307 and allow_blob_redirect:
            location = error.headers.get("Location", "")
            # GHCR serves config blobs through its signed CDN. Permit one hop
            # to that exact HTTPS origin, without forwarding any bearer token.
            if not location.startswith("https://pkg-containers.githubusercontent.com/"):
                raise ReleaseError("Unexpected image configuration redirect.") from None
            return fetch_json(location)
        # No response body, request headers or bearer token enters the log.
        raise ReleaseError(f"Release verification returned HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ReleaseError("Release verification failed; retry the read-only check.") from None


def verify_published(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ReleaseError("Invalid Games commit.")
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GH_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    compare = fetch_json(
        f"https://api.github.com/repos/bingops-com/games/compare/{sha}...master",
        headers,
    )
    if compare.get("status") not in ("ahead", "identical"):
        raise ReleaseError("Games commit is not merged into master. Merge Games first, then pin the published merge commit.")

    # GHCR access is anonymous: never use the GitHub workflow credential here.
    auth = fetch_json("https://ghcr.io/token?service=ghcr.io&scope=repository:bingops-com/games:pull")
    token = auth.get("token")
    if not isinstance(token, str) or not token or len(token) > 16384:
        raise ReleaseError("Anonymous GHCR access is unavailable.")
    registry_headers = {
        "Authorization": "Bearer " + token,
        "Accept": ", ".join((
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        )),
    }

    def registry(path):
        return fetch_json("https://ghcr.io/v2/bingops-com/games/" + path, registry_headers, allow_blob_redirect=path.startswith("blobs/"))

    def digest(value):
        if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ReleaseError("Invalid image manifest digest.")
        return value

    manifest = registry("manifests/sha-" + sha)
    if "manifests" in manifest:
        target = next((item for item in manifest["manifests"] if item.get("platform", {}).get("os") == "linux" and item.get("platform", {}).get("architecture") == "amd64"), None)
        if target is None:
            raise ReleaseError("The published image does not support Linux/amd64.")
        manifest = registry("manifests/" + digest(target.get("digest")))
    config = registry("blobs/" + digest(manifest.get("config", {}).get("digest")))
    if config.get("os") != "linux" or config.get("architecture") != "amd64":
        raise ReleaseError("The published image does not support Linux/amd64.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--offline", action="store_true", help="Check pin consistency only; does not verify publication")
    args = parser.parse_args()
    try:
        sha = extract_pins(
            (args.root / "apps/gitops/clusters/labprod/games.yaml").read_text(),
            (args.root / "apps/workloads/games/clusters/labprod/values.yaml").read_text(),
        )
        if args.offline:
            print(f"Games pins agree: {sha}. Publication not checked (offline).")
        else:
            verify_published(sha)
            print(f"Games {sha}: merged, public Linux/amd64 image available.")
        return 0
    except (ReleaseError, OSError, KeyError, TypeError, AttributeError) as error:
        print(str(error) if isinstance(error, ReleaseError) else "Unable to verify Games release metadata.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
