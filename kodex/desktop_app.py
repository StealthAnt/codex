"""Standalone KoDex desktop MVP: local Ollama chat, tasks, apps, and project links."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
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
    "You have no permission to operate apps or run code from this chat window. "
    "Suggest actions for the user to review and start themselves."
)

STARTER_RESOURCES = [
    ("MathWorks Challenge Project Hub", "Research and design project ideas", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub"),
    ("Drones", "UAV control, path planning, SLAM, and sensing projects", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Drones.md"),
    ("Robotics", "Robot design, manipulation, navigation, and simulation ideas", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Robotics.md"),
    ("Autonomous Vehicles", "Localization, perception, planning, and vehicle control", "https://github.com/mathworks/MATLAB-Simulink-Challenge-Project-Hub/blob/main/megatrends/Autonomous%20Vehicles.md"),
    ("Hackathon-in-a-Box", "Materials and steps for running a 4-6 hour hackathon", "https://github.com/mathworks/hackathon-in-a-box/tree/main"),
]


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
        self.model_names: list[str] = []
        self.history: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        for key, label in [("chat", "Chat"), ("tasks", "My tasks"), ("apps", "My apps"), ("resources", "Project resources")]:
            ttk.Button(self.nav, text=label, command=lambda page=key: self._show_page(page)).pack(fill="x", pady=3)
        ttk.Separator(self.nav).pack(fill="x", pady=14)
        ttk.Label(self.nav, text="MODEL", background=PANEL, foreground=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=10, pady=(3, 8))
        self.model_box = ttk.Combobox(self.nav, textvariable=self.model, state="normal", width=24)
        self.model_box.pack(fill="x", padx=5)
        ttk.Button(self.nav, text="Refresh models", command=self.refresh_models).pack(fill="x", pady=(8, 4))
        ttk.Button(self.nav, text="Open Ollama", command=self.open_ollama).pack(fill="x", pady=4)
        ttk.Label(self.nav, text="Chat runs on your PC\nwhen a local model is ready.", background=PANEL, foreground=MUTED, font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=9, pady=(18, 5))

        self.content = ttk.Frame(body, style="Panel.TFrame", padding=20)
        self.content.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.pages: dict[str, ttk.Frame] = {}
        self._chat_page()
        self._tasks_page()
        self._apps_page()
        self._resources_page()

    def _page_header(self, parent: ttk.Frame, title: str, subtitle: str) -> None:
        ttk.Label(parent, text=title, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 17)).pack(anchor="w")
        ttk.Label(parent, text=subtitle, background=PANEL, foreground=MUTED, wraplength=760).pack(anchor="w", pady=(4, 16))

    def _chat_page(self) -> None:
        page = ttk.Frame(self.content, style="Panel.TFrame")
        self.pages["chat"] = page
        self._page_header(page, "Local assistant", "Your messages stay on this computer when you use Ollama with a downloaded model.")
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
        ttk.Label(page, text="Enter a local model name if the model list is empty, then press Send. Ctrl+Enter sends.", background=PANEL, foreground=MUTED).pack(anchor="w", pady=(7, 0))
        self._append_chat("KoDex", "Welcome. I’m a local-first assistant shell. Pick a model in the left panel to start a conversation.")

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
        if not prompt:
            return
        if not model:
            messagebox.showinfo("Choose a model", "Install/download a model in Ollama, then select it or type its name in the Model field.")
            return
        self.prompt.delete("1.0", "end")
        self.history.append({"role": "user", "content": prompt})
        self._append_chat("You", prompt)
        self.send_button.configure(state="disabled", text="Thinking…")
        threading.Thread(target=self._chat_request, args=(model, list(self.history)), daemon=True).start()

    def _chat_request(self, model: str, messages: list[dict[str, str]]) -> None:
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

    def _chat_finished(self, answer: str, error: str | None) -> None:
        if error:
            self._append_chat("KoDex", f"I couldn’t reach the local model at {OLLAMA_URL}. Open Ollama and check that a model is installed.\n\nDetails: {error}")
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
        else:
            self._append_chat("KoDex", answer)
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
        self.model_box.configure(values=names)
        if names and not self.model.get():
            self.model.set(names[0])
        self.status.configure(text=f"Local Ollama · {len(names)} model(s)" if not error else "Local model offline · open Ollama to start")

    def open_ollama(self) -> None:
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [local / "Programs" / "Ollama" / "ollama app.exe"]
        for app in candidates:
            if app.is_file():
                subprocess.Popen([str(app)], close_fds=True)
                self.after(900, self.refresh_models)
                return
        messagebox.showerror("Ollama not found", "Install Ollama or open it from the Windows Start menu.")

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
        self._page_header(page, "Project resources", "Starter material from MathWorks for robotics, UAV, autonomous vehicle, and student competition projects. Internet is needed to visit a link.")
        for title, description, url in STARTER_RESOURCES:
            card = ttk.Frame(page, style="Panel.TFrame", padding=(12, 10))
            card.pack(fill="x", pady=5)
            ttk.Label(card, text=title, background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w")
            ttk.Label(card, text=description, background=PANEL, foreground=MUTED, wraplength=680).pack(anchor="w", pady=(3, 7))
            link = ttk.Label(card, text=url, background=PANEL, foreground=ACCENT, cursor="hand2", wraplength=700)
            link.pack(anchor="w")
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))

    def _show_page(self, key: str) -> None:
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        if key == "tasks":
            self.refresh_tasks()


if __name__ == "__main__":
    KoDexDesktop().mainloop()
