#!/usr/bin/env python3
"""Publish built APKs to the GitHub 'latest' release.

Flow:
1. Create the release (tag 'latest') if it does not exist.
2. Upload every *.apk (+ manifest.json if present) with --clobber.
3. Delete superseded older-version APKs via scripts/cleanup_old_apks.py.
4. Refresh the release title and notes from the final asset list.

Upload-first-then-cleanup order is deliberate: if the upload fails the old
asset is still there; if cleanup fails the job fails loudly instead of
silently accumulating superseded APKs.

Usage:
    python scripts/github_publish_release.py --apks-dir ./release-apks [--tag latest]
"""
import argparse
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")

REPO_ROOT = Path(__file__).resolve().parent.parent
CLEANUP_SCRIPT = REPO_ROOT / "scripts" / "cleanup_old_apks.py"


def gh(args: list[str], token: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    env.pop("GITHUB_TOKEN", None)
    result = subprocess.run(["gh", *args], capture_output=True, text=True, env=env)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"gh {' '.join(args)} failed: {detail[:500]}")
    return result


def repo_slug(token: str) -> str:
    slug = (os.environ.get("GITHUB_REPOSITORY") or "").strip()
    if slug:
        return slug
    out = gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
             token).stdout.strip()
    if not out:
        raise RuntimeError("cannot determine repository slug (GITHUB_REPOSITORY unset)")
    return out


def release_exists(tag: str, token: str) -> bool:
    return gh(["release", "view", tag], token, check=False).returncode == 0


def ensure_release(tag: str, token: str) -> None:
    if release_exists(tag, token):
        return
    logging.info(f"Release '{tag}' not found; creating it.")
    gh(["release", "create", tag,
        "--title", "Morphe APKs",
        "--notes", "Auto-built Morphe APKs.",
        "--latest"], token)


def asset_names(tag: str, token: str) -> list[str]:
    out = gh(["release", "view", tag, "--json", "assets", "--jq", ".assets[].name"],
             token).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def build_notes(names: list[str], repo: str, tag: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    base = f"https://github.com/{repo}/releases/download/{tag}"
    lines = ["# Morphe APKs - Auto Built", "", "## Available Apps", ""]
    for name in sorted(set(names)):
        if name.endswith(".apk"):
            lines.append(f"- [{name}]({base}/{name})")
        else:
            lines.append(f"- {name}")
    lines += [
        "", "---", "",
        "## Build Information",
        f"- **Auto-built {now} UTC**",
        "- **Multiple architecture support** (arm64-v8a, armeabi-v7a, universal)",
        "- **Latest Morphe patches**",
        "", "## Architecture Guide",
        "- **arm64-v8a**: Modern ARM devices (2014+)",
        "- **armeabi-v7a**: Older ARM devices",
        "- **universal**: All ARM devices (larger file)",
        "", "## Disclaimer",
        "These APKs are built automatically. Use at your own risk.",
    ]
    return "\n".join(lines)


def update_metadata(tag: str, token: str, repo: str, names: list[str]) -> None:
    title = "Morphe APKs - " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    notes = build_notes(names, repo, tag)
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(notes + "\n")
        gh(["release", "edit", tag, "--title", title, "--notes-file", path], token)
    finally:
        os.unlink(path)


def cleanup_superseded(tag: str, token: str, apks: list[Path]) -> None:
    fd, keep_file = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for apk in apks:
                f.write(apk.name + "\n")
        env = os.environ.copy()
        env["GH_TOKEN"] = token
        env.pop("GITHUB_TOKEN", None)
        result = subprocess.run(
            [sys.executable, str(CLEANUP_SCRIPT), "--release", tag,
             "--keep-file", keep_file],
            capture_output=True, text=True, env=env,
        )
        for line in (result.stdout or "").splitlines():
            logging.info(line)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"cleanup_old_apks.py failed: {detail[:500]}")
    finally:
        os.unlink(keep_file)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apks-dir", required=True)
    parser.add_argument("--tag", default="latest")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        logging.error("GH_TOKEN/GITHUB_TOKEN is not set.")
        return 1

    apks_dir = Path(args.apks_dir)
    apks = sorted(apks_dir.glob("*.apk"))
    manifest = apks_dir / "manifest.json"
    if not apks:
        logging.info("No APKs to publish; skipping release.")
        return 0

    repo = repo_slug(token)
    ensure_release(args.tag, token)

    assets = list(apks)
    if manifest.exists():
        assets.append(manifest)

    logging.info(f"Uploading {len(assets)} asset(s) to '{args.tag}'...")
    gh(["release", "upload", args.tag, *[str(a) for a in assets], "--clobber"], token)

    logging.info("Removing superseded APK versions...")
    cleanup_superseded(args.tag, token, apks)

    names = asset_names(args.tag, token)
    update_metadata(args.tag, token, repo, names)

    url = f"https://github.com/{repo}/releases/tag/{args.tag}"
    logging.info(f"Release URL: {url}")
    extra = " plus manifest" if manifest.exists() else ""
    logging.info(f"Published {len(apks)} APK(s){extra} to '{args.tag}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
