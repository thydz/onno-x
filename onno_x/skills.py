import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import httpx
from pydantic import BaseModel
from onno_x.config import CONFIG_DIR

GLOBAL_SKILLS_DIR = CONFIG_DIR / "skills"
PACKAGE_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
MARKETPLACES_FILE = CONFIG_DIR / "marketplaces.json"


def local_dot_skills_dir() -> Path:
    """Project-local skills dir, resolved on every call.

    These used to be module constants built from `Path.cwd()` at import time, so
    after `/cd` the CLI kept reading and writing skills in the startup directory.
    """
    return Path.cwd() / ".onno-x" / "skills"


def repo_skills_dir() -> Path:
    return Path.cwd() / "skills"


def invalidate_skills_cache() -> None:
    """Drop the discovery cache so cwd-dependent sources are rescanned."""
    global _SKILLS_CACHE
    _SKILLS_CACHE = None


class Skill(BaseModel):
    name: str
    description: str
    content: str
    scope: str = "global"  # "global", "repo", "local", "builtin", "plugin"
    path: str = ""


def ensure_skills_dir() -> None:
    GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


_SKILL_NAME_MAX = 64


def sanitize_skill_name(name: str) -> Optional[str]:
    """Return a safe skill name, or None if it could escape the skills dir.

    Skill names become filenames (`<name>.md`) and folder names. The name can
    come from a remote SKILL.md frontmatter (`/skill install <url>`), so it must
    never be able to traverse out of the skills directory.
    """
    if not isinstance(name, str):
        return None
    cleaned = name.strip()
    if not cleaned or len(cleaned) > _SKILL_NAME_MAX:
        return None
    if cleaned.startswith(".") or cleaned in (".", ".."):
        return None
    if "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        return None
    if Path(cleaned).name != cleaned:
        return None
    return cleaned


