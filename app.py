"""Loopback dashboard for Drift. Run python app.py --demo."""
from __future__ import annotations

import argparse
import json
import secrets
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from drift import BUCKETS, DriftError, Organizer, models

BASE = Path(__file__).resolve().parent


def create_server(organizer: Organizer, port: int = 8778, demo: bool = False) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"
    state = {"busy": False, "error": None, "plan": None}
    job_lock = threading.Lock()

    def run_plan(body):
        try:
            state["plan"] = organizer.propose(body["model"], body.get("intention", ""), body.get("excerpts") is True)
        except Exception as exc:
            state["error"] = str(exc)
        finally:
            state["busy"] = False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, mime="application/json"):
            raw = json.dumps(data).encode() if mime == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(raw)

        def host_ok(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.host_ok():
                return self.reply({"error": "Invalid local host."}, 403)
            if self.path == "/":
                html = (BASE / "static/index.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self.reply(html.encode(), mime="text/html")
            if self.path in {"/app.js", "/style.css"}:
                return self.reply((BASE / "static" / self.path[1:]).read_bytes(), mime="text/javascript" if self.path.endswith(".js") else "text/css")
            if self.headers.get("X-Drift-Token") != token:
                return self.reply({"error": "Local session required."}, 403)
            try:
                if self.path == "/api/state":
                    return self.reply({**state, "root": str(organizer.root), "demo": demo, "buckets": BUCKETS})
                if self.path == "/api/models":
                    return self.reply({"models": models()})
                if self.path == "/api/history":
                    return self.reply({"history": organizer.history()})
            except DriftError as exc:
                return self.reply({"error": str(exc)}, 400)
            return self.reply({"error": "Not found."}, 404)

        def do_POST(self):
            if not self.host_ok() or self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}" or self.headers.get("X-Drift-Token") != token:
                return self.reply({"error": "Local session and matching origin required."}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise DriftError("Invalid request size.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise DriftError("Request must be an object.")
                with job_lock:
                    if state["busy"]:
                        return self.reply({"error": "The model is still working. Please wait."}, 409)
                    if self.path == "/api/plan":
                        if not isinstance(body.get("model"), str) or not isinstance(body.get("intention", ""), str):
                            raise DriftError("Choose a model and enter a text preference.")
                        state.update(busy=True, error=None, plan=None)
                        threading.Thread(target=run_plan, args=(body,), daemon=True).start()
                        return self.reply({"started": True}, 202)
                    if self.path == "/api/apply":
                        result = organizer.apply(body.get("plan_id"), body.get("selected"))
                        state["plan"] = None
                        return self.reply(result)
                    if self.path == "/api/undo":
                        if type(body.get("id")) is not int:
                            raise DriftError("Choose a move to undo.")
                        state["plan"] = None
                        organizer.plan = None
                        return self.reply(organizer.undo(body["id"]))
                    if self.path == "/api/recover":
                        organizer.recover()
                        return self.reply({"history": organizer.history()})
                    if self.path == "/api/scan":
                        organizer.plan = None
                        state["plan"] = None
                        return self.reply(organizer.scan())
                return self.reply({"error": "Not found."}, 404)
            except (DriftError, OSError, ValueError, TypeError) as exc:
                return self.reply({"error": str(exc)}, 400)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Kshetrajna Drift — a local AI filing companion")
    parser.add_argument("--folder", type=Path, help="Approved folder. Only its loose files are read.")
    parser.add_argument("--demo", action="store_true", help="Use a disposable sample folder; inference is still real.")
    parser.add_argument("--port", type=int, default=8778)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if bool(args.folder) == bool(args.demo):
        parser.error("Choose exactly one of --demo or --folder PATH.")
    local = BASE / ".drift-local"
    if args.demo:
        root = local / "demo-downloads"
        if not root.exists():
            shutil.copytree(BASE / "sample-files", root)
    else:
        root = args.folder
    organizer = Organizer(root, local / "journal.sqlite3")
    server = create_server(organizer, args.port, args.demo)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Kshetrajna Drift: {url}\nApproved folder: {organizer.root}\nCtrl+C stops the dashboard.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        organizer.db.close()


if __name__ == "__main__":
    main()
