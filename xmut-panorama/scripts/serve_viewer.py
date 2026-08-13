#!/usr/bin/env python3
"""Local embedded viewer for XMUT 3D panorama.

Official site sends X-Frame-Options: SAMEORIGIN, so cross-origin iframes fail.
This server serves a local HTML shell and reverse-proxies /2022 assets while
stripping frame-busting headers.

Also exposes /api/goto + /api/state so repeated opens update the already-open
viewer tab (macOS `open` often only focuses the old tab without navigating).

Usage:
  python3 scripts/serve_viewer.py --foreground --no-open
  python3 scripts/serve_viewer.py 图书馆
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "viewer" / "index.html"
VIEWER_DIR = ROOT / "viewer"
PLACES = ROOT / "references" / "places.json"
UPSTREAM = "https://3d.xmut.edu.cn"
DEFAULT_HOST = "127.0.0.1"  # listen address
DEFAULT_OPEN_HOST = "localhost"  # URL shown / opened in browser
DEFAULT_PORT = 8765
DROP_HEADERS = {
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "content-encoding",  # urllib 已解压，转发该头会导致浏览器二次解压失败
}

_STATE_LOCK = threading.Lock()
_STATE = {
    "scene_id": "pano926",
    "name": "空中全景",
    "seq": 0,
    "tour": None,
    "updated_at": 0.0,
}


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def load_places() -> dict:
    return json.loads(PLACES.read_text(encoding="utf-8"))


def resolve_scene(target: str | None) -> tuple[str, str]:
    data = load_places()
    if not target:
        return "空中全景", "pano926"
    key = target.strip()
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
        return hit["name"], hit["scene_id"]
    if key.startswith("pano"):
        return key, key
    raise SystemExit(f"unknown place/scene: {target}")


def set_state(scene_id: str, name: str | None = None, tour: str | None = None) -> dict:
    if not name:
        try:
            name, scene_id = resolve_scene(scene_id)
        except SystemExit:
            name = scene_id
    with _STATE_LOCK:
        _STATE["scene_id"] = scene_id
        _STATE["name"] = name
        _STATE["seq"] = int(_STATE["seq"]) + 1
        _STATE["tour"] = tour
        _STATE["updated_at"] = time.time()
        return dict(_STATE)


def get_state() -> dict:
    with _STATE_LOCK:
        return dict(_STATE)


def viewer_url(host: str, port: int, scene_id: str, tour: str | None = None) -> str:
    url = f"http://{host}:{port}/?scene={quote(scene_id)}"
    if tour:
        url += f"&tour={quote(tour)}"
    return url


def patch_upstream_html(body: bytes, content_type: str | None, query: str = "") -> bytes:
    """Bake startscene into HTML and force krpano to open that scene."""
    if not content_type or "text/html" not in content_type.lower():
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body

    qs = parse_qs(query)
    scene = (qs.get("startscene") or qs.get("s") or [None])[0]
    if not scene or not str(scene).startswith("pano"):
        scene = None

    if scene:
        # Client-side cookie so later index.xml requests still know the target scene
        # even if krpano requests xml without query string.
        inject = f"""<script>
