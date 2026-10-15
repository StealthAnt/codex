"""Local KoDex MCP bridge for app launching, engineering tools, and task memory.

This server uses only Python's standard library. It communicates over stdio and
never opens a listening network port. Codex prompts before each tool call.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def kodex_home() -> Path:
    value = os.environ.get("CODEX_HOME")
    if value:
        return Path(value).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "KoDex" if local else Path.home() / ".kodex"


def task_file() -> Path:
    return kodex_home() / "tasks.json"


GITHUB_CATEGORIES = {
    "robotics": "topic:robotics",
    "engineering": "topic:engineering",
    "steam": "topic:steam",
    "competitions": "topic:competition",
    "competition_robots": "robot competition",
    "arduino": "topic:arduino",
    "cad": "topic:cad",
    "stl_cad": "STL CAD 3D-printable",
    "matlab": "topic:matlab",
    "ros": "topic:ros",
}

DESIGN_SUFFIXES = {".stl", ".step", ".stp", ".fcstd", ".scad", ".obj", ".3mf", ".iges", ".igs"}


def github_resource_search(category: str, query: str = "", limit: int = 10, sort: str = "stars") -> dict[str, Any]:
    """Search public GitHub repositories. Does not authenticate or access private repos."""
    if category not in GITHUB_CATEGORIES:
        raise ValueError("Choose a category: robotics, engineering, steam, competitions, competition_robots, arduino, cad, stl_cad, matlab, or ros.")
    if len(query) > 120 or any(ord(char) < 32 for char in query):
        raise ValueError("Search text must be at most 120 printable characters.")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20.")
    if sort not in {"stars", "updated"}:
        raise ValueError("sort must be stars or updated.")
    terms = f"{GITHUB_CATEGORIES[category]} is:public archived:false"
    if query.strip():
        terms = f"{query.strip()} {terms}"
    cache_path = kodex_home() / "github_resource_cache.json"
    cache_key = json.dumps([category, query.strip(), limit, sort], ensure_ascii=False)
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cached = {}
    if not isinstance(cached, dict):
        cached = {}
    cached_item = cached.get(cache_key) if isinstance(cached, dict) else None
    if isinstance(cached_item, dict) and time.time() - cached_item.get("saved_at", 0) < 900:
        return {**cached_item["data"], "cached": True}

    params = urllib.parse.urlencode({"q": terms, "sort": sort, "order": "desc", "per_page": limit})
    request = urllib.request.Request(
        "https://api.github.com/search/repositories?" + params,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "KoDex-local-resource-finder", "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            remaining = response.headers.get("X-RateLimit-Remaining")
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 429}:
            reset = exc.headers.get("X-RateLimit-Reset")
            raise RuntimeError(f"GitHub search is rate-limited. Try again later (reset epoch: {reset or 'not provided'}).") from exc
        raise RuntimeError(f"GitHub repository search failed with HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach GitHub: {exc}.") from exc

    repos = []
    for item in payload.get("items", []):
        repos.append({
            "full_name": item.get("full_name"),
            "description": item.get("description"),
            "url": item.get("html_url"),
            "clone_url": item.get("clone_url"),
            "language": item.get("language"),
            "stars": item.get("stargazers_count", 0),
            "forks": item.get("forks_count", 0),
            "updated_at": item.get("pushed_at"),
            "topics": item.get("topics", []),
            "license": (item.get("license") or {}).get("spdx_id"),
            "archived": item.get("archived", False),
        })
    data = {
        "category": category,
        "query": query.strip(),
        "total_count": payload.get("total_count", 0),
        "repositories": repos,
        "rate_limit_remaining": int(remaining) if remaining and remaining.isdigit() else None,
        "cached": False,
        "note": "Public repository metadata only. Review a project's license, maintenance, and code before using it.",
    }
    cached[cache_key] = {"saved_at": time.time(), "data": data}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="github-search-", suffix=".tmp", dir=cache_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp:
            json.dump(cached, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
        os.replace(temp_name, cache_path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return data


def local_design_files(limit: int = 100) -> dict[str, Any]:
    """List common CAD/mesh files in KoDex resource clones; never opens or executes them."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500.")
    root = kodex_home() / "resources"
    files = []
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.casefold() in DESIGN_SUFFIXES:
                files.append({"name": path.name, "format": path.suffix, "path": str(path), "repository": str(path.relative_to(root).parts[0])})
                if len(files) >= limit:
                    break
    return {"resource_directory": str(root), "count": len(files), "files": files, "note": "Files are listed only; KoDex does not execute or open downloaded design files."}


