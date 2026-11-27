#!/usr/bin/env bash
# onno-x installer — curl -fsSL https://<your-firebase-host>/install.sh | bash
#
# Requires: Python 3.10+, git, network access to GitHub + PyPI.
# No PyPI publish, no VPS, no root. Installs into a private venv and links
# `onno-x` into ~/.local/bin (or $ONNOX_BIN_DIR).
#
# Env overrides:
#   ONNOX_REPO=sapasaja/onno-x     GitHub owner/repo (default)
#   ONNOX_REF=main                 git ref/branch/tag to install (default: main)
#   ONNOX_SOURCE=...               full pip source; overrides REPO/REF
#                                  (e.g. /path/to/local/checkout, or a wheel URL)
#   ONNOX_INSTALL_DIR=...          venv location (default: ~/.local/share/onno-x)
#   ONNOX_BIN_DIR=...              where `onno-x` symlink goes (default: ~/.local/bin)
#   PYTHON_BIN=python3.11          force a Python interpreter
set -euo pipefail

ONNOX_REPO="${ONNOX_REPO:-sapasaja/onno-x}"
ONNOX_REF="${ONNOX_REF:-main}"
ONNOX_SOURCE="${ONNOX_SOURCE:-git+https://github.com/${ONNOX_REPO}.git@${ONNOX_REF}}"
ONNOX_INSTALL_DIR="${ONNOX_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/onno-x}"
ONNOX_BIN_DIR="${ONNOX_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
PYTHON_BIN="${PYTHON_BIN:-}"

say() { printf '%s\n' "$*"; }
err() { printf 'onno-x install: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

# ---- pick a Python 3.10+ interpreter -------------------------------------
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
[ -n "$PYTHON_BIN" ] || die "Python 3.10+ not found. Install Python and re-run."
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python not found: $PYTHON_BIN"

"$PYTHON_BIN" - <<'PY' || die "Python 3.10+ required."
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ required, found " + sys.version.split()[0])
PY

command -v git >/dev/null 2>&1 || die "git not found. Install git and re-run."

# ---- isolated venv -------------------------------------------------------
VENV_DIR="$ONNOX_INSTALL_DIR/venv"
mkdir -p "$ONNOX_INSTALL_DIR" "$ONNOX_BIN_DIR"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  say "→ creating virtualenv: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

say "→ upgrading pip"
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null

say "→ installing onno-x from: $ONNOX_SOURCE"
"$VENV_DIR/bin/python" -m pip install --force-reinstall --upgrade "$ONNOX_SOURCE"

# ---- link the console script --------------------------------------------
[ -x "$VENV_DIR/bin/onno-x" ] || die "install finished but no onno-x script in $VENV_DIR/bin"
ln -sf "$VENV_DIR/bin/onno-x" "$ONNOX_BIN_DIR/onno-x"
chmod +x "$ONNOX_BIN_DIR/onno-x"

say ""
say "✓ onno-x installed."
say "  binary : $ONNOX_BIN_DIR/onno-x"
say "  venv   : $VENV_DIR"
say ""

case ":$PATH:" in
  *":$ONNOX_BIN_DIR:"*)
    say "$ONNOX_BIN_DIR is already on PATH. Run: onno-x"
    ;;
  *)
    say "Add this to your shell rc (~/.zshrc / ~/.bashrc), then restart the shell:"
    say "  export PATH=\"$ONNOX_BIN_DIR:\$PATH\""
    say ""
    say "Then run: onno-x   (or: $ONNOX_BIN_DIR/onno-x)"
    ;;
esac

say ""
say "Next: configure a model in ~/.onno-x/config.json, e.g. /model or onno-x model add."
say "Docs: https://github.com/${ONNOX_REPO}"
