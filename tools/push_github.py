"""Push the local HEAD to GitHub over the REST API.

Use this when `git push` cannot reach github.com (e.g. direct 443 is reset) but
api.github.com is reachable. Files are read from the local git index (HEAD), so
.gitignore still applies.

    python tools/push_github.py            # push HEAD to main
    python tools/push_github.py --dry-run  # show what would be uploaded

Token lookup: $GITHUB_TOKEN, then `git credential fill` for github.com.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def repo_slug() -> str:
    out = subprocess.run(
        ["git", "remote", "get-url", "origin"], capture_output=True, text=True
    )
    url = out.stdout.strip()
    if not url:
        raise SystemExit("no git remote 'origin'")
    if url.startswith("git@"):
        url = url.split(":", 1)[1]
    url = url.removeprefix("https://github.com/").removeprefix("http://github.com/")
    return url.removesuffix(".git").strip("/")


def token() -> str:
    # The stored git credential is tried first: a stale $GITHUB_TOKEN in the
    # environment would otherwise shadow a working credential.
    p = subprocess.run(
        ["git", "credential", "fill"],
        input=b"protocol=https\nhost=github.com\n\n",
        capture_output=True,
    )
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    env = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if env:
        return env.strip()
    raise SystemExit("no GitHub token (store a credential or set GITHUB_TOKEN)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="main")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    slug = repo_slug()
    hdr = {
        "Authorization": "token " + token(),
        "User-Agent": "msx-clone-push",
        "Accept": "application/vnd.github+json",
    }

    def call(method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(API + path, data=data, headers=hdr, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:600]}")

    files = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
    ).stdout.decode("utf-8", "replace").splitlines()
    message = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], capture_output=True
    ).stdout.decode("utf-8", "replace").strip()

    print(f"repo   {slug}")
    print(f"branch {args.branch}")
    print(f"files  {len(files)}")
    print(f"msg    {message.splitlines()[0] if message else '(empty)'}")
    if args.dry_run:
        for f in files:
            print("  " + f)
        return 0

    try:
        remote = call("GET", f"/repos/{slug}/git/ref/heads/{args.branch}")
        parents = [remote["object"]["sha"]]
    except SystemExit:
        parents = []

    tree = []
    for i, name in enumerate(files, 1):
        with open(name, "rb") as f:
            raw = f.read()
        blob = call("POST", f"/repos/{slug}/git/blobs", {
            "content": base64.b64encode(raw).decode(),
            "encoding": "base64",
        })
        tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        if i % 25 == 0:
            print(f"  uploaded {i}/{len(files)}")

    root = call("POST", f"/repos/{slug}/git/trees", {"tree": tree})
    commit = call("POST", f"/repos/{slug}/git/commits", {
        "message": message or "update",
        "tree": root["sha"],
        "parents": parents,
    })
    if parents:
        call("PATCH", f"/repos/{slug}/git/refs/heads/{args.branch}", {
            "sha": commit["sha"], "force": True,
        })
    else:
        call("POST", f"/repos/{slug}/git/refs", {
            "ref": f"refs/heads/{args.branch}", "sha": commit["sha"],
        })
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{args.branch}", commit["sha"]])
    print(f"done   {commit['sha']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
