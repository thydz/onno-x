from typing import Any, Callable, Dict
from onno_x.tools.shell import run_shell
from onno_x.tools.fs import read_file, write_file, edit_file, delete_file, list_dir, grep_search
from onno_x.tools.web import fetch_url, web_search
from onno_x.tools.skills_tool import load_skill, search_skills
from onno_x.tools.obsidian import obsidian_search_notes, obsidian_read_note, obsidian_write_note

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Execute a bash shell command in the local environment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents with line numbers. Use offset and max_lines to page through large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute file path"},
                    "offset": {"type": "integer", "description": "1-based line number to start reading from", "default": 1},
                    "max_lines": {"type": "integer", "description": "Max lines to read per call", "default": 150},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a new file or completely overwrite an existing file with content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "content": {"type": "string", "description": "Full file contents"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Performs exact string replacement in a file (preferred for precise edits without rewriting whole file).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to modify"},
                    "old_string": {"type": "string", "description": "Exact text snippet to replace"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory permanently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file or folder to remove"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and subdirectories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search regex pattern across files in project (code search like grep/ripgrep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or keyword to search for"},
                    "path": {"type": "string", "description": "Root folder to search", "default": "."},
                    "file_pattern": {"type": "string", "description": "Glob filter (e.g. '*.py')", "default": "*"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch webpage or API text via HTTP GET (web browsing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP/HTTPS URL to read"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live internet for recent documentation, errors, or information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search terms"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Search available specialized skills by keyword (e.g. 'audit', 'azure', 'git', 'fix').",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search skills for", "default": ""}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "Load a specialized skill prompt or workflow by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Name of the skill to load"}
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user an interactive question, clarification, or multiple choice when you need user input before continuing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask the user"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of predefined choices/options for the user to select from",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_search_notes",
            "description": "Search long-term memory notes, pentest reports, and knowledge in Obsidian (192.168.100.102:2233).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword or concept to search for in Obsidian memory"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_read_note",
            "description": "Read the full markdown content of a specific note from Obsidian memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_name": {"type": "string", "description": "Filename or path of the note to read (e.g. 'bugbounty-onnoai.md')"}
                },
                "required": ["note_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_write_note",
            "description": "Save or update a persistent note into Obsidian memory on 192.168.100.102.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the note"},
                    "content": {"type": "string", "description": "Markdown body content"},
                    "folder": {"type": "string", "description": "Subfolder name (e.g. 'Knowledge' or 'Tasks')", "default": "Knowledge"},
                },
                "required": ["title", "content"],
            },
        },
    },
]

def ask_user(question: str, options: list = None) -> str:
    """Prompt the user with an interactive question or choice during turn execution."""
    from onno_x.ui import console
    console.print(f"\n[bold magenta]❓ Question from onno-x:[/bold magenta] [bold white]{question}[/bold white]")
    if options:
        for idx, opt in enumerate(options, 1):
            console.print(f"   [cyan]{idx})[/cyan] {opt}")
        prompt_text = f"[bold yellow]Your choice (1-{len(options)}) or custom response: [/bold yellow]"
    else:
        prompt_text = "[bold yellow]Your answer: [/bold yellow]"

    try:
        ans = console.input(prompt_text).strip()
        if options and ans.isdigit():
            idx = int(ans) - 1
            if 0 <= idx < len(options):
                ans = options[idx]
        return ans or "(no answer provided)"
    except (EOFError, KeyboardInterrupt):
        return "(user skipped question)"


TOOL_RUNNERS: Dict[str, Callable[..., str]] = {
    "run_shell": run_shell,
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "delete_file": delete_file,
    "list_dir": list_dir,
    "grep_search": grep_search,
    "fetch_url": fetch_url,
    "web_search": web_search,
    "search_skills": search_skills,
    "load_skill": load_skill,
    "ask_user": ask_user,
    "obsidian_search_notes": obsidian_search_notes,
    "obsidian_read_note": obsidian_read_note,
    "obsidian_write_note": obsidian_write_note,
}

# Dangerous shell commands that should always prompt in Auto mode
DANGEROUS_SHELL_PATTERNS = [
    "rm ", "rmdir", "delete", "unlink", "git reset", "git clean", "git checkout -f",
    "drop database", "mkfs", "> /dev/", "chmod 777", "chmod -R", "chown", "pkill", "killall"
]

SAFE_READ_TOOLS = {
    "read_file",
    "list_dir",
    "grep_search",
    "fetch_url",
    "web_search",
    "search_skills",
    "load_skill",
    "ask_user",
    "obsidian_search_notes",
    "obsidian_read_note",
    "mcp__hexstrike__search_tools",
    "mcp__api-anything__find_sites",
    "mcp__api-anything__list_sites",
    "mcp__api-anything__list_operations",
    "mcp__api-anything__site_status",
}