def github_clone_public_repository(full_name: str) -> dict[str, Any]:
    """Clone one public GitHub repository into KoDex's dedicated resources directory."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", full_name.strip()):
        raise ValueError("Provide a GitHub repository as owner/name (not a URL).")
    if full_name.strip().startswith("-") or "/../" in full_name:
        raise ValueError("Invalid GitHub repository name.")
    git = shutil.which("git")
    if not git:
        raise ValueError("Git was not found on PATH.")
    owner, repo = full_name.strip().split("/", 1)
    destination = kodex_home() / "resources" / f"{owner}__{repo.removesuffix('.git')}"
    if destination.exists():
        raise ValueError(f"This resource already exists locally: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [git, "clone", "--depth", "1", "--", f"https://github.com/{owner}/{repo.removesuffix('.git')}.git", str(destination)],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("GitHub clone timed out after 10 minutes; partial checkout may need manual removal.") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout)[-5000:] or "Git clone failed.")
    design_files = []
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix.casefold() in DESIGN_SUFFIXES:
            design_files.append({"name": path.name, "format": path.suffix, "path": str(path.relative_to(destination))})
            if len(design_files) >= 100:
                break
    return {
        "repository": f"{owner}/{repo.removesuffix('.git')}",
        "local_path": str(destination),
        "design_file_count_in_first_100": len(design_files),
        "design_files": design_files,
        "note": "Cloned source and assets only. KoDex has not run project code; inspect the repository license and contents before use.",
    }


@contextmanager
def task_lock() -> Iterator[None]:
    """Serialize task edits across bridge and voice processes."""
    path = kodex_home() / "tasks.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt

            lock.seek(0)
            if lock.read(1) == b"":
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def load_tasks() -> list[dict[str, Any]]:
    path = task_file()
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    path = task_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="tasks-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp:
            json.dump(tasks, temp, ensure_ascii=False, indent=2)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def add_task(title: str) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("Task title must not be empty.")
    with task_lock():
        tasks = load_tasks()
        task = {
            "id": "KDX-" + uuid.uuid4().hex[:8].upper(),
            "title": title,
            "status": "open",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        tasks.append(task)
        save_tasks(tasks)
        return task


def list_tasks(include_done: bool = False) -> list[dict[str, Any]]:
    with task_lock():
        tasks = load_tasks()
    return tasks if include_done else [task for task in tasks if task.get("status") != "done"]


def complete_task(task_id: str) -> dict[str, Any]:
    with task_lock():
        tasks = load_tasks()
        for task in tasks:
            if task.get("id", "").casefold() == task_id.strip().casefold():
                task["status"] = "done"
                from datetime import datetime

                task["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                save_tasks(tasks)
                return task
    raise ValueError(f"No task found with ID {task_id!r}.")


def app_paths() -> dict[str, list[Path]]:
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    candidates: dict[str, list[Path]] = {
        "vscode": [
            local / "Programs" / "Microsoft VS Code" / "Code.exe",
            program_files / "Microsoft VS Code" / "Code.exe",
        ],
        "arduino_ide": [
            program_files / "Arduino IDE" / "Arduino IDE.exe",
            local / "Programs" / "Arduino IDE" / "Arduino IDE.exe",
        ],
        "freecad": [
            program_files / "FreeCAD 1.0" / "bin" / "FreeCAD.exe",
            program_files / "FreeCAD 1.1" / "bin" / "FreeCAD.exe",
            program_files / "FreeCAD 0.21" / "bin" / "FreeCAD.exe",
            program_files / "FreeCAD 1.0" / "FreeCAD.exe",
            program_files_x86 / "FreeCAD 0.21" / "bin" / "FreeCAD.exe",
        ],
        "matlab": [
            program_files / "MATLAB" / "R2026b" / "bin" / "matlab.exe",
            program_files / "MATLAB" / "R2026a" / "bin" / "matlab.exe",
            program_files / "MATLAB" / "R2025b" / "bin" / "matlab.exe",
            program_files / "MATLAB" / "R2025a" / "bin" / "matlab.exe",
        ],
    }
    return candidates


def find_app(name: str) -> Path | None:
    env_names = {
        "vscode": "KODEX_VSCODE_EXE",
        "arduino_ide": "KODEX_ARDUINO_IDE_EXE",
        "freecad": "KODEX_FREECAD_EXE",
        "matlab": "KODEX_MATLAB_EXE",
    }
    override = os.environ.get(env_names[name])
    if override and Path(override).is_file():
        return Path(override)
    for candidate in app_paths()[name]:
        if candidate.is_file():
            return candidate
    command_names = {
        "vscode": "code",
        "arduino_ide": "arduino-ide",
        "freecad": "freecad",
        "matlab": "matlab",
    }
    found = shutil.which(command_names[name])
    return Path(found) if found else None


def discover_apps() -> list[dict[str, Any]]:
    labels = {
        "vscode": "Visual Studio Code",
        "arduino_ide": "Arduino IDE",
        "freecad": "FreeCAD",
        "matlab": "MATLAB",
    }
    result = []
    for key, label in labels.items():
        exe = find_app(key)
        result.append({"id": key, "name": label, "installed": exe is not None, "executable": str(exe) if exe else None})
    arduino_cli = find_arduino_cli()
    result.append({"id": "arduino_cli", "name": "Arduino CLI", "installed": arduino_cli is not None, "executable": str(arduino_cli) if arduino_cli else None})
    return result


def windows_start_apps() -> list[dict[str, str]]:
    """Read the Windows Start menu app catalog without launching anything."""
    if os.name != "nt":
        return []
    script = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(entries, dict):
        entries = [entries]
    return [
        {"name": str(entry["Name"]), "app_id": str(entry["AppID"])}
        for entry in entries
        if isinstance(entry, dict) and entry.get("Name") and entry.get("AppID")
    ]


def open_start_app(name: str) -> dict[str, str]:
    """Open an app by exact display name from the current Start menu catalog."""
    matches = [entry for entry in windows_start_apps() if entry["name"].casefold() == name.strip().casefold()]
    if len(matches) != 1:
        raise ValueError("Choose an exact app name from kodex_apps_discover; the app must be registered in the Windows Start menu.")
    app_id = matches[0]["app_id"]
    subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id], close_fds=True)
    return {"opened": matches[0]["name"]}


def find_arduino_cli() -> Path | None:
    found = shutil.which("arduino-cli") or shutil.which("arduino-cli.exe")
    if found:
        return Path(found)
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        for candidate in downloads.glob("arduino-cli*/arduino-cli.exe"):
            return candidate
    return None


def launch_app(app: str, path: str | None = None) -> dict[str, str]:
    if app not in {"vscode", "arduino_ide", "freecad", "matlab"}:
        raise ValueError("Openable apps are vscode, arduino_ide, freecad, and matlab.")
    exe = find_app(app)
    if exe is None:
        raise ValueError(f"{app} was not found. Set its KODEX_*_EXE environment variable or install it first.")
    args = [str(exe)]
    if path:
        target = Path(path).expanduser().resolve(strict=True)
        if app == "arduino_ide" and target.is_dir() and not any(target.glob("*.ino")):
            raise ValueError("Arduino sketch folder must contain an .ino file.")
        args.append(str(target))
    subprocess.Popen(args, close_fds=True)
    return {"app": app, "opened": str(Path(path).expanduser().resolve()) if path else "application"}


def create_freecad_box(output_file: str, x: float, y: float, z: float) -> dict[str, str]:
    exe = find_app("freecad")
    if exe is None:
        raise ValueError("FreeCAD was not found. Install it or set KODEX_FREECAD_EXE.")
    if not all(0 < value <= 10000 for value in (x, y, z)):
        raise ValueError("Box dimensions must be greater than 0 and no more than 10000 mm.")
    destination = Path(output_file).expanduser().resolve()
    if destination.suffix.casefold() != ".fcstd":
        raise ValueError("The output filename must end in .FCStd.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    macro_dir = kodex_home() / "macros"
    macro_dir.mkdir(parents=True, exist_ok=True)
    macro = macro_dir / ("create_box_" + uuid.uuid4().hex + ".FCMacro")
    destination_literal = json.dumps(str(destination))
    macro.write_text(
        "import FreeCAD as App\n"
        "import Part\n"
        "doc = App.newDocument('KoDexBox')\n"
        f"shape = Part.makeBox({float(x)}, {float(y)}, {float(z)})\n"
        "obj = doc.addObject('PartDesign::Feature', 'Box')\n"
        "obj.Label = 'KoDex Box'\n"
        "obj.Shape = shape\n"
        "doc.recompute()\n"
        f"doc.saveAs({destination_literal})\n",
        encoding="utf-8",
    )
    subprocess.Popen([str(exe), str(macro)], close_fds=True)
    return {"created": str(destination), "macro": str(macro), "dimensions_mm": f"{x} x {y} x {z}"}


def arduino_compile(sketch_dir: str, fqbn: str) -> dict[str, Any]:
    cli = find_arduino_cli()
    if cli is None:
        raise ValueError("Arduino CLI was not found. Install it or add arduino-cli.exe to PATH.")
    sketch = Path(sketch_dir).expanduser().resolve(strict=True)
    if not sketch.is_dir() or not any(sketch.glob("*.ino")):
        raise ValueError("Sketch path must be a folder containing an .ino file.")
    if not fqbn.strip() or len(fqbn) > 200:
        raise ValueError("Provide a valid Arduino FQBN, such as arduino:avr:uno.")
    output = kodex_home() / "build" / uuid.uuid4().hex
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(cli), "compile", "--fqbn", fqbn.strip(), "--output-dir", str(output), str(sketch)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output_dir": str(output),
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-6000:],
        "upload_performed": False,
    }


def matlab_run(script_path: str, timeout_seconds: int = 300) -> dict[str, Any]:
    exe = find_app("matlab")
    if exe is None:
        raise ValueError("MATLAB was not found. Install it or set KODEX_MATLAB_EXE.")
    script = Path(script_path).expanduser().resolve(strict=True)
    if not script.is_file() or script.suffix.casefold() != ".m":
        raise ValueError("MATLAB script must be an existing .m file.")
    if timeout_seconds < 1 or timeout_seconds > 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600.")
    matlab_path = str(script).replace("'", "''")
    statement = f"run('{matlab_path}')"
    result = subprocess.run(
        [str(exe), "-batch", statement],
        cwd=str(script.parent),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout[-12000:],
        "stderr": result.stderr[-6000:],
        "script": str(script),
        "note": "Uses your installed MATLAB and its current MathWorks license/sign-in. No account credentials are read or stored by KoDex.",
    }


TOOLS: list[dict[str, Any]] = [
    {"name": "kodex_github_search_repositories", "description": "Search public GitHub repositories for robotics, engineering, STEAM, competition robot designs, STL/CAD, Arduino, MATLAB, or ROS projects. Read-only; results include stars, activity, topics, and license metadata.", "inputSchema": {"type": "object", "properties": {"category": {"type": "string", "enum": list(GITHUB_CATEGORIES)}, "query": {"type": "string", "maxLength": 120}, "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10}, "sort": {"type": "string", "enum": ["stars", "updated"], "default": "stars"}}, "required": ["category"], "additionalProperties": False}},
    {"name": "kodex_github_clone_public_repository", "description": "Clone one public GitHub repository by owner/name into KoDex's local resources folder. Clones files only; does not run code. Approval is required.", "inputSchema": {"type": "object", "properties": {"full_name": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"}}, "required": ["full_name"], "additionalProperties": False}},
    {"name": "kodex_resource_find_design_files", "description": "List STL, STEP, FreeCAD, OpenSCAD, OBJ, 3MF, and IGES files in cloned KoDex resources. Does not open or execute them.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}}, "additionalProperties": False}},
    {"name": "kodex_task_add", "description": "Save a task in KoDex's local task list.", "inputSchema": {"type": "object", "properties": {"title": {"type": "string", "minLength": 1}}, "required": ["title"], "additionalProperties": False}},
    {"name": "kodex_task_list", "description": "List open KoDex tasks, or include completed tasks.", "inputSchema": {"type": "object", "properties": {"include_done": {"type": "boolean", "default": False}}, "additionalProperties": False}},
    {"name": "kodex_task_complete", "description": "Mark a KoDex task complete by its KDX ID.", "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"], "additionalProperties": False}},
    {"name": "kodex_apps_discover", "description": "List supported engineering apps and the apps registered in this Windows user's Start menu. Discovery is read-only.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "kodex_app_open", "description": "Open VS Code, Arduino IDE, FreeCAD, or MATLAB, optionally with an existing project or document path.", "inputSchema": {"type": "object", "properties": {"app": {"type": "string", "enum": ["vscode", "arduino_ide", "freecad", "matlab"]}, "path": {"type": "string"}}, "required": ["app"], "additionalProperties": False}},
    {"name": "kodex_app_open_by_name", "description": "Open an installed app by exact display name from Windows Start menu discovery.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "minLength": 1}}, "required": ["name"], "additionalProperties": False}},
    {"name": "kodex_freecad_create_box", "description": "Create a box model as an FCStd document and open it in FreeCAD.", "inputSchema": {"type": "object", "properties": {"output_file": {"type": "string"}, "x": {"type": "number", "exclusiveMinimum": 0}, "y": {"type": "number", "exclusiveMinimum": 0}, "z": {"type": "number", "exclusiveMinimum": 0}}, "required": ["output_file", "x", "y", "z"], "additionalProperties": False}},
    {"name": "kodex_arduino_compile", "description": "Compile an existing Arduino sketch using Arduino CLI. This does not upload to a board.", "inputSchema": {"type": "object", "properties": {"sketch_dir": {"type": "string"}, "fqbn": {"type": "string"}}, "required": ["sketch_dir", "fqbn"], "additionalProperties": False}},
    {"name": "kodex_matlab_run", "description": "Run an existing .m script in installed MATLAB batch mode using your current local MathWorks license/session.", "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 3600, "default": 300}}, "required": ["script_path"], "additionalProperties": False}},
]


def call_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "kodex_github_search_repositories":
        return github_resource_search(args["category"], args.get("query", ""), int(args.get("limit", 10)), args.get("sort", "stars"))
    if name == "kodex_github_clone_public_repository":
        return github_clone_public_repository(args["full_name"])
    if name == "kodex_resource_find_design_files":
        return local_design_files(int(args.get("limit", 100)))
    if name == "kodex_task_add":
        return add_task(args["title"])
    if name == "kodex_task_list":
        return list_tasks(bool(args.get("include_done", False)))
    if name == "kodex_task_complete":
        return complete_task(args["task_id"])
    if name == "kodex_apps_discover":
        return {"integrations": discover_apps(), "start_menu_apps": windows_start_apps()}
    if name == "kodex_app_open":
        return launch_app(args["app"], args.get("path"))
    if name == "kodex_app_open_by_name":
        return open_start_app(args["name"])
    if name == "kodex_freecad_create_box":
        return create_freecad_box(args["output_file"], float(args["x"]), float(args["y"]), float(args["z"]))
    if name == "kodex_arduino_compile":
        return arduino_compile(args["sketch_dir"], args["fqbn"])
    if name == "kodex_matlab_run":
        return matlab_run(args["script_path"], int(args.get("timeout_seconds", 300)))
    raise ValueError(f"Unknown KoDex tool {name!r}.")


def mcp_server() -> None:
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                result: Any = {
                    "protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kodex-local-bridge", "version": "0.2.0"},
                }
            elif method == "notifications/initialized" or (isinstance(method, str) and method.startswith("notifications/")):
                continue
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    value = call_tool(params.get("name", ""), params.get("arguments", {}))
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": False}
                except Exception as exc:  # Return tool errors as MCP tool results.
                    result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            else:
                if request_id is None:
                    continue
                response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
                continue
            if request_id is not None:
                sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            print(f"KoDex MCP bridge error: {exc}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="KoDex local assistant bridge")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--task-add")
    group.add_argument("--task-list", action="store_true")
    group.add_argument("--task-complete")
    args = parser.parse_args()
    if args.task_add is not None:
        print(json.dumps(add_task(args.task_add), ensure_ascii=False))
    elif args.task_list:
        print(json.dumps(list_tasks(), ensure_ascii=False))
    elif args.task_complete is not None:
        print(json.dumps(complete_task(args.task_complete), ensure_ascii=False))
    else:
        mcp_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
