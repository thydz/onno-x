"""Web UI untuk onno-x.

Menjalankan agent onno-x dari browser, setara `opencode serve` / `opencode pair`:
sebuah HTTP server lokal yang menyajikan UI chat, lalu URL-nya dibuka di browser.

    onno-x serve                 # http://127.0.0.1:8765, langsung dibuka di browser
    onno-x serve --port 9000
    onno-x serve --host 0.0.0.0 --allow-remote   # butuh eksplisit (berisiko)

Desain:
- Pure stdlib (`http.server`), tanpa dependency baru.
- Streaming token & event tool via SSE.
- Prompt izin tool (y/n/a) lewat HTTP, dengan timeout supaya tidak menggantung.
- Token acak untuk autentikasi, supaya halaman tidak bisa diakses bebas dari
  jaringan lain (agen bisa menjalankan perintah shell!).
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from onno_x.config import Config, load_config, save_config
from onno_x.persistence import delete_session, list_sessions, load_session
from onno_x.session import AgentSession
from onno_x.web_ui import HTML_PAGE

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PERMISSION_TIMEOUT = 300.0  # detik


# --------------------------------------------------------------------------
# Event stream: buffer per-turn supaya klien SSE bisa replay lalu tail
# --------------------------------------------------------------------------
class EventStream:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._events: List[Dict[str, Any]] = []
        self._closed = False

    def emit(self, event: Dict[str, Any]) -> None:
        with self._cond:
            self._events.append(event)
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    def read_from(self, index: int, timeout: float = 10.0) -> Tuple[List[Dict[str, Any]], int]:
        with self._cond:
            if index >= len(self._events) and not self._closed:
                self._cond.wait(timeout)
            if index < len(self._events):
                chunk = self._events[index:]
                return chunk, index + len(chunk)
            return [], index


# --------------------------------------------------------------------------
# State bersama: sesi agent, stream turn, antrean permintaan izin
# --------------------------------------------------------------------------
class WebHub:
    def __init__(self, cfg: Config, model: Optional[str] = None) -> None:
        self.cfg = cfg
        self.lock = threading.RLock()
        if model:
            if model not in cfg.models:
                raise ValueError(f"Model '{model}' tidak dikenal.")
            cfg.active_model = model
        self.session = AgentSession(cfg)
        self.session.permission_handler = self._on_permission
        self.streams: Dict[str, EventStream] = {}
        self.permissions: Dict[str, Dict[str, Any]] = {}
        self.current_turn: Optional[str] = None
        self.turn_counter = 0

    # -------------------------------------------------------------- helpers
    def _emit(self, event: Dict[str, Any]) -> None:
        with self.lock:
            stream = self.streams.get(self.current_turn or "")
        if stream:
            stream.emit(event)

    # --------------------------------------------------------------- state
    def state(self) -> Dict[str, Any]:
        with self.lock:
            models = []
            for m in self.cfg.models.values():
                data = m.model_dump()
                data.pop("api_key", None)  # jangan pernah kirim API key ke browser
                models.append(data)
            return {
                "models": models,
                "active_model": getattr(self.cfg.models.get(self.cfg.active_model), "name", self.cfg.active_model),
                "permission_mode": self.session.permission_mode,
                "cwd": os.getcwd(),
                "session_id": self.session.session_id,
                "messages_count": len(self.session.messages),
                "turns_count": self.session.turns_count,
                "max_steps": self.cfg.max_steps,
            }

    def set_permission_mode(self, mode: str) -> Optional[str]:
        mode = (mode or "").lower().strip()
        if mode not in ("auto", "manual", "all"):
            return None
        with self.lock:
            self.session.permission_mode = mode
            return mode

    def switch_model(self, name: str) -> Optional[str]:
        with self.lock:
            # UI kirim ModelSpec.name; key dict bisa beda (mis. key "gpt-oss", name "onno-oss").
            if name not in self.cfg.models:
                name = next((k for k, m in self.cfg.models.items() if m.name == name), "")
            if not name:
                return None
            if not self.session.switch_model(name):
                return None
            self.cfg.active_model = name
            try:
                save_config(self.cfg)
            except Exception:
                pass
            return self.cfg.models[name].name

    def new_session(self) -> str:
        with self.lock:
            self.session = AgentSession(self.cfg)
            self.session.permission_handler = self._on_permission
            return self.session.session_id

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        with self.lock:
            data = load_session(session_id)
            if not data:
                return []
            self.session.session_id = data.get("session_id", session_id)
            self.session.messages = data.get("messages", self.session.messages)
            self.session.turns_count = data.get("turns_count", self.session.turns_count)
            self.session.permission_mode = data.get("permission_mode", self.session.permission_mode)
            return self.session.messages

    # -------------------------------------------------------------- izin
    def _on_permission(self, name: str, args: Dict[str, Any], mode: str) -> str:
        request_id = uuid.uuid4().hex[:8]
        event = threading.Event()
        with self.lock:
            self.permissions[request_id] = {"event": event, "choice": "n"}
        self._emit({
            "type": "permission",
            "request_id": request_id,
            "name": name,
            "args": args,
            "mode": mode,
        })
        try:
            if not event.wait(timeout=PERMISSION_TIMEOUT):
                return "n"
            with self.lock:
                pending = self.permissions.get(request_id)
                return (pending or {}).get("choice", "n")
        finally:
            with self.lock:
                self.permissions.pop(request_id, None)

    def answer_permission(self, request_id: str, choice: str) -> bool:
        with self.lock:
            pending = self.permissions.get(request_id)
            if not pending:
                return False
            pending["choice"] = choice
            pending["event"].set()
            return True

    # --------------------------------------------------------------- turn
    def start_turn(self, message: str) -> str:
        with self.lock:
            self.turn_counter += 1
            turn_id = f"turn-{self.turn_counter}-{uuid.uuid4().hex[:6]}"
            stream = EventStream()
            self.streams[turn_id] = stream
            self.current_turn = turn_id
        thread = threading.Thread(
            target=self._run_turn,
            args=(turn_id, message, stream),
            daemon=True,
            name=f"web-turn-{turn_id}",
        )
        thread.start()
        return turn_id

    def _run_turn(self, turn_id: str, message: str, stream: EventStream) -> None:
        try:
            stream.emit({"type": "user", "text": message})

            def on_token(token: str) -> None:
                stream.emit({"type": "token", "text": token})

            def on_status(kind: str, detail: str) -> None:
                stream.emit({"type": "status", "kind": kind, "detail": detail})

            def on_tool_call(name: str, args: Dict[str, Any]) -> None:
                stream.emit({"type": "tool_call", "name": name, "args": args})

            def on_tool_result(name: str, result: str) -> None:
                stream.emit({"type": "tool_result", "name": name, "text": (result or "")[:4000]})

            def on_error(message: str) -> None:
                stream.emit({"type": "error", "message": message})

            final = self.session.run_turn(
                message,
                on_output=lambda renderable: None,  # renderable-rich tidak dipakai di web
                on_token=on_token,
                on_status=on_status,
                on_tool_call=on_tool_call,
                on_tool_result=on_tool_result,
                on_error=on_error,
            )
            stream.emit({"type": "done", "text": final or ""})
        except InterruptedError:
            stream.emit({"type": "done", "text": "", "interrupted": True})
        except Exception as exc:  # noqa: BLE001
            stream.emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            stream.close()
            with self.lock:
                # Bersihkan stream lama supaya tidak menumpuk di memori
                if len(self.streams) > 50:
                    for old in list(self.streams)[:-50]:
                        self.streams.pop(old, None)

    def stop_turn(self) -> None:
        self.session.cancel_requested.set()

    def stream_for(self, turn_id: str) -> Optional[EventStream]:
        with self.lock:
            return self.streams.get(turn_id)


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------
class WebRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "onno-x-web"
    sys_version = ""

    hub: WebHub  # diisi saat instantiate server
    token: str = ""

    # ------------------------------------------------------------ utilities
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        pass  # quieter: jangan poluhi terminal

    def _authorized(self, query: Dict[str, List[str]]) -> bool:
        header = self.headers.get("X-Onno-Token") or ""
        param = (query.get("t") or [""])[0]
        return bool(self.token) and (header == self.token or param == self.token)

    def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ------------------------------------------------------------- routing
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if path == "/" and self._authorized(query):
            body = HTML_PAGE.encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        if path == "/api/health":
            self._json({"ok": True, "app": "onno-x"})
            return

        if not self._authorized(query):
            self._json({"error": "Unauthorized"}, status=401)
            return

        if path == "/api/state":
            self._json(self.hub.state())
            return
        if path == "/api/sessions":
            try:
                sessions = list_sessions()
            except Exception:
                sessions = []
            self._json({"sessions": sessions})
            return
        if path == "/api/stream":
            self._serve_stream(query)
            return

        self._json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)

        if not self._authorized(query):
            self._json({"error": "Unauthorized"}, status=401)
            return

        payload = self._read_json()

        if path == "/api/turn":
            message = (payload.get("message") or "").strip()
            if not message:
                self._json({"error": "Pesan kosong."}, status=400)
                return
            turn_id = self.hub.start_turn(message)
            self._json({"turn_id": turn_id, "session_id": self.hub.session.session_id})
            return
        if path == "/api/permission":
            request_id = payload.get("request_id") or ""
            choice = payload.get("choice") or "n"
            ok = self.hub.answer_permission(request_id, choice)
            self._json({"ok": ok})
            return
        if path == "/api/stop":
            self.hub.stop_turn()
            self._json({"ok": True})
            return
        if path == "/api/model":
            name = (payload.get("model") or "").strip()
            result = self.hub.switch_model(name)
            if not result:
                self._json({"error": f"Model '{name}' tidak dikenal."}, status=400)
                return
            self._json({"ok": True, "active_model": result})
            return
        if path == "/api/session/new":
            session_id = self.hub.new_session()
            self._json({"ok": True, "session_id": session_id})
            return
        if path == "/api/mode":
            mode = self.hub.set_permission_mode(payload.get("mode") or "")
            if not mode:
                self._json({"error": "Mode harus auto, manual, atau all."}, status=400)
                return
            self._json({"ok": True, "permission_mode": mode})
            return
        if path == "/api/session/load":
            session_id = (payload.get("session_id") or "").strip()
            messages = self.hub.load_session(session_id)
            if not messages:
                self._json({"error": "Sesi tidak ditemukan."}, status=404)
                return
            self._json({"ok": True, "messages": messages})
            return
        if path == "/api/session/delete":
            session_id = (payload.get("session_id") or "").strip()
            if not delete_session(session_id):
                self._json({"error": "Sesi tidak ditemukan."}, status=404)
                return
            # Sesi aktif dihapus: ganti ke sesi baru agar tidak tersimpan ulang saat turn berikutnya.
            if session_id == self.hub.session.session_id:
                self.hub.new_session()
            self._json({"ok": True})
            return
        if path == "/api/sessions/clear":
            count = sum(delete_session(s["id"]) for s in list_sessions())
            self.hub.new_session()
            self._json({"ok": True, "deleted": count})
            return

        self._json({"error": "Not found"}, status=404)

    # ----------------------------------------------------------------- SSE
    def _serve_stream(self, query: Dict[str, List[str]]) -> None:
        turn_id = (query.get("turn") or [""])[0]
        stream = self.hub.stream_for(turn_id)
        if stream is None:
            self._json({"error": "Turn tidak ditemukan."}, status=404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

        index = 0
        last_ping = time.time()
        try:
            while True:
                events, index = stream.read_from(index, timeout=5.0)
                for event in events:
                    chunk = f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n".encode("utf-8")
                    self.wfile.write(chunk)
                    self.wfile.flush()
                if events:
                    last_ping = time.time()
                elif time.time() - last_ping > 15:
                    # keepalive supaya proxy/browser tidak memutus koneksi
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_ping = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # klien menutup tab / koneksi diputus


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def _find_free_port(host: str, port: int) -> int:
    for candidate in range(port, port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise OSError(f"Tidak ada port bebas di range {port}-{port + 19}.")


def run_web_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    model: Optional[str] = None,
    open_browser: bool = True,
    allow_remote: bool = False,
) -> None:
    """Jalankan Web UI onno-x lalu (opsional) buka di browser."""
    from onno_x.interrupt import install_interrupt_guard

    install_interrupt_guard()

    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if host not in local_hosts and not allow_remote:
        raise SystemExit(
            f"Menolak bind ke '{host}'.\n"
            "Web UI bisa menjalankan perintah shell di mesin ini.\n"
            "Kalau memang mau diakses dari jaringan lain, tambahkan --allow-remote."
        )

    cfg = load_config()
    try:
        hub = WebHub(cfg, model=model)
    except ValueError as exc:
        raise SystemExit(str(exc))

    token = secrets.token_urlsafe(18)
    handler = type("BoundWebRequestHandler", (WebRequestHandler,), {"hub": hub, "token": token})

    try:
        port = _find_free_port(host, port)
    except OSError as exc:
        raise SystemExit(str(exc))

    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{port}/?t={token}"

    print(f"\n  \033[36monno-x Web UI\033[0m  →  \033[1m{url}\033[0m", flush=True)
    print(f"  \033[2mCtrl+C untuk menghentikan server\033[0m\n", flush=True)

    if open_browser:
        def _open() -> None:
            time.sleep(0.4)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    try:
        httpd.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n  \033[33m⏹ Web UI dihentikan.\033[0m")
    finally:
        httpd.shutdown()
        httpd.server_close()