window.__XMUT_STARTSCENE={json.dumps(scene)};
try {{
  document.cookie = "xmut_scene=" + window.__XMUT_STARTSCENE + "; path=/; SameSite=Lax";
}} catch (e) {{}}
function __xmutForceScene(krpano) {{
  var sc = window.__XMUT_STARTSCENE;
  if (!sc) return;
  var api = krpano || document.getElementById("krpanoSWFObject");
  if (!api || typeof api.call !== "function") return false;
  try {{
    api.call("mainloadscene(" + sc + ")");
    return true;
  }} catch (e1) {{
    try {{
      api.call("loadscene(" + sc + ", null, MERGE, BLEND(0.35))");
      return true;
    }} catch (e2) {{
      return false;
    }}
  }}
}}
window.__xmutForceScene = __xmutForceScene;
(function(){{
  var n = 0;
  var timer = setInterval(function(){{
    n += 1;
    if (__xmutForceScene() || n > 60) clearInterval(timer);
  }}, 200);
}})();
</script>"""
        if "__XMUT_STARTSCENE" not in text:
            if "<head>" in text:
                text = text.replace("<head>", "<head>" + inject, 1)
            else:
                text = inject + text

        # Keep xml path stable (no query). Scene is passed via cookie + vars + onready.
        # Add onready hooks on both embedpano calls.
        if "onready:" not in text:
            text = text.replace(
                ",webglsettings:{preserveDrawingBuffer:false, depth:true, stencil:true}\n\t\t\t\t\t});",
                ",webglsettings:{preserveDrawingBuffer:false, depth:true, stencil:true}"
                ",onready:function(k){setTimeout(function(){window.__xmutForceScene&&window.__xmutForceScene(k);},50);}"
                "\n\t\t\t\t\t});",
            )
            # Fallback if whitespace differs: append before every embedpano closing after webglsettings once more loosely
            if "onready:function" not in text:
                text = text.replace(
                    "webglsettings:{preserveDrawingBuffer:false, depth:true, stencil:true}",
                    "webglsettings:{preserveDrawingBuffer:false, depth:true, stencil:true},onready:function(k){setTimeout(function(){window.__xmutForceScene&&window.__xmutForceScene(k);},50);}",
                )

    text = text.replace(
        "vars:{skipintro:true,norotation:true,startscene:curScene,starttime:curTime}",
        "vars:{skipintro:true,norotation:true,startscene:(window.__XMUT_STARTSCENE||curScene),starttime:curTime}",
    )
    text = text.replace(
        "vars:{startscene:curScene,starttime:curTime}",
        "vars:{startscene:(window.__XMUT_STARTSCENE||curScene),starttime:curTime}",
    )
    text = text.replace(
        "accessStdVr();",
        "accessStdVr(window.__XMUT_STARTSCENE||null);",
    )
    text = text.replace(
        "accessWebVr();",
        "accessWebVr(window.__XMUT_STARTSCENE||null);",
    )

    # Disable little-planet intro that feels like aerial overview.
    text = text.replace(
        'tour_firstlittleplanet="true"',
        'tour_firstlittleplanet="false"',
    )

    return text.encode("utf-8")


def patch_index_xml(body: bytes, scene: str | None) -> bytes:
    """Force startup action to use the requested scene."""
    if not scene or not scene.startswith("pano"):
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body

    text = text.replace(
        'tour_firstlittleplanet="true"',
        'tour_firstlittleplanet="false"',
    )

    text2, n = re.subn(
        r'(<action name="startup">\s*)',
        rf"\1set(startscene, {scene});\n    set(s, {scene});\n    ",
        text,
        count=1,
    )
    if n:
        text = text2

    text = re.sub(
        r"set\(startscene,\s*pano926\);",
        f"set(startscene, {scene});",
        text,
        count=1,
    )
    return text.encode("utf-8")


def scene_from_cookie(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    m = re.search(r"(?:^|;\s*)xmut_scene=(pano\d+)", cookie_header)
    return m.group(1) if m else None


def scene_from_query_or_referer(query: str, referer: str | None) -> str | None:
    qs = parse_qs(query)
    scene = (qs.get("startscene") or qs.get("s") or [None])[0]
    if scene and str(scene).startswith("pano"):
        return scene
    if referer:
        try:
            ref = urlparse(referer)
            rqs = parse_qs(ref.query)
            scene = (rqs.get("startscene") or rqs.get("s") or [None])[0]
            if scene and str(scene).startswith("pano"):
                return scene
        except Exception:
            return None
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "XMUTPanoramaViewer/1.2"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def do_HEAD(self) -> None:
        self.head_only = True
        try:
            self.do_GET()
        finally:
            self.head_only = False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._send_file(VIEWER, "text/html; charset=utf-8")
            return
        if path == "/places.json":
            self._send_file(PLACES, "application/json; charset=utf-8")
            return
        if path.startswith("/assets/"):
            rel = path[len("/assets/") :]
            if ".." in rel or rel.startswith("/"):
                self.send_error(400, "invalid path")
                return
            asset = (VIEWER_DIR / "assets" / rel).resolve()
            assets_root = (VIEWER_DIR / "assets").resolve()
            try:
                asset.relative_to(assets_root)
            except ValueError:
                self.send_error(400, "invalid path")
                return
            if not asset.is_file():
                self.send_error(404, "asset not found")
                return
            ctype = "application/octet-stream"
            if asset.suffix.lower() == ".png":
                ctype = "image/png"
            elif asset.suffix.lower() in (".jpg", ".jpeg"):
                ctype = "image/jpeg"
            elif asset.suffix.lower() == ".svg":
                ctype = "image/svg+xml"
            elif asset.suffix.lower() == ".webp":
                ctype = "image/webp"
            self._send_file(asset, ctype)
            return
        if path == "/api/state":
            self._send_json(get_state())
            return
        if path == "/api/goto":
            scene = (qs.get("scene") or qs.get("startscene") or [None])[0]
            tour = (qs.get("tour") or [None])[0]
            if scene:
                # Some clients pass UTF-8 bytes decoded as latin-1.
                try:
                    repaired = scene.encode("latin-1").decode("utf-8")
                    if repaired:
                        scene = repaired
                except Exception:
                    pass
            if not scene:
                self.send_error(400, "missing scene")
                return
            try:
                name, scene_id = resolve_scene(scene)
            except SystemExit:
                self.send_error(404, f"unknown scene: {scene}")
                return
            state = set_state(scene_id, name, tour)
            self._send_json(state)
            return
        if path.startswith("/proxy/"):
            self._proxy(path[len("/proxy/") :], parsed.query)
            return
        self.send_error(404, "not found")

    def _write_body(self, data: bytes) -> None:
        if getattr(self, "head_only", False):
            return
        self.wfile.write(data)

    def _send_json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._write_body(data)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.is_file():
            self.send_error(404, f"missing {file_path.name}")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._write_body(data)

    def _proxy(self, upstream_path: str, query: str) -> None:
        if ".." in upstream_path:
            self.send_error(400, "invalid path")
            return

        scene = scene_from_query_or_referer(query, self.headers.get("Referer"))
        if not scene:
            scene = scene_from_cookie(self.headers.get("Cookie"))
        path_l = upstream_path.lower()
        # Our startscene query is only for local patching; do not send it upstream.
        upstream_query = query
        if path_l.endswith("index.xml") or path_l.endswith("index_vr.xml") or path_l.endswith(
            "index.html"
        ) or upstream_path.rstrip("/") in ("2022", "2022/"):
            keep = []
            for key, values in parse_qs(query).items():
                if key in ("startscene", "s", "_"):
                    continue
                for value in values:
                    keep.append(f"{quote(key)}={quote(value)}")
            upstream_query = "&".join(keep)

        target = f"{UPSTREAM}/{upstream_path}"
        if upstream_query:
            target += f"?{upstream_query}"
        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": "xmut-panorama-viewer/1.2",
                "Accept": self.headers.get("Accept", "*/*"),
                "Referer": f"{UPSTREAM}/2022/",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                is_tour_html = (
                    "text/html" in (ctype or "") and b"embedpano" in body and b"accessStdVr" in body
                )
                if is_tour_html:
                    body = patch_upstream_html(body, ctype, query)
                elif path_l.endswith("index.xml") or path_l.endswith("index_vr.xml"):
                    body = patch_index_xml(body, scene)

                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    lk = key.lower()
                    if lk in DROP_HEADERS or lk == "content-length":
                        continue
                    if lk == "location" and value.startswith(UPSTREAM):
                        value = "/proxy/" + value[len(UPSTREAM) + 1 :]
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Cache-Control",
                    "no-store"
                    if (is_tour_html or path_l.endswith("index.xml") or path_l.endswith("index_vr.xml"))
                    else "public, max-age=300",
                )
                self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
                if is_tour_html and scene:
                    self.send_header(
                        "Set-Cookie",
                        f"xmut_scene={scene}; Path=/; SameSite=Lax",
                    )
                self.end_headers()
                self._write_body(body)
        except urllib.error.HTTPError as err:
            body = err.read()
            self.send_response(err.code)
            self.send_header("Content-Type", err.headers.get("Content-Type", "text/plain"))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write_body(body)
        except Exception as err:  # noqa: BLE001
            msg = f"proxy error: {err}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self._write_body(msg)


def open_browser(url: str) -> bool:
    import platform
    import subprocess
    import webbrowser

    system = platform.system()
    cmds = {
        "Darwin": ["open", url],
        "Windows": ["cmd", "/c", "start", "", url],
    }.get(system, ["xdg-open", url])
    try:
        completed = subprocess.run(cmds, check=False, capture_output=True, text=True)
        if completed.returncode == 0:
            return True
    except Exception:
        pass
    try:
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def ensure_server(host: str, port: int) -> tuple[ThreadingHTTPServer | None, bool]:
    if port_open(host, port):
        return None, True
    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, False


def main() -> None:
    parser = argparse.ArgumentParser(description="XMUT embedded panorama viewer")
    parser.add_argument("target", nargs="?", help="place name / scene_id")
    parser.add_argument("--host", default=DEFAULT_HOST, help="listen address (default 127.0.0.1)")
    parser.add_argument(
        "--open-host",
        default=DEFAULT_OPEN_HOST,
        help="hostname used in browser URL (default localhost)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tour", choices=["freshman"], help="start freshman tour")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    args = parser.parse_args()

    name, scene_id = resolve_scene(args.target)
    state = set_state(scene_id, name, args.tour)
    url = viewer_url(args.open_host, args.port, scene_id, args.tour)

    server, already = ensure_server(args.host, args.port)
    opened = False if args.no_open else open_browser(url)

    print(
        json.dumps(
            {
                "mode": "embed",
                "opened": opened,
                "already_running": already,
                "name": name,
                "scene_id": scene_id,
                "seq": state["seq"],
                "viewer_url": url,
                "listen": f"{args.host}:{args.port}",
                "upstream": f"{UPSTREAM}/2022/?startscene={scene_id}",
            },
            ensure_ascii=False,
        )
    )

    if args.foreground:
        try:
            print(
                f"serving http://{args.open_host}:{args.port}/ (listen {args.host}) — Ctrl+C to stop",
                file=sys.stderr,
            )
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            if server is not None:
                server.shutdown()
        return

    if server is not None:
        time.sleep(2)


if __name__ == "__main__":
    main()
