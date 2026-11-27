"""Penjaga Ctrl+C (anti "Exception ignored on threading shutdown").

Kenapa modul ini ada?
---------------------
Saat Anda menekan Ctrl+C, Python menjalankan `threading._shutdown()` yang memanggil
`concurrent.futures.thread._python_exit()`. Fungsi itu melakukan `thread.join()`
TANPA timeout untuk setiap worker `ThreadPoolExecutor` yang masih hidup.

Kalau salah satu worker-nya macet (mis. menunggu socket MCP yang tidak pernah
datang), `join()` itu memblokir selamanya -> program "nge-hang" saat keluar.

Tekan Ctrl+C kedua -> `KeyboardInterrupt` muncul DI DALAM hook atexit sehingga
Python tidak bisa meneruskannya, dan hanya mencetak:

    Exception ignored on threading shutdown:
    Traceback (most recent call last):
      ...
      File ".../concurrent/futures/thread.py", line 31, in _python_exit
        t.join()
      KeyboardInterrupt:

Modul ini memasang penjaga: begitu interpreter masuk fase shutdown, Ctrl+C
berikutnya langsung keluar paksa (`os._exit`) -> tidak ada traceback, tidak nge-hang.
"""

import os
import signal
import sys
import threading
from typing import Any, Dict

# PENTING: import ini harus DI AWAL modul.
# `concurrent.futures.thread` mendaftarkan `_python_exit` ke `threading._register_atexit`.
# Hook-hook tersebut dijalankan dengan urutan terbalik (yang terdaftar terakhir jalan
# pertama), jadi dengan meng-import modul ini lebih dulu, `_python_exit` terdaftar
# lebih awal -> hook penjaga kita (yang terdaftar belakangan) akan jalan LEBIH DAHULU
# dan flag "sedang shutdown" selalu terpasang sebelum join yang macet terjadi.
try:  # pragma: no cover - hanya untuk mengatur urutan registrasi hook
    import concurrent.futures.thread  # noqa: F401
except Exception:  # pragma: no cover
    pass

_STATE: Dict[str, Any] = {"installed": False, "shutting_down": False}


def _flush_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


def hard_exit(code: int = 130) -> None:
    """Keluar paksa tanpa menjalankan atexit hook (yang bisa saja nge-hang)."""
    _flush_streams()
    os._exit(code)


def _mark_shutting_down() -> None:
    """Dipanggil tepat sebelum interpreter mulai shut down."""
    _STATE["shutting_down"] = True


def is_shutting_down() -> bool:
    """True kalau interpreter sedang dalam fase shutdown."""
    if _STATE["shutting_down"]:
        return True
    # Python >= 3.13 menandai fase ini lewat threading._SHUTTING_DOWN
    return bool(getattr(threading, "_SHUTTING_DOWN", False))


def _handle_sigint(signum, frame):
    if is_shutting_down():
        # Sudah di fase shutdown: jangan tunggu, keluar sekarang saja.
        hard_exit()
    raise KeyboardInterrupt


def install_interrupt_guard() -> None:
    """Pasang penjaga Ctrl+C. Aman dipanggil berkali-kali."""
    if _STATE["installed"]:
        return
    _STATE["installed"] = True

    register = getattr(threading, "_register_atexit", None)
    if callable(register):
        try:
            register(_mark_shutting_down)
        except Exception:
            pass

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (ValueError, OSError, RuntimeError):
        # Tidak di main thread / tidak didukung di platform ini -> pakai default.
        pass
