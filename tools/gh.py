#!/usr/bin/env python3
"""Manage the deployed oshi-calendar repo through the GitHub API.

Local helper for the AI agent (and for you). It edits `targets.json` in the
repository, triggers the update workflow, and can do the initial deployment.

Auth (never commit these):
  .secrets/github_token.txt   fine-grained PAT, one line
  .secrets/github_repo.txt    owner/repo, one line

Or set GITHUB_TOKEN / GITHUB_REPO. `OSHI_SECRETS_DIR` overrides .secrets path.

Examples:
  python tools/gh.py status
  python tools/gh.py list
  python tools/gh.py search 渡瀬結月
  python tools/gh.py add 渡瀬結月 55045
  python tools/gh.py add-url https://www.eventernote.com/actors/川村玲奈/77840
  python tools/gh.py remove 55045
  python tools/gh.py dispatch
  python tools/gh.py deploy .
"""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lxml import html as lxml_html

ROOT = Path(__file__).resolve().parents[1]
SECRETS = Path(os.environ.get("OSHI_SECRETS_DIR", ROOT.parent / ".secrets"))
API = "https://api.github.com"
WORKFLOW = "update.yml"
TARGETS_FILE = "targets.json"

EXCLUDE_DIRS = {".git", ".secrets", "__pycache__"}
EXCLUDE_NAMES = {"sample.ics", "sample_preview.txt", "feed_preview.txt"}
EXCLUDE_SUFFIX = {".pyc", ".zip"}


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"GitHub API {status}: {body}")
        self.status = status
        self.body = body


def _read_secret(name: str) -> str:
    path = SECRETS / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def config() -> tuple[str, str]:
    token = os.environ.get("GITHUB_TOKEN") or _read_secret("github_token.txt")
    repo = os.environ.get("GITHUB_REPO") or _read_secret("github_repo.txt")
    if not token or not repo:
        raise SystemExit(
            "missing credentials: put the token in .secrets/github_token.txt "
            "and owner/repo in .secrets/github_repo.txt (or set GITHUB_TOKEN/GITHUB_REPO)"
        )
    return token, repo


def api(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | None]:
    token, _ = config()
    url = API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "oshi-calendar-manager",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", errors="replace")) from exc


def get_text(path: str) -> tuple[str | None, str | None]:
    _, repo = config()
    try:
        _, data = api("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}")
    except ApiError as exc:
        if exc.status == 404:
            return None, None
        raise
    assert data is not None
    return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]


def put_text(path: str, text: str, message: str) -> None:
    _, repo = config()
    _, repo_info = api("GET", f"/repos/{repo}")
    branch = (repo_info or {}).get("default_branch", "main")
    _, current_sha = get_text(path)
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if current_sha:
        payload["sha"] = current_sha
    api("PUT", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", payload)


def read_targets() -> list[dict]:
    text, _ = get_text(TARGETS_FILE)
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit("targets.json must be a JSON array")
    return data


def write_targets(targets: list[dict], message: str) -> None:
    text = json.dumps(targets, ensure_ascii=False, indent=2) + "\n"
    put_text(TARGETS_FILE, text, message)


def dispatch() -> None:
    _, repo = config()
    _, repo_info = api("GET", f"/repos/{repo}")
    branch = (repo_info or {}).get("default_branch", "main")
    last_error: ApiError | None = None
    for _ in range(5):
        try:
            api("POST", f"/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches", {"ref": branch})
            print("workflow dispatched")
            return
        except ApiError as exc:
            last_error = exc
            if exc.status in (404, 422):
                time.sleep(6)
                continue
            raise
    raise SystemExit(f"dispatch failed: {last_error}")


# ---------------------------------------------------------------- commands

def cmd_status() -> None:
    _, repo = config()
    _, info = api("GET", f"/repos/{repo}")
    assert info is not None
    print(f"repo: {repo}")
    print(f"default branch: {info.get('default_branch')}")
    print(f"private: {info.get('private')}")
    targets = read_targets()
    print(f"targets: {len(targets)}")
    try:
        _, runs = api("GET", f"/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=1")
        run = (runs or {}).get("workflow_runs", [])
        if run:
            print(f"latest run: {run[0]['status']} / {run[0].get('conclusion')} ({run[0]['created_at']})")
    except ApiError as exc:
        print(f"latest run: unavailable ({exc.status})")


def cmd_list() -> None:
    targets = read_targets()
    if not targets:
        print("(empty)")
        return
    for item in targets:
        print(f"{item.get('id'):>8}  {item.get('name')}")


def _eventernote_search(keyword: str) -> list[dict]:
    url = "https://www.eventernote.com/actors/search?keyword=" + urllib.parse.quote(keyword)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0",
            "Accept-Language": "ja,en;q=0.8",
        },
    )
    ctx = ssl._create_unverified_context() if os.environ.get("EVENTERNOTE_INSECURE") == "1" else ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    tree = lxml_html.fromstring(page)
    found: dict[str, dict] = {}
    for link in tree.xpath('//ul[contains(@class,"gb_actors_list")]/li/a'):
        href = link.get("href") or ""
        match = re.search(r"/actors/([^/]+)/(\d+)$", href)
        if not match:
            continue
        actor_id = match.group(2)
        found[actor_id] = {
            "id": actor_id,
            "name": link.text_content().strip() or urllib.parse.unquote(match.group(1)),
            "url": "https://www.eventernote.com" + href,
        }
    return list(found.values())


