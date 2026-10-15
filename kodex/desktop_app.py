"""Standalone KoDex desktop MVP: local Ollama chat, tasks, apps, and project links."""

from __future__ import annotations

import json
import os
import base64
import ctypes
import shutil
import sys
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import getpass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import assistant_bridge as bridge


BG = "#10141c"
PANEL = "#171e29"
PANEL_2 = "#202a38"
TEXT = "#e8edf5"
MUTED = "#9aa8ba"
ACCENT = "#72d7c5"
OLLAMA_URL = "http://127.0.0.1:11434"
SYSTEM_PROMPT = (
    "You are KoDex, a personal offline engineering and learning assistant. "
    "Help with robotics, CAD, MATLAB, Arduino, software, cybersecurity, STEAM, "
    "and research. Be clear about uncertainty and cite links when you know them. "
    "You may inspect only the currently approved project folder and files the user attaches. "
    "Use read-only inspection only. Never write files, run programs, or access files outside that folder. "
    "Do not claim to have changed files or operated apps."
)
CHAT_PROVIDERS = ("Local Ollama", "ChatGPT account (Codex)", "Claude API", "Claude Code CLI", "Qwen API")
DEFAULT_MODELS = {"Claude API": "claude-sonnet-4-6", "Qwen API": "qwen-plus"}
QWEN_DEFAULT_ENDPOINT = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _windows_protect(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise OSError("KoDex credential storage requires Windows DPAPI.")
    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    blob_ptr = ctypes.POINTER(_DataBlob)
    common = [blob_ptr, ctypes.c_void_p, blob_ptr, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, blob_ptr]
    crypt32.CryptProtectData.argtypes = common
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [blob_ptr, ctypes.POINTER(ctypes.c_wchar_p), blob_ptr, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, blob_ptr]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(data)
    source_blob = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    result_blob = _DataBlob()
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source_blob), None, None, None, None, 1, ctypes.byref(result_blob))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source_blob), None, None, None, None, 1, ctypes.byref(result_blob))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData)
    finally:
        kernel32.LocalFree(result_blob.pbData)

