# onno-x

**Multi-model coding agent CLI** . No hardcoded
model, no private IP, no shipped API key / MCP secret. You add your own model;
your local data stays in `~/.onno-x` / `.onno-x`.

- **Multi-model**: local LLM (Ollama, vLLM, LM Studio, OpenAI-compatible) + remote
  (Anthropic, OpenAI, …). `provider` `openai` / `anthropic` / `ollama`.
- **Autonomous tools**: read, write, edit, delete, list, grep, shell, web fetch/search,
  skills, `ask_user`, optional MCP.
- **Live streaming**, `Ctrl+C`/ESC interrupt, auto-compact, **disk-level `/rewind`**,
  `/undo`, checkpoints.
- **3-mode permissions**: `auto` / `manual` / `all`, `Shift+Tab`, `[y/N/a]`.
- **3 UIs**: default **Textual TUI**, `--cli` classic REPL, `web`/`serve`. 

---

## Install

**No PyPI, no VPS, no root.** GitHub + Firebase Hosting (or raw GitHub).
Needs **Python 3.10+**, **git**, network to GitHub + PyPI, `curl`/`wget` + `bash`.
macOS/Linux (Windows → WSL).

```bash
curl -fsSL https://onno-x.web.app/install.sh | bash
# raw GitHub (no Firebase):
curl -fsSL https://raw.githubusercontent.com/sapasaja/onno-x/main/install.sh | bash

export PATH="$HOME/.local/bin:$PATH"
onno-x
```

- Script `install.sh`; Firebase serves `public/install.sh` (`firebase.json`).
- private venv `~/.local/share/onno-x/venv`; symlink `~/.local/bin/onno-x`.
- source `git+https://github.com/sapasaja/onno-x.git@main`.
- `ONNOX_REPO`, `ONNOX_REF`, `ONNOX_SOURCE`, `ONNOX_INSTALL_DIR`,
  `ONNOX_BIN_DIR`, `PYTHON_BIN`. Details `docs/install.md`.
- **`curl|bash` runs remote code; repo must be public + clean. No secrets.**

### Manual

```bash
git clone https://github.com/sapasaja/onno-x.git
cd onno-x
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
onno-x
```

### New GitHub repo (sapasaja/onno-x)

```bash
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/sapasaja/onno-x.git
git push -u origin main
```

(If `origin` already exists: `git remote set-url origin https://github.com/sapasaja/onno-x.git`.)

### Firebase Hosting

```bash
firebase login
# .firebaserc projectId: your Firebase project
firebase deploy --only hosting --project <your-firebase-project>
# serves public/install.sh at https://<project>.web.app/install.sh
```

### Firebase CLI install (alternative)

```bash
npm i -g firebase-tools
npx firebase-tools@latest login
firebase use <your-firebase-project>
```

---

## Add a model (no shipped model)

Nothing is pre-configured. Create `~/.onno-x/config.json` or:

```bash
onno-x model add my-model \
  --provider openai \
  --id <model-id> \
  --url <api-base-url> \
  --key <api-key>          # omit for local models

onno-x model add claude --provider anthropic --id <claude-model-id> --key <key>
onno-x model add local --provider ollama --id llama3.1 --url http://127.0.0.1:11434
onno-x model list
onno-x model use my-model
```

`api_key` stays in your local `~/.onno-x/config.json` (`0600`, atomic).
Provider keys `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`. No `api_key` is committed.
Provider URLs are yours; **no private IP / MCP IP shipped.** 

---

## Usage

```bash
onno-x                 # Textual TUI (default)
onno-x tui             # explicit TUI
onno-x --cli           # classic readline REPL
onno-x -p "audit"      # one-shot
onno-x web             # Firebase-unrelated: local web UI (127.0.0.1)
onno-x model ...       # model registry
onno-x skill ...       # skills
onno-x --help
```

Slash commands `/help`, `/model`, `/models`, `/steps`, `/autocompact`,
`/mode`, `/permissions`, `/rewind`, `/undo`, `/snapshot`, `/restore`, `/compact`,
`/todo`, `/grep`, `/find`, `/test`, `/lint`, `/mcp`, `/save`, `/resume`, `/exit`. See `menu.md`.

---

## Optional MCP (no hardcoded IP/secret)

No `.mcp.json` is shipped. Copy `.mcp.json.example` → `.mcp.json` (gitignored)
and fill your own `command`/`args`/`env`. Looked up in `cwd` + `~/.onno-x/mcp.json`.
`.mcp.json` + `mcp.json` are gitignored. No HexStrike / Kali / private IP baked in.

---

## Sensitive data

- **Nothing sensitive is shipped.** No model, no `onno-ai`, no HexStrike, no MCP IP,
  no `kali@`, no private `192.168…`/`10…`/`127…`, no `api_key`, `apiKey`, `password`,
  secret, token. 
- `.gitignore` `.env`, `.env.*`, `*.pem`, `*.key`, `.mcp.json`, `opencode.json`,
  `.onno-x/`, `error.txt`, `.firebaserc`. 
- `~/.onno-x/config.json` `0600`; sessions `write_json_atomic 0600`.
- `_escape_markup` is **Rich safety**, not secret redaction. Don't commit secrets.

---

## Develop

```bash
python -m unittest discover -s tests
python -m compileall onno_x
```

`onno_x` (`typer` app `onno_x.main:app`), `hatchling`. `requires-python >=3.10`. 138 tests.

### Installer files

`install.sh`, `public/install.sh`, `firebase.json`, `.firebaserc`,
`.github/workflows/deploy-installer.yml`, `docs/install.md`.
