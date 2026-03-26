from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import tkinter as tk
import urllib.parse
import urllib.request
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
        self.root.geometry("900x600")

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.busy = False
        self.last_prompt_id: str | None = None

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
            ("Run Workflow", self.run_workflow),
            ("Check Output", self.check_output),
            ("Open Modal", self.open_modal),
        ]:
            tk.Button(buttons, text=text, width=14, command=cmd).pack(side=tk.LEFT, padx=(0, 8))

        # Prompt input section
        prompt_frame = tk.Frame(self.root, padx=12, pady=4)
        prompt_frame.pack(fill=tk.X)
        
        tk.Label(prompt_frame, text="Video Prompt (leave blank for default):", anchor="w").pack(fill=tk.X)
        self.prompt_input = tk.Text(prompt_frame, height=3, wrap=tk.WORD, font=("Consolas", 9))
        self.prompt_input.pack(fill=tk.X)
        
        default_prompt = "A traditional Japanese tea ceremony takes place in a tatami room as a host carefully prepares matcha."
        self.prompt_input.insert(tk.END, default_prompt)

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

    def run_workflow(self) -> None:
        def do_run() -> str:
            workflow_path = ROOT_DIR / "workflow_api.json"
            if not workflow_path.exists():
                return f"Error: {workflow_path} not found."
            
            try:
                # Get custom prompt from input
                custom_prompt = self.prompt_input.get("1.0", tk.END).strip()
                
                with open(workflow_path, "r") as f:
                    workflow = json.load(f)
                
                # Update all CLIPTextEncode nodes with custom prompt
                if custom_prompt:
                    for node_id, node_data in workflow.get("nodes", {}).items() if isinstance(workflow.get("nodes"), dict) else enumerate(workflow.get("nodes", [])):
                        if isinstance(node_data, dict) and node_data.get("type") == "CLIPTextEncode":
                            if "widgets_values" in node_data and isinstance(node_data["widgets_values"], list):
                                node_data["widgets_values"][0] = custom_prompt
                
                url = f"{COMFYUI_URL}/prompt"
                data = json.dumps({"prompt": workflow}).encode("utf-8")
                
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    prompt_id = result.get("prompt_id")
                    self.last_prompt_id = prompt_id
                    return f"Workflow submitted!\nPrompt: {custom_prompt[:60]}...\nPrompt ID: {prompt_id}\nCheck status with 'Check Output' button."
            except Exception as e:
                return f"Error submitting workflow: {str(e)}"
        
        self._run_in_thread(do_run)
    
    def check_output(self) -> None:
        def do_check() -> str:
            if not self.last_prompt_id:
                return "No prompt ID stored. Run a workflow first."
            
            try:
                url = f"{COMFYUI_URL}/history/{self.last_prompt_id}"
                with urllib.request.urlopen(url, timeout=10) as response:
                    history = json.loads(response.read().decode("utf-8"))
                
                if not history or self.last_prompt_id not in history:
                    return f"Prompt {self.last_prompt_id} not in history yet. Still processing or not started."
                
                output = history[self.last_prompt_id]
                lines = [f"Prompt ID: {self.last_prompt_id}"]
                
                if "outputs" in output:
                    lines.append("\nOutputs:")
                    for node_id, node_output in output["outputs"].items():
                        lines.append(f"\n  Node {node_id}:")
                        for key, value in node_output.items():
                            if isinstance(value, list):
                                for item in value:
                                    if isinstance(item, str) and (item.endswith(".mp4") or item.endswith(".png")):
                                        download_url = f"{COMFYUI_URL}/view?filename={item}"
                                        lines.append(f"    {key}: {item}")
                                        lines.append(f"    Download: {download_url}")
                            else:
                                lines.append(f"    {key}: {value}")
                else:
                    lines.append("No outputs yet.")
                
                return "\n".join(lines)
            except Exception as e:
                return f"Error checking output: {str(e)}"
        
        self._run_in_thread(do_check)

    def open_modal(self) -> None:
        webbrowser.open(DEPLOYMENT_URL)
        self._append_log(f"\nOpened {DEPLOYMENT_URL}\n")


def main() -> None:
    root = tk.Tk()
    ControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()