def cmd_search(keyword: str) -> None:
    results = _eventernote_search(keyword)
    if not results:
        print("no match")
        return
    for item in results:
        print(f"{item['id']:>8}  {item['name']}  {item['url']}")


def cmd_add(name: str, actor_id: str) -> None:
    targets = read_targets()
    if any(str(item.get("id")) == str(actor_id) for item in targets):
        print(f"already in targets: {actor_id}")
        return
    targets.append({"name": name, "id": str(actor_id)})
    write_targets(targets, f"chore: add target {name} ({actor_id})")
    print(f"added: {name} ({actor_id})")
    dispatch()


def cmd_add_url(url: str) -> None:
    match = re.search(r"/actors/([^/]+)/(\d+)", url)
    if not match:
        raise SystemExit("not an eventernote actor URL")
    name = urllib.parse.unquote(match.group(1))
    cmd_add(name, match.group(2))


def cmd_remove(key: str) -> None:
    targets = read_targets()
    kept = [t for t in targets if str(t.get("id")) != str(key) and str(t.get("name")) != str(key)]
    if len(kept) == len(targets):
        print(f"not found: {key}")
        return
    write_targets(kept, f"chore: remove target {key}")
    print(f"removed: {key}")
    dispatch()


def _collect_files(folder: Path) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIX:
            continue
        files.append((rel.as_posix(), path.read_bytes()))
    return files


def _ensure_initial_commit(repo: str, branch: str) -> None:
    """The Git Data API rejects blob creation on a repo with no commits."""
    try:
        api("GET", f"/repos/{repo}/git/ref/heads/{branch}")
        return
    except ApiError as exc:
        if exc.status not in (404, 409):
            raise
    api(
        "PUT",
        f"/repos/{repo}/contents/.gitignore",
        {
            "message": "chore: init",
            "content": base64.b64encode(b"__pycache__/\n*.pyc\n.secrets/\n").decode("ascii"),
            "branch": branch,
        },
    )


def cmd_deploy(folder: str) -> None:
    _, repo = config()
    base = Path(folder).resolve()
    files = _collect_files(base)
    if not files:
        raise SystemExit("no files to deploy")

    _, info = api("GET", f"/repos/{repo}")
    branch = (info or {}).get("default_branch", "main")
    _ensure_initial_commit(repo, branch)

    base_tree = None
    parents: list[str] = []
    _, ref = api("GET", f"/repos/{repo}/git/ref/heads/{branch}")
    parent = ref["object"]["sha"]  # type: ignore[index]
    _, commit = api("GET", f"/repos/{repo}/git/commits/{parent}")
    base_tree = commit["tree"]["sha"]  # type: ignore[index]
    parents = [parent]

    tree = []
    for rel, content in files:
        _, blob = api(
            "POST",
            f"/repos/{repo}/git/blobs",
            {"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
        )
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})  # type: ignore[index]

    tree_payload: dict = {"tree": tree}
    if base_tree:
        tree_payload["base_tree"] = base_tree
    _, new_tree = api("POST", f"/repos/{repo}/git/trees", tree_payload)
    _, new_commit = api(
        "POST",
        f"/repos/{repo}/git/commits",
        {"message": "chore: deploy oshi-calendar", "tree": new_tree["sha"], "parents": parents},  # type: ignore[index]
    )
    sha = new_commit["sha"]  # type: ignore[index]
    if parents:
        api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", {"sha": sha})
    else:
        api("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    print(f"deployed {len(files)} files to {repo}@{branch}")
    dispatch()


def cmd_set_permissions() -> None:
    _, repo = config()
    try:
        api(
            "PUT",
            f"/repos/{repo}/actions/permissions/workflow",
            {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": False},
        )
        print("workflow permissions set to write")
    except ApiError as exc:
        print(f"could not set permissions ({exc.status}); toggle it in Settings → Actions → General")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    command = sys.argv[1]
    args = sys.argv[2:]

    if command == "status":
        cmd_status()
    elif command == "list":
        cmd_list()
    elif command == "search":
        cmd_search(args[0])
    elif command == "add":
        cmd_add(args[0], args[1])
    elif command == "add-url":
        cmd_add_url(args[0])
    elif command == "remove":
        cmd_remove(args[0])
    elif command == "dispatch":
        dispatch()
    elif command == "deploy":
        cmd_deploy(args[0] if args else ".")
    elif command == "set-permissions":
        cmd_set_permissions()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
