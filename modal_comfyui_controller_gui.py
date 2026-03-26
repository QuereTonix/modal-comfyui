from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext

ROOT_DIR = Path(__file__).resolve().parent
APP_NAME = "modal-comfyui"
COMFYUI_URL = "https://chlevin135--modal-comfyui-ui.modal.run"
DEPLOYMENT_URL = "https://modal.com/apps/chlevin135/main/deployed/modal-comfyui"
WORKFLOW_URL = "https://paste.rs/sSZpU"

_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        capture_output=True,
        env=_ENV,
    )


def _find_app_ids() -> list[str]:
    result = _run(["modal", "app", "list"])
    app_ids: list[str] = []
    for line in (result.stdout or "").splitlines():
        if APP_NAME not in line:
            continue
        if "\u2502" in line:
            parts = [p.strip() for p in line.split("\u2502") if p.strip()]
        elif "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
        else:
            parts = line.split()
        for part in parts:
            if part.startswith("ap-"):
                app_ids.append(part)
                break
    return app_ids


class ControllerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Modal ComfyUI Controller")
        self.root.geometry("760x520")

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.busy = False

        self._build_ui()
        self._poll_output()

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, padx=12, pady=12)
        top.pack(fill=tk.X)

        tk.Label(
            top,
            text="LTX 2.3 + ComfyUI + Modal",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        ).pack(fill=tk.X)

        tk.Label(
            top,
            text="Start, stop, inspect, and open your deployment from one window.",
            anchor="w",
        ).pack(fill=tk.X, pady=4)

        buttons = tk.Frame(top)
        buttons.pack(fill=tk.X, pady=8)

        for text, cmd in [
            ("Start", self.start_app),
            ("Stop", self.stop_app),
            ("Status", self.status_app),
            ("Open ComfyUI", self.open_app),
            ("Open Modal", self.open_modal),
        ]:
            tk.Button(buttons, text=text, width=14, command=cmd).pack(side=tk.LEFT, padx=(0, 8))

        log_frame = tk.Frame(self.root, padx=12, pady=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.insert(tk.END, "Ready.\n")
        self.log.configure(state=tk.DISABLED)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _poll_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)
        self.root.after(200, self._poll_output)

    def _stream(self, command: list[str]) -> None:
        if self.busy:
            messagebox.showinfo("Busy", "Another action is still running.")
            return
        self.busy = True
        self._append_log(f"\n$ {' '.join(command)}\n")

        def worker() -> None:
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=_ENV,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.output_queue.put(line)
                code = proc.wait()
                self.output_queue.put(f"[exit {code}]\n")
            finally:
                self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _run_in_thread(self, fn: object) -> None:
        if self.busy:
            messagebox.showinfo("Busy", "Another action is still running.")
            return
        self.busy = True

        def worker() -> None:
            try:
                text = fn()  # type: ignore[call-arg]
                self.output_queue.put(str(text) + "\n")
            finally:
                self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def start_app(self) -> None:
        self._stream(["modal", "deploy", "comfyui.py"])

    def stop_app(self) -> None:
        def do_stop() -> str:
            app_ids = _find_app_ids()
            if not app_ids:
                return "No deployed modal-comfyui app found."
            lines = []
            for app_id in app_ids:
                result = _run(["modal", "app", "stop", app_id])
                lines.append(f"Stopped {app_id}")
                if result.stdout:
                    lines.append(result.stdout.strip())
                if result.stderr:
                    lines.append(result.stderr.strip())
            return "\n".join(lines)

        self._run_in_thread(do_stop)

    def status_app(self) -> None:
        def do_status() -> str:
            result = _run(["modal", "app", "list"])
            matched = [ln for ln in (result.stdout or "").splitlines() if APP_NAME in ln]
            if matched:
                return "\n".join(matched) + f"\n\nComfyUI URL: {COMFYUI_URL}"
            return "No modal-comfyui app found."

        self._run_in_thread(do_status)

    def open_app(self) -> None:
        encoded = urllib.parse.quote(WORKFLOW_URL, safe="")
        url = f"{COMFYUI_URL}/?workflow={encoded}"
        webbrowser.open(url)
        self._append_log(f"\nOpened {url}\n")

    def open_modal(self) -> None:
        webbrowser.open(DEPLOYMENT_URL)
        self._append_log(f"\nOpened {DEPLOYMENT_URL}\n")


def main() -> None:
    root = tk.Tk()
    ControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()