STARTER_RESOURCES = [
    ("MathWorks Challenge Project Hub", "Research and design project ideas", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub"),
    ("Drones", "UAV control, path planning, SLAM, and sensing projects", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Drones.md"),
    ("Robotics", "Robot design, manipulation, navigation, and simulation ideas", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Robotics.md"),
    ("Autonomous Vehicles", "Localization, perception, planning, and vehicle control", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Autonomous%20Vehicles.md"),
    ("Hackathon-in-a-Box", "Materials and steps for running a 4-6 hour hackathon", "https://github.com/mathworks/hackathon-in-a-box/tree/main"),
    ("MIT OCW: Introduction to Robotics", "Robot kinematics, motion planning, mechanisms, controls, sensors, and labs", "https://ocw.mit.edu/courses/2-12-introduction-to-robotics-fall-2005/"),
    ("MIT OCW: Robotic Manipulation", "Perception, manipulation planning, and robot control course materials", "https://ocw.mit.edu/courses/6-4210-robotic-manipulation-fall-2022/"),
    ("Stanford: Introduction to Robotics", "Open course materials for robotics", "https://see.stanford.edu/Course/CS223A"),
    ("ROS Documentation", "ROS 2 tutorials and technical documentation", "https://docs.ros.org/en/rolling/"),
    ("NIST Cybersecurity Framework", "Cybersecurity outcomes and implementation guidance", "https://www.nist.gov/cyberframework"),
    ("MITRE ATT&CK", "Public knowledge base for defensive threat-informed security", "https://attack.mitre.org/"),
    ("OWASP Top 10", "Web application security risks and defensive guidance", "https://owasp.org/www-project-top-ten/"),
]

RESOURCE_CATEGORIES = {
    "robotics": "Robotics",
    "engineering": "Engineering",
    "steam": "STEAM",
    "competitions": "Competitions",
    "competition_robots": "Competition robots",
    "arduino": "Arduino",
    "cad": "CAD",
    "stl_cad": "STL and CAD files",
    "matlab": "MATLAB",
    "ros": "ROS",
}


class KoDexDesktop(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KoDex | Personal Engineering Assistant")
        self.geometry("1100x740")
        self.minsize(850, 600)
        self.configure(bg=BG)
        asset_dir = Path(__file__).resolve().parent
        icon_file = asset_dir / "app_icon.ico"
        if icon_file.is_file():
            self.iconbitmap(str(icon_file))
        png_file = asset_dir / "app_icon.png"
        self.brand_icon = tk.PhotoImage(file=str(png_file)) if png_file.is_file() else None
        self.model = tk.StringVar(value="")
        self.provider = tk.StringVar(value="Local Ollama")
        self.model_names: list[str] = []
        self.provider_models = dict(DEFAULT_MODELS)
        self.provider_models.update({"Local Ollama": "", "ChatGPT account (Codex)": "", "Claude Code CLI": ""})
        self._current_provider = self.provider.get()
        self.history: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.user_name = getpass.getuser()
        self.settings_path = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "KoDex" / "permissions.json"
        self.secrets_path = self.settings_path.with_name("credentials.dpapi")
        self.provider_settings_path = self.settings_path.with_name("providers.json")
        self.allowed_roots = self._load_allowed_roots()
        self.secrets = self._load_secrets()
        self.provider_settings = self._load_provider_settings()
        self._style()
        self._shell()
        self._show_page("chat")
        self.after(300, self.refresh_models)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Brand.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 19))
        style.configure("TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, padding=(12, 8), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#2c3b4d"), ("disabled", PANEL)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#10141c", font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#91e7d7")])
        style.configure("TEntry", fieldbackground=PANEL_2, foreground=TEXT, borderwidth=0, padding=8)
        style.configure("TCombobox", fieldbackground=PANEL_2, foreground=TEXT, background=PANEL_2, padding=6)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=32, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=MUTED, font=("Segoe UI Semibold", 9), relief="flat")

    def _shell(self) -> None:
        header = ttk.Frame(self, padding=(22, 17, 22, 12))
        header.pack(fill="x")
        if self.brand_icon:
            ttk.Label(header, image=self.brand_icon).pack(side="left", padx=(0, 10))
        ttk.Label(header, text="KoDex", style="Brand.TLabel").pack(side="left")
        ttk.Label(header, text="PERSONAL ENGINEERING ASSISTANT", style="Muted.TLabel").pack(side="left", padx=(12, 0), pady=(7, 0))
        self.status = ttk.Label(header, text="Checking local model…", style="Muted.TLabel")
        self.status.pack(side="right", pady=(5, 0))

        body = ttk.Frame(self, padding=(16, 0, 16, 16))
        body.pack(fill="both", expand=True)
        self.nav = ttk.Frame(body, style="Panel.TFrame", padding=10)
        self.nav.pack(side="left", fill="y")
        ttk.Label(self.nav, text="WORKSPACE", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=10, pady=(7, 12))
        for key, label in [("chat", "Chat"), ("workspace", "Workspace"), ("providers", "AI providers"), ("permissions", "Permissions"), ("tasks", "My tasks"), ("apps", "My apps"), ("resources", "Project resources")]:
            ttk.Button(self.nav, text=label, command=lambda page=key: self._show_page(page)).pack(fill="x", pady=3)
        ttk.Separator(self.nav).pack(fill="x", pady=14)
        ttk.Label(self.nav, text="MODEL", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=10, pady=(3, 8))
        self.provider_box = ttk.Combobox(self.nav, textvariable=self.provider, state="readonly", values=CHAT_PROVIDERS, width=24)
        self.provider_box.pack(fill="x", padx=5, pady=(0, 7))
        self.provider_box.bind("<<ComboboxSelected>>", self._provider_changed)
        self.model_box = ttk.Combobox(self.nav, textvariable=self.model, state="normal", width=24)
        self.model_box.pack(fill="x", padx=5)
        ttk.Button(self.nav, text="Refresh models", command=self.refresh_models).pack(fill="x", pady=(8, 4))
        ttk.Button(self.nav, text="Provider sign-in / setup", command=self.manage_provider).pack(fill="x", pady=4)
        ttk.Button(self.nav, text="Open Ollama", command=self.open_ollama).pack(fill="x", pady=4)
        ttk.Label(self.nav, text="Ollama stays local.\nOther providers send prompts to their service.", background=PANEL, foreground=MUTED, font=("Segoe UI", 9), justify="left", wraplength=185).pack(anchor="w", padx=9, pady=(15, 5))
        ttk.Label(self.nav, text=f"WINDOWS USER\n{self.user_name}", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 8), justify="left").pack(anchor="w", padx=9, pady=(15, 5))

        self.content = ttk.Frame(body, style="Panel.TFrame", padding=20)
        self.content.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.pages: dict[str, ttk.Frame] = {}
        self._chat_page()
        self._workspace_page()
        self._permissions_page()
        self._providers_page()
        self._tasks_page()
        self._apps_page()
        self._resources_page()

    def _page_header(self, parent: ttk.Frame, title: str, subtitle: str) -> None:
        ttk.Label(parent, text=title, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 17)).pack(anchor="w")
        ttk.Label(parent, text=subtitle, background=PANEL, foreground=MUTED, wraplength=760).pack(anchor="w", pady=(4, 16))

    def _chat_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["chat"] = page
        self._page_header(page, "KoDex chat", "Choose Ollama for on-device chat or a connected provider. Cloud providers receive the messages you send.")
        self.chat_view = tk.Text(page, bg=BG, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", padx=14, pady=12, font=("Segoe UI", 10), state="disabled")
        self.chat_view.pack(fill="both", expand=True)
        self.chat_view.tag_configure("who", foreground=ACCENT, font=("Segoe UI Semibold", 10))
        self.chat_view.tag_configure("body", foreground=TEXT, spacing3=12)
        compose = ttk.Frame(page, style="Panel.TFrame", padding=(0, 12, 0, 0))
        compose.pack(fill="x")
        self.prompt = tk.Text(compose, height=3, bg=PANEL_2, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", padx=10, pady=9, font=("Segoe UI", 10))
        self.prompt.pack(side="left", fill="x", expand=True)
        self.prompt.bind("<Control-Return>", self._send_hotkey)
        self.send_button = ttk.Button(compose, text="Send", style="Accent.TButton", command=self.send_message)
        self.send_button.pack(side="left", padx=(10, 0), anchor="s")
        compose_tools = ttk.Frame(page, style="Panel.TFrame")
        compose_tools.pack(fill="x", pady=(7, 0))
        ttk.Button(compose_tools, text="Attach workspace file", command=self.attach_workspace_file).pack(side="left")
        self.voice_button = ttk.Button(compose_tools, text="Dictate", command=self.start_dictation)
        self.voice_button.pack(side="left", padx=(7, 0))
        self.speak_replies = tk.BooleanVar(value=False)
        ttk.Checkbutton(compose_tools, text="Speak replies", variable=self.speak_replies).pack(side="left", padx=7)
        ttk.Label(compose_tools, text="Voice is push-to-talk. Review the transcript before sending.", background=PANEL, foreground=MUTED).pack(side="left", padx=6)
        self._append_chat("KoDex", "Welcome. I’m a local-first assistant shell. Pick a model in the left panel to start a conversation.")

    def _voice_script_path(self) -> Path:
        bundle = getattr(sys, "_MEIPASS", None)
        base = Path(bundle) if bundle else Path(__file__).resolve().parent
        return base / "KoDexVoiceInput.ps1"

    def start_dictation(self) -> None:
        if getattr(self, "voice_busy", False):
            return
        script = self._voice_script_path()
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if not script.is_file() or not powershell:
            messagebox.showerror("Voice input unavailable", "The KoDex voice helper or Windows PowerShell is missing. Rebuild KoDex from the repository before using voice input.")
            return
        self.voice_busy = True
        self.voice_button.configure(state="disabled", text="Listening…")
        threading.Thread(target=self._listen_once, args=(powershell, script), daemon=True).start()

    def _listen_once(self, powershell: str, script: Path) -> None:
        args = [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "Listen"]
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            transcript = result.stdout.strip()
            error = result.stderr.strip() if result.returncode else ""
            if result.returncode and not error:
                error = "Windows speech recognition did not complete. Check microphone permission and an installed speech language."
            self.after(0, lambda text=transcript, detail=error: self._voice_finished(text, detail))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.after(0, lambda detail=str(exc): self._voice_finished("", detail))

    def _voice_finished(self, transcript: str, error: str) -> None:
        self.voice_busy = False
        self.voice_button.configure(state="normal", text="Dictate")
        if error:
            self._append_chat("KoDex voice", f"Voice input could not complete: {error}")
            return
        transcript = transcript.strip()
        if not transcript:
            self._append_chat("KoDex voice", "I did not catch anything. Try Dictate again.")
            return
        command = transcript.casefold()
        if command.startswith("add task "):
            title = transcript[9:].strip()
            if title:
                try:
                    task = bridge.add_task(title)
                    self.refresh_tasks()
                    self._append_chat("KoDex voice", f"Added task {task['id']}: {task['title']}")
                    self._speak_reply(f"Task added: {task['title']}")
                except Exception as exc:
                    self._append_chat("KoDex voice", f"Could not add task: {exc}")
                return
        if command in {"list tasks", "list my tasks", "show tasks", "show my tasks", "read my tasks"}:
            tasks = bridge.list_tasks()
            summary = "You have no open tasks." if not tasks else "Open tasks: " + "; ".join(f"{item['id']}: {item['title']}" for item in tasks[:10])
            self._append_chat("KoDex voice", summary)
            self._speak_reply(summary)
            return
        if command.startswith("complete task "):
            task_id = transcript[len("complete task "):].strip().upper()
            try:
                task = bridge.complete_task(task_id)
                self.refresh_tasks()
                message = f"Completed task {task['id']}: {task['title']}"
                self._append_chat("KoDex voice", message)
                self._speak_reply(message)
            except Exception as exc:
                self._append_chat("KoDex voice", f"Could not complete that task: {exc}")
            return
        self._show_page("chat")
        self.prompt.insert("end", transcript)
        self.prompt.focus_set()
        self._append_chat("KoDex voice", f"Transcript ready to review: {transcript}")

    def _speak_reply(self, text: str) -> None:
        if not getattr(self, "speak_replies", None) or not self.speak_replies.get():
            return
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        script = self._voice_script_path()
        if not powershell or not script.is_file():
            return
        encoded = base64.b64encode(text[:1000].encode("utf-8")).decode("ascii")
        args = [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Action", "Speak"]
        threading.Thread(target=lambda: subprocess.run(args, input=encoded, capture_output=True, text=True, timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)), daemon=True).start()

    def _load_allowed_roots(self) -> list[Path]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            roots = [Path(item).resolve() for item in data.get("workspace_roots", [])]
            return [path for path in roots if path.is_dir()]
        except (OSError, ValueError, TypeError):
            return []

    def _load_secrets(self) -> dict[str, str]:
        try:
            raw = _windows_protect(self.secrets_path.read_bytes(), decrypt=True)
            data = json.loads(raw.decode("utf-8"))
            return {str(name): str(value) for name, value in data.items() if value}
        except (OSError, ValueError, UnicodeError, TypeError):
            return {}

    def _save_secrets(self) -> None:
        self.secrets_path.parent.mkdir(parents=True, exist_ok=True)
        protected = _windows_protect(json.dumps(self.secrets).encode("utf-8"))
        self.secrets_path.write_bytes(protected)

    def _load_provider_settings(self) -> dict[str, str]:
        try:
            data = json.loads(self.provider_settings_path.read_text(encoding="utf-8"))
            return {"qwen_endpoint": str(data.get("qwen_endpoint") or QWEN_DEFAULT_ENDPOINT)}
        except (OSError, ValueError, TypeError):
            return {"qwen_endpoint": QWEN_DEFAULT_ENDPOINT}

    def _save_provider_settings(self) -> None:
        self.provider_settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.provider_settings_path.write_text(json.dumps(self.provider_settings, indent=2), encoding="utf-8")

    def _provider_changed(self, _event: tk.Event[Any] | None = None) -> None:
        selected = self.provider.get()
        if selected != self._current_provider:
            self.provider_models[self._current_provider] = self.model.get().strip()
            self.model.set(self.provider_models.get(selected, DEFAULT_MODELS.get(selected, "")))
            self._current_provider = selected
        if selected == "Local Ollama":
            self.model_box.configure(state="normal", values=self.model_names)
            if self.model_names and self.model.get() not in self.model_names:
                self.model.set(self.model_names[0])
        else:
            self.model_box.configure(state="normal", values=())
            if selected in {"Claude API", "Qwen API"} and not self.model.get():
                self.model.set(DEFAULT_MODELS[selected])
        if selected == "ChatGPT account (Codex)":
            self.status.configure(text="ChatGPT via local Codex sign-in")
        elif selected == "Claude Code CLI":
            self.status.configure(text="Claude Code CLI available" if shutil.which("claude") else "Claude Code CLI not installed")
        elif selected in {"Claude API", "Qwen API"}:
            key = "anthropic" if selected == "Claude API" else "qwen"
            self.status.configure(text=f"{selected} key saved" if self.secrets.get(key) else f"{selected} needs setup")
        else:
            self.status.configure(text="Checking local model…")

    def _providers_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["providers"] = page
        self._page_header(page, "AI providers", "Use your local Ollama models or connect to the AI accounts and APIs you already have. KoDex does not request provider passwords.")
        definitions = [
            ("ChatGPT account (Codex)", "Uses the installed Codex CLI sign-in. Chats are sent to OpenAI; KoDex asks the CLI to run read-only.", "codex"),
            ("Claude API", "Uses an Anthropic API key. This is billed through the API account, separately from Claude web plans.", "anthropic"),
            ("Claude Code CLI", "Uses Claude Code's own OAuth sign-in if its CLI is installed. Plan mode keeps this chat read-only.", "claude_cli"),
            ("Qwen API", "Uses an Alibaba Cloud Model Studio API key and its regional endpoint. API charges and limits follow that account.", "qwen"),
            ("Local Ollama", "Runs on this laptop with downloaded models. No prompt leaves the computer through Ollama.", "ollama"),
        ]
        for title, detail, key in definitions:
            card = ttk.Frame(page, style="Panel.TFrame", padding=12)
            card.pack(fill="x", pady=5)
            left = ttk.Frame(card, style="Panel.TFrame")
            left.pack(side="left", fill="x", expand=True)
            ttk.Label(left, text=title, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w")
            ttk.Label(left, text=detail, background=PANEL, foreground=MUTED, wraplength=620, justify="left").pack(anchor="w", pady=(4, 0))
            status = self._provider_status(key)
            ttk.Label(card, text=status, background=PANEL, foreground=ACCENT if "ready" in status.lower() or "saved" in status.lower() else MUTED, wraplength=160).pack(side="right", padx=(10, 0))
            ttk.Button(card, text="Set up", command=lambda provider=title: self._configure_provider(provider)).pack(side="right", padx=(10, 0))

    def _provider_status(self, provider_key: str) -> str:
        if provider_key == "codex":
            return "Codex CLI found" if shutil.which("codex") else "Not installed"
        if provider_key == "claude_cli":
            return "CLI found" if shutil.which("claude") else "Not installed"
        if provider_key in {"anthropic", "qwen"}:
            return "API key saved" if self.secrets.get(provider_key) else "Add API key"
        return "Select model" if self.model_names else "Ollama offline"

    def manage_provider(self) -> None:
        self._configure_provider(self.provider.get())

    def _configure_provider(self, provider: str) -> None:
        if provider == "ChatGPT account (Codex)":
            executable = shutil.which("codex")
            if not executable:
                messagebox.showinfo("Codex sign-in", "Install Codex CLI and sign in with your ChatGPT account first.")
                return
            try:
                result = subprocess.run([executable, "login", "status"], capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                status = (result.stdout + "\n" + result.stderr).strip()
            except (OSError, subprocess.TimeoutExpired) as exc:
                status = str(exc)
            messagebox.showinfo("ChatGPT account", status or "Codex CLI is installed. Sign in from a terminal with `codex login` if needed.")
        elif provider == "Claude API":
            self._set_secret("anthropic", "Anthropic API key", "Paste an Anthropic Console API key. KoDex stores it encrypted for this Windows account.")
        elif provider == "Claude Code CLI":
            if shutil.which("claude"):
                messagebox.showinfo("Claude Code", "Claude Code CLI is detected. KoDex will call it in plan mode for chat requests.")
            else:
                if messagebox.askyesno("Claude Code not found", "Claude Code is not installed. Open Anthropic's official setup guide?"):
                    webbrowser.open("https://docs.anthropic.com/en/docs/claude-code/getting-started")
        elif provider == "Qwen API":
            self._set_secret("qwen", "Qwen Model Studio API key", "Paste the Alibaba Cloud Model Studio key for the endpoint below. KoDex encrypts it for this Windows account.")
            endpoint = simpledialog.askstring("Qwen endpoint", "Regional base URL (include /compatible-mode/v1; don't add /chat/completions). The key and endpoint must be from the same region:", initialvalue=self.provider_settings.get("qwen_endpoint", QWEN_DEFAULT_ENDPOINT), parent=self)
            if endpoint and endpoint.startswith("https://"):
                self.provider_settings["qwen_endpoint"] = endpoint.rstrip("/")
                self._save_provider_settings()
            elif endpoint:
                messagebox.showerror("Invalid endpoint", "The Qwen endpoint must start with https://")
        elif provider == "Local Ollama":
            self.provider.set(provider)
            self.refresh_models()
        self._provider_changed()

    def _set_secret(self, key: str, title: str, prompt: str) -> None:
        if self.secrets.get(key):
            if messagebox.askyesno(title, "A key is already saved. Replace it?"):
                value = simpledialog.askstring(title, prompt, show="*", parent=self)
            elif messagebox.askyesno(title, "Remove the saved key?"):
                self.secrets.pop(key, None)
                self._save_secrets()
            else:
                return
        else:
            value = simpledialog.askstring(title, prompt, show="*", parent=self)
        if value:
            self.secrets[key] = value.strip()
            try:
                self._save_secrets()
            except OSError as exc:
                self.secrets.pop(key, None)
                messagebox.showerror("Could not store key", f"The key was not saved.\n\n{exc}")

    def _save_allowed_roots(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps({"workspace_roots": [str(path) for path in self.allowed_roots]}, indent=2), encoding="utf-8")

    def _workspace_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["workspace"] = page
        self._page_header(page, "Workspace", "KoDex can browse only folders you add here. Choose a project folder to grant it as a workspace.")
        row = ttk.Frame(page, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 10))
        self.workspace_var = tk.StringVar()
        self.workspace_box = ttk.Combobox(row, textvariable=self.workspace_var, state="readonly")
        self.workspace_box.pack(side="left", fill="x", expand=True)
        self.workspace_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_workspace())
        ttk.Button(row, text="Add project folder", style="Accent.TButton", command=self.add_workspace).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Remove access", command=self.remove_workspace).pack(side="left", padx=(8, 0))
        self.workspace_tree = ttk.Treeview(page, columns=("kind", "size"), show="tree headings", selectmode="browse")
        self.workspace_tree.heading("#0", text="PROJECT FILES")
        self.workspace_tree.heading("kind", text="TYPE")
        self.workspace_tree.heading("size", text="SIZE")
        self.workspace_tree.column("#0", width=490)
        self.workspace_tree.column("kind", width=110, stretch=False)
        self.workspace_tree.column("size", width=100, stretch=False, anchor="e")
        self.workspace_tree.pack(fill="both", expand=True)
        self.workspace_tree.bind("<Double-1>", self._open_workspace_item)
        actions = ttk.Frame(page, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="Attach selected file to chat", command=self.attach_selected_workspace_file).pack(side="left")
        ttk.Label(actions, text="Attaching sends that file's text to your selected local model.", background=PANEL, foreground=MUTED).pack(side="left", padx=10)
        self.refresh_workspace()

    def _permissions_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["permissions"] = page
        self._page_header(page, "Permissions", "KoDex uses your existing Windows account. Codex does not ask for or store your Windows password.")
        card = ttk.Frame(page, style="Panel.TFrame", padding=16)
        card.pack(fill="x", pady=(0, 12))
        ttk.Label(card, text="SIGNED IN TO WINDOWS", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w")
        ttk.Label(card, text=self.user_name, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 16)).pack(anchor="w", pady=(4, 12))
        ttk.Label(card, text="KoDex runs with the permissions of this Windows account. Add only the project folders you want it to read. Windows continues to enforce your account's file permissions.", background=PANEL, foreground=MUTED, wraplength=720, justify="left").pack(anchor="w")
        ttk.Label(page, text="APPROVED WORKSPACE FOLDERS", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 6))
        self.permission_list = tk.Listbox(page, height=8, bg=BG, fg=TEXT, selectbackground=ACCENT, relief="flat", font=("Segoe UI", 10), activestyle="none")
        self.permission_list.pack(fill="both", expand=True)
        row = ttk.Frame(page, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Grant a project folder", style="Accent.TButton", command=self.add_workspace).pack(side="left")
        ttk.Button(row, text="Revoke selected folder", command=self.remove_selected_permission).pack(side="left", padx=8)
        ttk.Label(page, text="Folder access is limited to the paths listed above. Chat cannot silently browse your other folders or run commands.", background=PANEL, foreground=MUTED, wraplength=730).pack(anchor="w", pady=(14, 0))
        self.refresh_permissions()

    def _selected_root(self) -> Path | None:
        text = self.workspace_var.get() if hasattr(self, "workspace_var") else ""
        return next((root for root in self.allowed_roots if str(root) == text), None)

    def _is_allowed_path(self, candidate: Path) -> bool:
        try:
            resolved = candidate.resolve(strict=True)
            return any(resolved == root or root in resolved.parents for root in self.allowed_roots)
        except (OSError, RuntimeError):
            return False

    def add_workspace(self) -> None:
        selected = filedialog.askdirectory(title="Choose a project folder to grant to KoDex", mustexist=True)
        if not selected:
            return
        root = Path(selected).resolve()
        if root not in self.allowed_roots:
            self.allowed_roots.append(root)
            try:
                self._save_allowed_roots()
            except OSError as exc:
                self.allowed_roots.remove(root)
                messagebox.showerror("Could not save permission", str(exc))
                return
        self.workspace_var.set(str(root))
        self.refresh_workspace()
        self.refresh_permissions()

    def remove_workspace(self) -> None:
        root = self._selected_root()
        if root is None:
            return
        self.allowed_roots.remove(root)
        self._save_allowed_roots()
        self.workspace_var.set("")
        self.refresh_workspace()
        self.refresh_permissions()

    def remove_selected_permission(self) -> None:
        selection = self.permission_list.curselection()
        if selection:
            self.workspace_var.set(str(self.allowed_roots[selection[0]]))
            self.remove_workspace()

    def refresh_permissions(self) -> None:
        if not hasattr(self, "permission_list"):
            return
        self.permission_list.delete(0, "end")
        for root in self.allowed_roots:
            self.permission_list.insert("end", str(root))

    def refresh_workspace(self) -> None:
        if not hasattr(self, "workspace_tree"):
            return
        values = [str(root) for root in self.allowed_roots]
        self.workspace_box.configure(values=values)
        root = self._selected_root()
        if root is None and self.allowed_roots:
            root = self.allowed_roots[0]
            self.workspace_var.set(str(root))
        self.workspace_tree.delete(*self.workspace_tree.get_children())
        if root is None:
            return
        self._add_workspace_items("", root, depth=0)

    def _add_workspace_items(self, parent: str, folder: Path, depth: int) -> None:
        if depth > 2:
            return
        try:
            entries = sorted(folder.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.casefold()))
        except OSError:
            return
        for path in entries:
            if path.name.startswith(".") or path.name in {"node_modules", "venv", ".venv", "__pycache__"}:
                continue
            try:
                if not self._is_allowed_path(path):
                    continue
                is_dir = path.is_dir()
                size = "" if is_dir else f"{path.stat().st_size:,} B"
            except OSError:
                continue
            item = self.workspace_tree.insert(parent, "end", text=path.name, values=("Folder" if is_dir else path.suffix.lstrip(".").upper() or "File", size), open=False)
            self.workspace_tree.item(item, tags=(str(path),))
            if is_dir:
                self._add_workspace_items(item, path, depth + 1)

    def _selected_workspace_path(self) -> Path | None:
        selection = self.workspace_tree.selection()
        if not selection:
            return None
        try:
            return Path(self.workspace_tree.item(selection[0], "tags")[0])
        except (IndexError, TypeError):
            return None

    def _open_workspace_item(self, _event: tk.Event[Any]) -> None:
        path = self._selected_workspace_path()
        if path and path.is_dir() and self._is_allowed_path(path):
            try:
                os.startfile(str(path))
            except OSError as exc:
                messagebox.showerror("Could not open folder", str(exc))
        elif path and path.is_file():
            self.attach_selected_workspace_file()

    def attach_workspace_file(self) -> None:
        root = self._selected_root()
        if root is None:
            messagebox.showinfo("Grant a workspace first", "Open Permissions and choose a project folder first.")
            return
        selected = filedialog.askopenfilename(title="Choose a file from your approved workspace", initialdir=str(root))
        if selected:
            self._attach_file(Path(selected))

    def attach_selected_workspace_file(self) -> None:
        path = self._selected_workspace_path()
        if path is None or not path.is_file():
            messagebox.showinfo("Select a file", "Choose a file in the workspace list first.")
            return
        self._attach_file(path)

    def _attach_file(self, path: Path) -> None:
        if not self._is_allowed_path(path) or not path.is_file():
            messagebox.showerror("Outside approved workspace", "That file is not inside an approved KoDex project folder.")
            return
        try:
            if path.stat().st_size > 200_000:
                messagebox.showinfo("File too large", "Attach a text file smaller than 200 KB at a time.")
                return
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("Could not read file", f"KoDex can attach UTF-8 text files only.\n\n{exc}")
            return
        addition = f"\n\n--- Attached project file: {path.name} ---\n{text}\n--- End attached file ---\n"
        self.prompt.insert("end", addition)
        self._show_page("chat")

    def _append_chat(self, who: str, message: str) -> None:
        self.chat_view.configure(state="normal")
        self.chat_view.insert("end", who + "\n", "who")
        self.chat_view.insert("end", message.strip() + "\n\n", "body")
        self.chat_view.see("end")
        self.chat_view.configure(state="disabled")

    def _send_hotkey(self, _event: tk.Event[Any]) -> str:
        self.send_message()
        return "break"

    def send_message(self) -> None:
        prompt = self.prompt.get("1.0", "end").strip()
        model = self.model.get().strip()
        provider = self.provider.get()
        if not prompt:
            return
        if provider == "Local Ollama" and not model:
            messagebox.showinfo("Choose a model", "Install/download a model in Ollama, then select it or type its name in the Model field.")
            return
        self.prompt.delete("1.0", "end")
        self.history.append({"role": "user", "content": prompt})
        self._append_chat("You", prompt)
        self.send_button.configure(state="disabled", text="Thinking…")
        threading.Thread(target=self._chat_request, args=(model, list(self.history)), daemon=True).start()

    def _chat_request(self, model: str, messages: list[dict[str, str]]) -> None:
        provider = self.provider.get()
        if provider == "ChatGPT account (Codex)":
            answer, error = self._codex_response(model, messages)
            if error:
                self.after(0, lambda err=error: self._chat_finished("", err))
            else:
                self.history.append({"role": "assistant", "content": answer})
                self.after(0, lambda result=answer: self._chat_finished(result, None))
            return
        if provider == "Claude Code CLI":
            answer, error = self._claude_code_response(model, messages)
            if error:
                self.after(0, lambda err=error: self._chat_finished("", err))
            else:
                self.history.append({"role": "assistant", "content": answer})
                self.after(0, lambda result=answer: self._chat_finished(result, None))
            return
        if provider in {"Claude API", "Qwen API"}:
            answer, error = self._cloud_response(provider, model, messages)
            if error:
                self.after(0, lambda err=error: self._chat_finished("", err))
            else:
                self.history.append({"role": "assistant", "content": answer})
                self.after(0, lambda result=answer: self._chat_finished(result, None))
            return
        payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
        req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = str(result.get("message", {}).get("content", "")).strip() or "The local model returned an empty response."
            self.history.append({"role": "assistant", "content": answer})
            self.after(0, lambda: self._chat_finished(answer, None))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            self.after(0, lambda err=str(exc): self._chat_finished("", err))

    def _codex_response(self, model: str, messages: list[dict[str, str]]) -> tuple[str, str | None]:
        executable = shutil.which("codex")
        if not executable:
            return "", "Codex CLI was not found on PATH. Install it and sign in to your ChatGPT account."
        user_text = "\n\n".join(f"{item['role'].upper()}:\n{item['content']}" for item in messages if item["role"] != "system")
        prompt = SYSTEM_PROMPT + "\n\n" + user_text
        root = self._selected_root()
        cwd = str(root if root else self.settings_path.parent)
        args = [executable, "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never", "--cd", cwd]
        if model:
            args.extend(["--model", model])
        args.append("-")
        try:
            result = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", f"Could not complete the ChatGPT request: {exc}"
        answer_parts: list[str] = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                answer_parts.append(str(item.get("text", "")))
        answer = "\n".join(part for part in answer_parts if part).strip()
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            return "", detail[-1800:] or f"Codex CLI exited with status {result.returncode}."
        return answer or "The ChatGPT provider returned no text.", None

    def _claude_code_response(self, model: str, messages: list[dict[str, str]]) -> tuple[str, str | None]:
        executable = shutil.which("claude")
        if not executable:
            return "", "Claude Code CLI is not installed on this laptop. Use Claude API after adding an API key, or install Claude Code and sign in through its own OAuth flow."
        root = self._selected_root()
        cwd = str(root if root else self.settings_path.parent)
        prompt = "\n\n".join(f"{item['role'].upper()}:\n{item['content']}" for item in messages if item["role"] != "system")
        args = [executable, "-p", "--output-format", "text", "--permission-mode", "plan", "--max-turns", "1"]
        if model:
            args.extend(["--model", model])
        args.append(SYSTEM_PROMPT + "\n\n" + prompt)
        try:
            result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", f"Could not complete the Claude Code request: {exc}"
        if result.returncode:
            return "", (result.stderr or result.stdout).strip()[-1800:] or f"Claude Code exited with status {result.returncode}."
        return result.stdout.strip() or "Claude Code returned no text.", None

    def _cloud_response(self, provider: str, model: str, messages: list[dict[str, str]]) -> tuple[str, str | None]:
        key_name = "anthropic" if provider == "Claude API" else "qwen"
        api_key = self.secrets.get(key_name, "")
        if not api_key:
            return "", f"Add the {provider} API key under Provider sign-in / setup first."
        if provider == "Claude API":
            system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
            turns = [{"role": item["role"], "content": item["content"]} for item in messages if item["role"] != "system"]
            payload = {"model": model or DEFAULT_MODELS[provider], "max_tokens": 2048, "system": system, "messages": turns}
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        else:
            base = str(self.provider_settings.get("qwen_endpoint", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")).rstrip("/")
            payload = {"model": model or DEFAULT_MODELS[provider], "messages": messages, "stream": False}
            url = base + "/chat/completions"
            headers = {"Authorization": "Bearer " + api_key}
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode("utf-8"))
            if provider == "Claude API":
                answer = "".join(str(part.get("text", "")) for part in body.get("content", []) if part.get("type") == "text")
            else:
                answer = str(body.get("choices", [{}])[0].get("message", {}).get("content", ""))
            return answer.strip() or "The provider returned an empty response.", None
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except OSError:
                detail = str(exc)
            return "", f"{provider} returned HTTP {exc.code}: {detail[:1200]}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            return "", f"Could not reach {provider}: {exc}"

    def _chat_finished(self, answer: str, error: str | None) -> None:
        if error:
            self._append_chat("KoDex", f"The selected provider could not complete the request.\n\nDetails: {error}")
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
        else:
            self._append_chat("KoDex", answer)
            self._speak_reply(answer)
        self.send_button.configure(state="normal", text="Send")

    def refresh_models(self) -> None:
        def worker() -> None:
            try:
                with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=2) as response:
                    data = json.loads(response.read().decode("utf-8"))
                names = [str(item.get("name")) for item in data.get("models", []) if item.get("name")]
                self.after(0, lambda: self._models_updated(names, None))
            except Exception as exc:
                self.after(0, lambda err=str(exc): self._models_updated([], err))
        threading.Thread(target=worker, daemon=True).start()

    def _models_updated(self, names: list[str], error: str | None) -> None:
        self.model_names = names
        if self.provider.get() == "Local Ollama":
            self.model_box.configure(values=names)
        if names and not self.model.get() and self.provider.get() == "Local Ollama":
            self.model.set(names[0])
        if self.provider.get() == "Local Ollama":
            self.status.configure(text=f"Local Ollama · {len(names)} model(s)" if not error else "Local model offline · open Ollama to start")
        self.provider_models["Local Ollama"] = self.model.get().strip() if self.provider.get() == "Local Ollama" else self.provider_models.get("Local Ollama", "")

    def _ollama_cli(self) -> str | None:
        configured = os.environ.get("OLLAMA_EXE")
        candidates = [configured] if configured else []
        candidates.extend([
            shutil.which("ollama"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
            str(Path.home() / "Documents" / "Codex" / "KoDexTools" / "Ollama" / "ollama.exe"),
        ])
        return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)

    def open_ollama(self) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [local / "Programs" / "Ollama" / "ollama app.exe"]
        for app in candidates:
            if app.is_file():
                subprocess.Popen([str(app)], close_fds=True)
                self.after(900, self.refresh_models)
                return
        executable = self._ollama_cli()
        if executable:
            env = os.environ.copy()
            env.setdefault("OLLAMA_MODELS", str(Path.home() / ".ollama" / "models"))
            try:
                subprocess.Popen([executable, "serve"], cwd=str(Path(executable).parent), env=env, close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.status.configure(text="Starting local Ollama…")
                self.after(1500, self.refresh_models)
                return
            except OSError as exc:
                messagebox.showerror("Could not start Ollama", str(exc))
                return
        messagebox.showerror("Ollama not found", "Install Ollama or select a local Ollama installation, then try again.")

    def _tasks_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["tasks"] = page
        self._page_header(page, "My tasks", "A small local task list shared with the KoDex bridge.")
        row = ttk.Frame(page, style="Panel.TFrame")
        row.pack(fill="x", pady=(0, 10))
        self.task_title = tk.StringVar()
        ttk.Entry(row, textvariable=self.task_title).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add task", style="Accent.TButton", command=self.add_task).pack(side="left", padx=(8, 0))
        columns = ("id", "title", "created")
        self.task_tree = ttk.Treeview(page, columns=columns, show="headings", selectmode="browse")
        self.task_tree.heading("id", text="ID")
        self.task_tree.heading("title", text="TASK")
        self.task_tree.heading("created", text="CREATED")
        self.task_tree.column("id", width=130, stretch=False)
        self.task_tree.column("title", width=470)
        self.task_tree.column("created", width=170, stretch=False)
        self.task_tree.pack(fill="both", expand=True)
        ttk.Button(page, text="Complete selected", command=self.complete_task).pack(anchor="e", pady=(10, 0))
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        if not hasattr(self, "task_tree"):
            return
        self.task_tree.delete(*self.task_tree.get_children())
        for task in bridge.list_tasks():
            self.task_tree.insert("", "end", values=(task.get("id"), task.get("title"), str(task.get("created_at", ""))[:16]))

    def add_task(self) -> None:
        try:
            bridge.add_task(self.task_title.get())
            self.task_title.set("")
            self.refresh_tasks()
        except Exception as exc:
            messagebox.showerror("Could not add task", str(exc))

    def complete_task(self) -> None:
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showinfo("Select a task", "Select a task first.")
            return
        task_id = self.task_tree.item(selected[0], "values")[0]
        try:
            bridge.complete_task(task_id)
            self.refresh_tasks()
        except Exception as exc:
            messagebox.showerror("Could not complete task", str(exc))

    def _apps_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["apps"] = page
        self._page_header(page, "My apps", "Open an installed engineering app with one click. Each button launches only the app named on it.")
        grid = ttk.Frame(page, style="Panel.TFrame")
        grid.pack(fill="x", anchor="n")
        for i, (key, label, detail) in enumerate([
            ("freecad", "FreeCAD", "CAD models and mechanical design"),
            ("arduino_ide", "Arduino IDE", "Microcontrollers and embedded projects"),
            ("vscode", "VS Code", "Code and project files"),
            ("matlab", "MATLAB", "Simulation, data, and control systems"),
        ]):
            card = ttk.Frame(grid, style="Panel.TFrame", padding=10)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
            ttk.Label(card, text=label, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w")
            ttk.Label(card, text=detail, background=PANEL, foreground=MUTED).pack(anchor="w", pady=(5, 10))
            ttk.Button(card, text="Open", command=lambda app=key: self.open_app(app)).pack(anchor="w")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

    def open_app(self, app: str) -> None:
        try:
            bridge.launch_app(app)
        except Exception as exc:
            messagebox.showerror("Could not open app", str(exc))

    def _resources_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["resources"] = page
        self._page_header(page, "Project resources", "Search public GitHub repos for robotics, engineering, STEAM, competitions, and CAD. Review a repo and its license before cloning it.")
        controls = ttk.Frame(page, style="Panel.TFrame")
        controls.pack(fill="x", pady=(0, 8))
        self.resource_category = tk.StringVar(value=RESOURCE_CATEGORIES["robotics"])
        category_box = ttk.Combobox(controls, textvariable=self.resource_category, state="readonly", values=list(RESOURCE_CATEGORIES.values()), width=22)
        category_box.pack(side="left")
        self.resource_query = tk.StringVar()
        ttk.Entry(controls, textvariable=self.resource_query).pack(side="left", fill="x", expand=True, padx=7)
        self.resource_search_button = ttk.Button(controls, text="Search public GitHub", style="Accent.TButton", command=self.search_resource_repositories)
        self.resource_search_button.pack(side="left")
        self.resource_tree = ttk.Treeview(page, columns=("stars", "license", "updated"), show="tree headings", selectmode="browse", height=7)
        self.resource_tree.heading("#0", text="REPOSITORY")
        self.resource_tree.heading("stars", text="STARS")
        self.resource_tree.heading("license", text="LICENSE")
        self.resource_tree.heading("updated", text="LAST PUSHED")
        self.resource_tree.column("#0", width=350)
        self.resource_tree.column("stars", width=80, stretch=False, anchor="e")
        self.resource_tree.column("license", width=110, stretch=False)
        self.resource_tree.column("updated", width=130, stretch=False)
        self.resource_tree.pack(fill="both", expand=True)
        self.resource_tree.bind("<<TreeviewSelect>>", self._resource_selected)
        self.resource_detail = ttk.Label(page, text="Search public repositories, or view CAD files already downloaded in KoDex resources.", background=PANEL, foreground=MUTED, wraplength=750)
        self.resource_detail.pack(anchor="w", pady=(7, 5))
        actions = ttk.Frame(page, style="Panel.TFrame")
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Open selected repo", command=self.open_selected_resource).pack(side="left")
        ttk.Button(actions, text="Clone selected repo…", command=self.clone_selected_resource).pack(side="left", padx=7)
        ttk.Button(actions, text="Show downloaded CAD files", command=self.show_local_design_files).pack(side="left")
        self.resource_status = ttk.Label(actions, text="Internet is needed for GitHub search and cloning.", background=PANEL, foreground=MUTED)
        self.resource_status.pack(side="left", padx=8)
        resources = ttk.LabelFrame(page, text="University, robotics, and cybersecurity materials", padding=8)
        resources.pack(fill="x", pady=(3, 0))
        for i, (title, _description, url) in enumerate(STARTER_RESOURCES):
            link = ttk.Label(resources, text=title, background=PANEL, foreground=ACCENT, cursor="hand2", wraplength=330)
            link.grid(row=i // 4, column=i % 4, sticky="w", padx=6, pady=3)
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))
        for col in range(4):
            resources.columnconfigure(col, weight=1)
        self.resource_repositories: list[dict[str, Any]] = []

    def search_resource_repositories(self) -> None:
        category = next((key for key, label in RESOURCE_CATEGORIES.items() if label == self.resource_category.get()), "")
        if category not in RESOURCE_CATEGORIES:
            messagebox.showerror("Choose a category", "Select a GitHub resource category first.")
            return
        query = self.resource_query.get().strip()
        self.resource_search_button.configure(state="disabled", text="Searching…")
        self.resource_status.configure(text="Searching public GitHub repositories…")
        def worker() -> None:
            try:
                result = bridge.github_resource_search(category, query=query, limit=12, sort="stars")
                self.after(0, lambda data=result: self._resource_search_finished(data, None))
            except Exception as exc:
                self.after(0, lambda error=str(exc): self._resource_search_finished(None, error))
        threading.Thread(target=worker, daemon=True).start()

    def _resource_search_finished(self, result: dict[str, Any] | None, error: str | None) -> None:
        self.resource_search_button.configure(state="normal", text="Search public GitHub")
        self.resource_tree.delete(*self.resource_tree.get_children())
        self.resource_repositories = []
        if error:
            self.resource_status.configure(text="GitHub search failed")
            self.resource_detail.configure(text=error[:500])
            return
        self.resource_repositories = list((result or {}).get("repositories", []))
        for index, repo in enumerate(self.resource_repositories):
            pushed = str(repo.get("updated_at") or "")[:10]
            self.resource_tree.insert("", "end", iid=str(index), text=repo.get("full_name", ""), values=(repo.get("stars", 0), repo.get("license") or "Unknown", pushed))
        total = (result or {}).get("total_count", 0)
        cached = " · cached" if (result or {}).get("cached") else ""
        self.resource_status.configure(text=f"Showing {len(self.resource_repositories)} of {total} public repos{cached}")
        self.resource_detail.configure(text="Select a repo to inspect its summary and license. KoDex only clones after you approve; downloaded code is not run.")

    def _selected_resource(self) -> dict[str, Any] | None:
        selection = self.resource_tree.selection()
        if not selection:
            return None
        try:
            return self.resource_repositories[int(selection[0])]
        except (IndexError, ValueError):
            return None

    def _resource_selected(self, _event: tk.Event[Any] | None = None) -> None:
        repo = self._selected_resource()
        if repo:
            description = repo.get("description") or "No description provided."
            topics = ", ".join(repo.get("topics", [])[:5])
            self.resource_detail.configure(text=f"{description}  License: {repo.get('license') or 'unknown'}  Topics: {topics or 'none'}")

    def open_selected_resource(self) -> None:
        repo = self._selected_resource()
        if repo and repo.get("url"):
            webbrowser.open(repo["url"])

    def clone_selected_resource(self) -> None:
        repo = self._selected_resource()
        if not repo:
            messagebox.showinfo("Select a repository", "Choose a repository first.")
            return
        full_name = str(repo.get("full_name", ""))
        if not messagebox.askyesno("Clone public repository?", f"Clone {full_name} into KoDex resources? Review its files and license before using it. KoDex will not run the downloaded code."):
            return
        self.resource_status.configure(text=f"Cloning {full_name}…")
        def worker() -> None:
            try:
                result = bridge.github_clone_public_repository(full_name)
                self.after(0, lambda data=result: self._resource_clone_finished(data, None))
            except Exception as exc:
                self.after(0, lambda error=str(exc): self._resource_clone_finished(None, error))
        threading.Thread(target=worker, daemon=True).start()

    def _resource_clone_finished(self, result: dict[str, Any] | None, error: str | None) -> None:
        if error:
            self.resource_status.configure(text=f"Clone failed: {error[:160]}")
            return
        data = result or {}
        self.resource_status.configure(text=f"Cloned {data.get('repository')} · {data.get('design_file_count_in_first_100', 0)} CAD/mesh files")
        self.resource_detail.configure(text=f"Saved to {data.get('local_path')}. No project code was run.")

    def show_local_design_files(self) -> None:
        try:
            result = bridge.local_design_files(limit=100)
        except Exception as exc:
            messagebox.showerror("Could not list local designs", str(exc))
            return
        files = result.get("files", [])
        self.resource_tree.delete(*self.resource_tree.get_children())
        self.resource_repositories = []
        for index, item in enumerate(files):
            self.resource_tree.insert("", "end", iid=str(index), text=item.get("name", ""), values=("", item.get("format", ""), item.get("repository", "")))
        self.resource_status.configure(text=f"{result.get('count', 0)} CAD/mesh files under {result.get('resource_directory')}")
        self.resource_detail.configure(text="Local designs are listed only. KoDex does not execute or automatically open downloaded CAD files.")

    def _show_page(self, key: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        if key == "tasks":
            self.refresh_tasks()


if __name__ == "__main__":
    KoDexDesktop().mainloop()