def should_prompt_permission(tool_name: str, args: dict, permission_mode: str = "auto") -> bool:
    """Determine if a tool execution requires user confirmation based on permission mode."""
    mode = (permission_mode or "auto").lower().strip()
    # 1. 'all' / 'accept-all' / 'yolo' mode: 100% direct execution, never prompt
    if mode in ("all", "accept-all", "accept_all", "yolo"):
        return False

    # 2. 'manual' mode: prompt for everything except safe read tools
    if mode == "manual":
        return tool_name not in SAFE_READ_TOOLS

    # 3. 'auto' mode (Default):
    # Safe read tools: never prompt
    if tool_name in SAFE_READ_TOOLS or "search_tools" in tool_name:
        return False

    # In auto mode, shell commands, file edits, and pentest tools execute DIRECTLY!
    # Only catastrophic destructive operations prompt:
    if tool_name == "delete_file":
        return True

    if tool_name == "run_shell":
        cmd = args.get("command", "").lower()
        if any(p in cmd for p in DANGEROUS_SHELL_PATTERNS):
            return True
        return False

    # All other tools execute directly in auto mode
    return False


def get_active_tool_definitions() -> list:
    """Return all built-in tools plus dynamically registered MCP tools."""
    from onno_x.mcp import MCPManager
    mcp_defs = MCPManager.get_instance().get_tool_definitions()
    return TOOL_DEFINITIONS + mcp_defs


def prompt_cli_permission_with_timeout(timeout: float = 60.0) -> str:
    """Prompt user for (y/n/a) with single keypress and timeout, ensuring terminal never freezes."""
    import sys, select, tty, termios

    prompt_str = "Allow execution? (y=yes / n=no / a=accept all / Enter=yes) [60s]: "
    sys.stdout.write(prompt_str)
    sys.stdout.flush()

    fd = None
    old_settings = None
    try:
        if sys.stdin.isatty():
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)
            if not rlist:
                sys.stdout.write("\n\033[33m⚡ Permission timed out after 60s (auto-denied).\033[0m\n")
                sys.stdout.flush()
                return "n"
            ch = sys.stdin.read(1)
            sys.stdout.write(ch + "\n")
            sys.stdout.flush()
            if ch in ("\r", "\n", "y", "Y"):
                return "y"
            elif ch in ("a", "A"):
                return "a"
            else:
                return "n"
        else:
            line = sys.stdin.readline().strip().lower()
            return line if line else "y"
    except Exception:
        return "n"
    finally:
        if fd is not None and old_settings is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass


def execute_tool(name: str, args: dict, permission_mode: str = "auto", session=None) -> str:
    from onno_x.mcp import MCPManager
    runner = TOOL_RUNNERS.get(name)

    # Check if runner is missing and not an MCP tool
    is_mcp = name.startswith("mcp__")
    if not runner and not is_mcp:
        return f"Error: Unknown tool {name}"

    effective_mode = getattr(session, "permission_mode", permission_mode)

    if should_prompt_permission(name, args, effective_mode):
        from onno_x.ui import console

        handler = getattr(session, "permission_handler", None)
        if handler:
            choice = handler(name, args, effective_mode)
        else:
            console.print(f"\n[bold yellow]⚡ Permission Request ({effective_mode.upper()} mode):[/bold yellow]")
            if name == "run_shell":
                console.print(f"   Command: [bold cyan]{args.get('command')}[/bold cyan]")
            elif name in ("write_file", "edit_file"):
                console.print(f"   Action:  [bold yellow]{name}[/bold yellow] on [bold cyan]{args.get('path')}[/bold cyan]")
            elif name == "delete_file":
                console.print(f"   Action:  [bold red]Permanently delete[/bold red] [bold white]{args.get('path')}[/bold white]")
            elif is_mcp:
                console.print(f"   Action:  [bold magenta]MCP Tool Execution[/bold magenta] [bold cyan]{name}[/bold cyan]")
                console.print(f"   Args:    {args}")
            else:
                console.print(f"   Tool:    [cyan]{name}[/cyan] ({args})")

            choice = prompt_cli_permission_with_timeout(timeout=60.0)

        if choice in ("a", "all"):
            if session:
                session.permission_mode = "all"
            console.print("[bold green]✔ Switched to ACCEPT ALL mode for this session.[/bold green]")
        elif choice not in ("y", "yes", ""):
            return f"Tool '{name}' execution was denied by the user."

    if is_mcp:
        mcp_res = MCPManager.get_instance().execute_tool(name, args)
        if mcp_res is not None:
            return mcp_res
        return f"Error: MCP Tool '{name}' returned no response"

    try:
        return runner(**args)
    except Exception as e:
        return f"Error executing {name}: {str(e)}"
