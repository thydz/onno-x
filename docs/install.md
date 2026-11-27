# Installing onno-x with `curl | bash`

Yes — you do **not** need PyPI, a VPS, npm, or root. **GitHub + Firebase
Hosting is enough.** Firebase only serves one static file (`install.sh`); the
actual code is pulled from your **GitHub** repo. 

End result, like Claude Code:

```bash
curl -fsSL https://onno-x.web.app/install.sh | bash
```

(or `https://YOUR-CUSTOM-DOMAIN/install.sh`, or `https://raw.githubusercontent.com/sapasaja/onno-x/main/install.sh`)

## What the installer needs on the machine running it
- **Python 3.10+** (`python3`) — `onno-x` is a Python package.
- **git** — `pip install git+https://github.com/sapasaja/onno-x.git`.
- network access to **GitHub** + **PyPI** (pip needs PyPI for `hatchling`, `typer`, `rich`, `pydantic`, `httpx`, `prompt-toolkit`, `textual`, `openai`).
- `curl` or `wget` + `bash`. **macOS / Linux.** (Windows: use WSL.)

No PyPI account is required to *install*; publishing to PyPI is optional.

## What it does
1. Finds a `python3.10+` (`python3.13/3.12/3.11/3.10/python3`, or `$PYTHON_BIN`).
2. Creates an isolated venv at `~/.local/share/onno-x/venv`.
3. `pip install --force-reinstall --upgrade git+https://github.com/sapasaja/onno-x.git@main`.
4. Symlinks `onno-x` → `~/.local/bin/onno-x`. 
5. Tells you to add `export PATH="$HOME/.local/bin:$PATH"`.

## Step 1 — GitHub
Push this repo to a **public** GitHub repo (the remote here is already
`https://github.com/sapasaja/onno-x.git`, branch `main`):

```bash
git add .
git commit -m "..."
git push origin main
```

If your repo is **private**, `git+https://...` needs a token
(`git+https://USER:TOKEN@github.com/OWNER/REPO.git`), or build a **GitHub
Release** wheel and set `ONNOX_SOURCE=<wheel-url>`. Public is simplest.

## Step 2 — Firebase Hosting
This repo already has `firebase.json` + `public/install.sh` + `.firebaserc`.

1. `npm i -g firebase-tools` (or `npx firebase-tools`).
2. `firebase login`.
3. Set the real project id in `.firebaserc`:
   ```json
   { "projects": { "default": "onno-x" } }
   ```
4. Keep `public/install.sh` in sync with root `install.sh` (CI does it; locally
   `cp install.sh public/install.sh`).
5. `firebase deploy --only hosting`.
6. Test: `curl -fsSL https://onno-x.web.app/install.sh | bash`.

### Optional CI
`.github/workflows/deploy-installer.yml` syncs `install.sh` → `public/`, runs
`bash -n`, and deploys to Firebase on push to `main`. Set repo secrets:
`FIREBASE_SERVICE_ACCOUNT` + `FIREBASE_PROJECT_ID`. 

## Just GitHub (no Firebase)
You don't even need Firebase:
```bash
curl -fsSL https://raw.githubusercontent.com/sapasaja/onno-x/main/install.sh | bash
```

## After install
```bash
export PATH="$HOME/.local/bin:$PATH"
onno-x            # Textual TUI (default)
onno-x --cli      # classic readline REPL
onno-x -p "audit" # one-shot
onno-x --help
```
Configure a model in `~/.onno-x/config.json`; see `README.md`. 
(e.g. `onno-x model add ...`, `/model`, `/steps`, `/autocompact`, `/mode`.)

## Overrides (env)
```bash
ONNOX_REPO=sapasaja/onno-x \
ONNOX_REF=main \
ONNOX_INSTALL_DIR=$HOME/.onno-x \
ONNOX_BIN_DIR=$HOME/bin \
PYTHON_BIN=python3.11 \
curl -fsSL https://onno-x.web.app/install.sh | bash
```
`ONNOX_SOURCE=/path/to/checkout` or `ONNOX_SOURCE=https://.../onno_x-*.whl`
installs from local/artifact instead of GitHub. 

## Uninstall
```bash
rm -f ~/.local/bin/onno-x
rm -rf ~/.local/share/onno-x
# keep your data: ~/.onno-x  and project .onno-x/
```

## Notes
- `curl | bash` executes remote code; the script is short and readable. Use a
  tagged `ONNOX_REF=v0.1.0` for reproducibility, or download + inspect first.
- Re-running upgrades in place. No `sudo`.
- **Claude-style install ≠ binary.** onno-x ships a Python `onno-x` console
  script (`onno_x.main:app`, hatchling); the script creates a venv + symlink,
  not a self-contained binary. 