def load_marketplaces() -> Dict[str, str]:
    ensure_skills_dir()
    if not MARKETPLACES_FILE.exists():
        default_mp = {
            "DietrichGebert/ponytail": "https://github.com/DietrichGebert/ponytail",
            "ponytail": "https://github.com/DietrichGebert/ponytail",
            "anthropics/claude-code": "https://github.com/anthropics/claude-code",
        }
        MARKETPLACES_FILE.write_text(json.dumps(default_mp, indent=2), encoding="utf-8")
        return default_mp
    try:
        return json.loads(MARKETPLACES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_marketplaces(data: Dict[str, str]) -> None:
    ensure_skills_dir()
    MARKETPLACES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def parse_skill_file(path: Path, scope: str = "global") -> Optional[Skill]:
    if not path.is_file() or not path.name.endswith(".md"):
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    name = path.parent.name if path.name in ("SKILL.md", "README.md", "skill.md") else path.stem
    desc = "Custom user skill"

    # Extract YAML frontmatter if present
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            for line in frontmatter.splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split("name:", 1)[1].strip().strip('"\'')
                elif line.startswith("description:"):
                    desc = line.split("description:", 1)[1].strip().strip('"\'')

    # Fallback to heading extraction
    if desc == "Custom user skill":
        for line in text.splitlines()[:10]:
            line = line.strip()
            if line.startswith("# "):
                desc = line[2:].strip()
                break
            elif line.lower().startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break

    # Frontmatter names are untrusted: fall back to the file/dir name, then skip.
    safe_name = sanitize_skill_name(name)
    if not safe_name:
        safe_name = sanitize_skill_name(path.stem) or sanitize_skill_name(path.parent.name)
    if not safe_name:
        return None
    name = safe_name

    return Skill(
        name=name,
        description=desc,
        content=text,
        scope=scope,
        path=str(path),
    )


def scan_dir_for_skills(directory: Path, scope: str) -> Dict[str, Skill]:
    results: Dict[str, Skill] = {}
    if not directory.exists() or not directory.is_dir():
        return results

    # 1. Look for *.md files directly in directory
    for p in directory.glob("*.md"):
        s = parse_skill_file(p, scope)
        if s:
            results[s.name] = s

    # 2. Look for subfolders containing SKILL.md, README.md, or *.md
    for sub in directory.iterdir():
        if sub.is_dir() and not sub.name.startswith("."):
            skill_target = None
            for candidate in ["SKILL.md", "skill.md", "README.md", f"{sub.name}.md"]:
                target = sub / candidate
                if target.exists():
                    skill_target = target
                    break
            if not skill_target:
                md_files = list(sub.glob("*.md"))
                if md_files:
                    skill_target = md_files[0]

            if skill_target:
                s = parse_skill_file(skill_target, scope)
                if s:
                    results[s.name] = s

    return results


_SKILLS_CACHE: Optional[Dict[str, Skill]] = None


def list_skills(force_reload: bool = False) -> Dict[str, Skill]:
    global _SKILLS_CACHE
    if _SKILLS_CACHE is not None and not force_reload:
        return _SKILLS_CACHE

    ensure_skills_dir()
    skills: Dict[str, Skill] = {}

    # 1. Built-in package skills
    if PACKAGE_SKILLS_DIR.exists():
        skills.update(scan_dir_for_skills(PACKAGE_SKILLS_DIR, "builtin"))

    # 2. Global user skills (~/.onno-x/skills/)
    skills.update(scan_dir_for_skills(GLOBAL_SKILLS_DIR, "global"))

    # 3. Current workspace repo skills (./skills/)
    repo_dir = repo_skills_dir()
    if repo_dir.exists() and repo_dir.resolve() != PACKAGE_SKILLS_DIR.resolve():
        skills.update(scan_dir_for_skills(repo_dir, "repo"))

    # 4. Local project override (.onno-x/skills/)
    local_dir = local_dot_skills_dir()
    if local_dir.exists():
        skills.update(scan_dir_for_skills(local_dir, "local"))

    _SKILLS_CACHE = skills
    return skills


def add_skill(name: str, content: str, description: Optional[str] = None, local: bool = False) -> Path:
    global _SKILLS_CACHE
    safe_name = sanitize_skill_name(name)
    if not safe_name:
        raise ValueError(f"Invalid skill name: {name!r}")
    _SKILLS_CACHE = None
    target_dir = local_dot_skills_dir() if local else GLOBAL_SKILLS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{safe_name}.md"

    header = ""
    if description:
        header = f"# {description}\n\n"
    elif not content.startswith("#"):
        header = f"# Skill: {safe_name}\n\n"

    target_file.write_text(f"{header}{content.strip()}\n", encoding="utf-8")
    return target_file


def delete_skill(name: str) -> bool:
    global _SKILLS_CACHE
    safe_name = sanitize_skill_name(name)
    if not safe_name:
        return False
    _SKILLS_CACHE = None
    removed = False
    for base in [GLOBAL_SKILLS_DIR, local_dot_skills_dir(), repo_skills_dir()]:
        g_file = base / f"{safe_name}.md"
        g_folder = base / safe_name
        if g_file.exists():
            g_file.unlink()
            removed = True
        if g_folder.exists() and g_folder.is_dir():
            shutil.rmtree(g_folder)
            removed = True
    return removed


def import_skills_from_dir(src: Path, target_global: bool = True) -> int:
    target_dir = GLOBAL_SKILLS_DIR if target_global else local_dot_skills_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    scanned = scan_dir_for_skills(src, "import")
    count = 0
    for name, skill in scanned.items():
        safe_name = sanitize_skill_name(name)
        if not safe_name:
            continue
        dest = target_dir / f"{safe_name}.md"
        dest.write_text(skill.content, encoding="utf-8")
        count += 1
    return count


def resolve_package_spec(target: str) -> List[str]:
    """Resolve a target like 'ponytail@ponytail', 'owner/repo', or 'https://...' into candidate download URLs."""
    clean = target.strip()
    mps = load_marketplaces()

    # 1. If exact key in marketplaces
    if clean in mps:
        clean = mps[clean]

    # 2. If 'package@marketplace'
    if "@" in clean and not clean.startswith("http://") and not clean.startswith("https://"):
        pkg, mp_name = clean.split("@", 1)
        mp_base = mps.get(mp_name)
        if not mp_base:
            # Check if marketplace matches by short name
            for k, v in mps.items():
                if k.split("/")[-1].lower() == mp_name.lower():
                    mp_base = v
                    break
        if not mp_base and "/" in mp_name:
            mp_base = f"https://github.com/{mp_name}"
        if not mp_base:
            mp_base = f"https://github.com/{mp_name}/{pkg}"

        clean = mp_base

    # 3. If 'owner/repo'
    if not clean.startswith("http://") and not clean.startswith("https://"):
        if "/" in clean:
            clean = f"https://github.com/{clean}"
        else:
            # Look up alias in marketplaces
            matched = None
            for k, v in mps.items():
                if k.split("/")[-1].lower() == clean.lower() or k.lower() == clean.lower():
                    matched = v
                    break
            clean = matched or f"https://github.com/{clean}/{clean}"

    candidates = []

    # If raw URL directly
    if "raw.githubusercontent.com" in clean:
        return [clean]

    # If GitHub blob URL
    if "github.com" in clean and "/blob/" in clean:
        raw = clean.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        return [raw]

    # If GitHub tree URL
    if "github.com" in clean and "/tree/" in clean:
        base_raw = clean.replace("github.com", "raw.githubusercontent.com").replace("/tree/", "/")
        for filename in ["SKILL.md", "skill.md", "README.md", "prompt.md"]:
            candidates.append(f"{base_raw.rstrip('/')}/{filename}")
        return candidates

    # If GitHub repo root URL (e.g. https://github.com/DietrichGebert/ponytail)
    if "github.com" in clean:
        repo_path = clean.split("github.com/", 1)[1].strip("/ ")
        # Strip tree/main if leftover
        if "/tree/" in repo_path:
            repo_path = repo_path.split("/tree/")[0]

        for branch in ["main", "master"]:
            for folder in ["", "skills/", "skills/ponytail/", ".claude/skills/", "plugin/"]:
                for filename in ["SKILL.md", "skill.md", "README.md", "prompt.md"]:
                    candidates.append(f"https://raw.githubusercontent.com/{repo_path}/{branch}/{folder}{filename}")
        return candidates

    candidates.append(clean)
    return candidates


def fetch_skill_from_url(url: str) -> Skill:
    candidate_urls = resolve_package_spec(url)
    last_err = None
    text = ""
    success_url = ""

    headers = {
        "User-Agent": "onno-x-cli/0.1.0"
    }

    with httpx.Client(follow_redirects=True, timeout=15.0, headers=headers) as client:
        for candidate in candidate_urls:
            try:
                resp = client.get(candidate)
                if resp.status_code == 200 and resp.text.strip():
                    text = resp.text
                    success_url = candidate
                    break
                else:
                    last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = str(e)

    if not text:
        raise RuntimeError(f"Failed to fetch skill from {url} ({last_err or 'No accessible skill file found'})")

    path_obj = Path(success_url.split("?")[0])
    derived_name = path_obj.stem
    if derived_name.lower() in ("skill", "readme", "prompt"):
        derived_name = path_obj.parent.name
        if derived_name in ("main", "master", "", "skills"):
            derived_name = url.strip("/").split("/")[-1].split("@")[0]

    desc = f"Imported from {url}"
    name = derived_name

    # Check YAML frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split("name:", 1)[1].strip().strip('"\'')
                elif line.startswith("description:"):
                    desc = line.split("description:", 1)[1].strip().strip('"\'')

    # Fallback description to heading
    if desc.startswith("Imported from"):
        for line in text.splitlines()[:10]:
            line = line.strip()
            if line.startswith("# "):
                desc = line[2:].strip()
                break

    safe_name = sanitize_skill_name(name)
    if not safe_name:
        safe_name = sanitize_skill_name(derived_name) or "imported-skill"

    return Skill(
        name=safe_name,
        description=desc,
        content=text,
        scope="plugin",
        path=url,
    )
