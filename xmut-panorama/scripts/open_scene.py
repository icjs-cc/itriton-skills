#!/usr/bin/env python3
"""Open XMUT panorama — default: local embedded viewer.

Usage:
  python3 scripts/open_scene.py 图书馆
  python3 scripts/open_scene.py pano1083
  python3 scripts/open_scene.py --tour freshman
  python3 scripts/open_scene.py 图书馆 --external
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES = ROOT / "references" / "places.json"
SERVE = ROOT / "scripts" / "serve_viewer.py"
BASE = "https://3d.xmut.edu.cn/2022/?startscene="
HOST = "127.0.0.1"  # bind / API（稳定走 IPv4）
OPEN_HOST = "localhost"  # 浏览器打开与展示用
PORT = 8765


def load_places() -> dict:
    return json.loads(PLACES.read_text(encoding="utf-8"))


def resolve_scene(name_or_id: str | None, data: dict) -> tuple[str, str, str]:
    if not name_or_id:
        p0 = next(p for p in data["places"] if p["scene_id"] == "pano926")
        return p0["name"], p0["scene_id"], p0["3d_url"]
    key = name_or_id.strip()
    lower = key.lower()
    exact = []
    soft = []
    for p in data["places"]:
        candidates = [p["name"], p["id"], p["scene_id"], *p.get("aliases", [])]
        if any(c.lower() == lower for c in candidates):
            exact.append(p)
        elif any(lower in c.lower() for c in candidates):
            soft.append(p)
    hit = (exact or soft or [None])[0]
    if hit:
        return hit["name"], hit["scene_id"], hit["3d_url"]
    if key.startswith("pano"):
        return key, key, BASE + key
    raise SystemExit(f"unknown place/scene: {name_or_id}")


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def open_url(url: str) -> bool:
    system = platform.system()
    if system == "Darwin":
        cmd = ["open", url]
    elif system == "Windows":
        cmd = ["cmd", "/c", "start", "", url]
    else:
        cmd = ["xdg-open", url]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if completed.returncode == 0:
            return True
    except Exception:
        pass
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def ensure_embed_server() -> tuple[bool, bool]:
    """Returns (ready, already_running)."""
    if port_open(HOST, PORT):
        return True, True
    log_path = ROOT / "viewer" / ".server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    subprocess.Popen(
        [sys.executable, str(SERVE), "--foreground", "--no-open"],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ.copy(),
    )
    for _ in range(40):
        if port_open(HOST, PORT):
            return True, False
        time.sleep(0.1)
    return False, False


def api_goto(scene_id: str, tour: str | None = None) -> dict | None:
    qs = {"scene": scene_id}
    if tour:
        qs["tour"] = tour
    url = f"http://{HOST}:{PORT}/api/goto?{urllib.parse.urlencode(qs)}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Open XMUT 3D panorama scene")
    parser.add_argument("target", nargs="?", help="scene_id / place name / alias")
    parser.add_argument("--name", help="place name or alias")
    parser.add_argument("--list", action="store_true", help="list places")
    parser.add_argument("--print-only", action="store_true", help="print URL only")
    parser.add_argument("--external", action="store_true", help="open official site directly")
    parser.add_argument("--tour", choices=["freshman"], help="open embedded freshman tour")
    parser.add_argument(
        "--reopen",
        action="store_true",
        help="always open/focus browser even if server already running",
    )
    args = parser.parse_args()
    data = load_places()

    if args.list:
        for p in data["places"]:
            print(f"{p['scene_id']}\t{p['name']}\t{p['3d_url']}")
        return

    target = args.name or args.target
    if args.tour and not target:
        target = "明理教学楼"
    if not target and not args.tour:
        parser.print_help()
        raise SystemExit(2)

    name, scene_id, upstream = resolve_scene(target, data)
    if args.external:
        url = upstream
        mode = "external"
        ready, already = True, False
        state = None
        opened = False if args.print_only else open_url(url)
    else:
        mode = "embed"
        if args.print_only:
            ready, already = port_open(HOST, PORT), port_open(HOST, PORT)
            state = None
            opened = False
        else:
            ready, already = ensure_embed_server()
            state = api_goto(scene_id, args.tour) if ready else None
            # If server was already up, rely on /api/goto + viewer polling.
            # Only force a browser open on first start (or --reopen).
            should_open = ready and ((not already) or args.reopen)
            url = f"http://{OPEN_HOST}:{PORT}/?scene={urllib.parse.quote(scene_id)}"
            if args.tour:
                url += f"&tour={urllib.parse.quote(args.tour)}"
            if state and "seq" in state:
                url += f"&seq={state['seq']}"
            opened = open_url(url) if should_open else False
            if already and state and not should_open:
                # Still try a soft focus open with same host — may not navigate,
                # but goto/poll keeps scene consistent.
                opened = False

    viewer_url = (
        upstream
        if args.external
        else f"http://{OPEN_HOST}:{PORT}/?scene={urllib.parse.quote(scene_id)}"
        + (f"&tour={args.tour}" if args.tour else "")
    )

    print(
        json.dumps(
            {
                "mode": mode,
                "opened": opened,
                "server_ready": ready,
                "already_running": already if mode == "embed" else False,
                "synced_via_api": bool(state),
                "name": name,
                "scene_id": scene_id,
                "seq": (state or {}).get("seq"),
                "viewer_url": viewer_url,
                "upstream": upstream,
                "note": (
                    "已通过 /api/goto 同步到现有查看器标签页"
                    if (mode == "embed" and already and state and not opened)
                    else None
                ),
            },
            ensure_ascii=False,
        )
    )
    if not args.print_only and not ready:
        raise SystemExit(1)
    if not args.print_only and mode == "embed" and not state and not opened:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
