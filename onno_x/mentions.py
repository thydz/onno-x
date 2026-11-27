"""Pemindai path untuk picker `@` (REPL + TUI).

Satu sumber kebenaran supaya kedua front-end menampilkan daftar yang sama:
folder dulu, lalu file, dengan pencarian bertingkat yang dibatasi jumlah
entri yang dipindai agar repo besar tidak memblokir UI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Tuple

# Folder yang tidak pernah berguna untuk di-mention dan bisa sangat besar.
IGNORE_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".onno-x",
    ".gemini",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "target",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".cache",
}

# Batas pemindaian: cukup untuk repo berukuran wajar, dan menjamin
# setiap penekanan tombol selesai dalam hitungan milidetik.
MAX_SCAN = 20000
MAX_DEPTH = 8

# Indeks jalur di-cache sebentar supaya tiap ketikan terasa instan;
# membangun ulang hanya setelah TTL habis (folder berubah tetap terdeteksi).
INDEX_TTL = 4.0
_index_cache: dict = {}


Mention = Tuple[str, bool, int]  # (path relatif, is_dir, ukuran byte)


def human_size(size: int) -> str:
    """Ukuran berkas ringkas untuk display_meta picker."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _visible(name: str) -> bool:
    return not name.startswith(".") or name in {".env.example", ".gitignore"}


def _entry(path: Path, root: Path) -> Mention:
    try:
        size = path.stat().st_size if path.is_file() else 0
    except OSError:
        size = 0
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.name
    return (rel, path.is_dir(), size)


def _sorted(entries: list) -> list:
    # Folder dulu supaya user bisa langsung menelusuri; lalu jalur pendek.
    return sorted(entries, key=lambda e: (not e[1], e[0].count("/"), e[0].lower()))


def iter_mentions(
    root: Path | str,
    prefix: str = "",
    limit: int = 60,
) -> list:
    """Kembalikan kandidat untuk token `@<prefix>`.

    - prefix kosong: isi folder kerja (tanpa rekursi)
    - prefix berakhir "/": isi folder tersebut
    - selain itu: pencarian rekursif, cocok bila jalur relatif memuat prefix
    """
    root = Path(root)
    if not root.is_dir():
        return []

    prefix = prefix.replace("\\", "/").lstrip("./")
    results: list = []

    if not prefix:
        try:
            children = list(root.iterdir())
        except OSError:
            return []
        for p in children:
            if p.name in IGNORE_NAMES or not _visible(p.name):
                continue
            results.append(_entry(p, root))
        return _sorted(results)[:limit]

    if prefix.endswith("/"):
        base = root / prefix
        if not base.is_dir():
            return []
        try:
            children = list(base.iterdir())
        except OSError:
            return []
        for p in children:
            if p.name in IGNORE_NAMES or not _visible(p.name):
                continue
            results.append(_entry(p, root))
        return _sorted(results)[:limit]

    needle = prefix.lower()
    basename_hits: list = []
    path_hits: list = []

    for rel, is_dir, size in _index(root):
        low = rel.lower()
        if needle not in low:
            continue
        name = rel.rsplit("/", 1)[-1].lower()
        item = (rel, is_dir, size)
        if name.startswith(needle) or name == needle:
            basename_hits.append(item)
        else:
            path_hits.append(item)
        if len(basename_hits) >= limit and len(path_hits) >= limit:
            break

    return (_sorted(basename_hits) + _sorted(path_hits))[:limit]


def _index(root: Path) -> list:
    """Indeks seluruh jalur visible di bawah root, di-cache singkat."""
    import time

    key = str(root)
    now = time.monotonic()
    cached = _index_cache.get(key)
    if cached and now - cached[0] < INDEX_TTL:
        return cached[1]

    entries: list = []
    scanned = 0
    try:
        for dirpath, dirnames, filenames in _walk(root):
            dirnames[:] = [
                d for d in dirnames if d not in IGNORE_NAMES and _visible(d)
            ][:200]
            for name in dirnames:
                scanned += 1
                if scanned > MAX_SCAN:
                    break
                p = Path(dirpath) / name
                entries.append((p.relative_to(root).as_posix(), True, 0))
            for name in filenames:
                if name in IGNORE_NAMES or not _visible(name):
                    continue
                scanned += 1
                if scanned > MAX_SCAN:
                    break
                p = Path(dirpath) / name
                if p.is_symlink():
                    continue
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                entries.append((p.relative_to(root).as_posix(), False, size))
            if scanned > MAX_SCAN:
                break
    except OSError:
        pass

    entries.sort(key=lambda e: (not e[1], e[0].count("/"), e[0].lower()))
    _index_cache[key] = (now, entries)
    return entries


def _walk(root: Path) -> Iterator[Tuple[str, list, list]]:
    """os.walk dengan pemangkasan folder besar (dipakai iter_mentions)."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_NAMES]
        depth = 0 if dirpath == str(root) else Path(dirpath).relative_to(root).as_posix().count("/") + 1
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        yield dirpath, dirnames, filenames
