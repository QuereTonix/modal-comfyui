"""
FitSweetTreat Video Automation App
Full pipeline: Prompt -> Bella/George (Gemini) -> KokoroTTS -> LTX 2.3 -> moviepy -> Queue
"""

import os
import sys
import json
import time
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from cryptography.fernet import Fernet
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "app_database.db"
CREDS_PATH = ROOT_DIR / "credentials.vault"
TEMP_DIR = ROOT_DIR / "temp"
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "assets"

COMFYUI_URL = "https://chlevin135--modal-comfyui-ui.modal.run"
KOKORO_URL = "http://localhost:8000"
BG_MUSIC_URL = "https://www.chosic.com/wp-content/uploads/2021/07/The-Wait-Extreme-Music.mp3"
GEMINI_MODEL = "gemini-2.0-flash"

GEORGE_SYSTEM_PROMPT = (
    "You are George, a video production expert for FitSweetTreat, a healthy food short-form channel.\n"
    "Given a food recipe prompt, produce a structured 3-scene video script as JSON.\n\n"
    "Output ONLY valid JSON matching this exact schema. No markdown, no code fences, no extra text:\n"
    "{\n"
    "  \"recipe_name\": \"Short dish name\",\n"
    "  \"script\": \"Full narration across all 3 scenes\",\n"
    "  \"video_scenes\": [\n"
    "    {\n"
    "      \"scene\": 1,\n"
    "      \"voiceText\": \"Hi, I'm George, this is FitSweetTreat and today we're making [DISH]. [Hook]. About 20 words.\",\n"
    "      \"videoPrompt\": \"40-60 word cinematic opening. Camera movement, lighting, textures, ambient audio.\"\n"
    "    },\n"
    "    {\n"
    "      \"scene\": 2,\n"
    "      \"voiceText\": \"One sentence about the main cooking step. About 20 words.\",\n"
    "      \"videoPrompt\": \"40-60 word mid-scene shot. Action, close-ups, sizzle sounds, steam, camera angle.\"\n"
    "    },\n"
    "    {\n"
    "      \"scene\": 3,\n"
    "      \"voiceText\": \"Final line ending with the word but or so. About 20 words.\",\n"
    "      \"videoPrompt\": \"40-60 word beauty shot. Warm golden light, full dish reveal, camera pull-back.\"\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Hard rules:\n"
    "- scene 1 voiceText MUST start with: Hi, I'm George, this is FitSweetTreat and today we're making\n"
    "- scene 3 voiceText MUST end with the word: but  OR  so\n"
    "- Each voiceText must be ~20 words (5-8 seconds spoken)\n"
    "- Each videoPrompt must be 40-60 words with camera movement + lighting + audio detail"
)


class CredentialVault:
    def __init__(self, vault_path=CREDS_PATH):
        self.vault_path = vault_path
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    def _load_or_create_key(self):
        key_file = self.vault_path.parent / ".vault_key"
        if key_file.exists():
            return key_file.read_bytes()
        key = Fernet.generate_key()
        key_file.write_bytes(key)
        return key

    def save_credentials(self, creds_dict):
        data = json.dumps(creds_dict).encode()
        self.vault_path.write_bytes(self.cipher.encrypt(data))

    def load_credentials(self):
        if not self.vault_path.exists():
            return {}
        try:
            return json.loads(self.cipher.decrypt(self.vault_path.read_bytes()).decode())
        except Exception:
            return {}


class Database:
    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS video_queue ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  recipe_name TEXT,"
            "  george_json TEXT,"
            "  final_video_path TEXT,"
            "  status TEXT DEFAULT 'pending',"
            "  created_at TEXT DEFAULT (datetime('now')),"
            "  approved_at TEXT"
            ")"
        )
        conn.commit()
        conn.close()

    def add_to_queue(self, recipe_name, george_json, final_video_path):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO video_queue (recipe_name, george_json, final_video_path) VALUES (?, ?, ?)",
            (recipe_name, json.dumps(george_json), str(final_video_path)),
        )
        vid_id = c.lastrowid
        conn.commit()
        conn.close()
        return vid_id

    def approve(self, vid_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE video_queue SET status='approved', approved_at=datetime('now') WHERE id=?",
            (vid_id,),
        )
        conn.commit()
        conn.close()

    def delete(self, vid_id):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM video_queue WHERE id=?", (vid_id,))
        conn.commit()
        conn.close()

    def get_pending(self):
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, recipe_name, final_video_path, created_at FROM video_queue "
            "WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return rows


class GeminiGeorge:
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=GEORGE_SYSTEM_PROMPT)

    def generate_scenes(self, user_prompt):
        response = self.model.generate_content(user_prompt)
        text = response.text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())


class ComfyUIBridge:
    def __init__(self):
        self.url = COMFYUI_URL
        wf_path = ROOT_DIR / "workflow_api.json"
        if not wf_path.exists():
            raise FileNotFoundError("workflow_api.json not found next to this script.")
        self.workflow = json.loads(wf_path.read_text())

    def submit(self, video_prompt):
        wf = json.loads(json.dumps(self.workflow))
        if "2483" in wf:
            wf["2483"]["inputs"]["text"] = video_prompt
        else:
            for node_id, node in wf.items():
                if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                    wf[node_id]["inputs"]["text"] = video_prompt
                    break
        resp = requests.post(f"{self.url}/prompt", json={"prompt": wf}, timeout=60)
        resp.raise_for_status()
        pid = resp.json().get("prompt_id")
        if not pid:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return pid

    def wait_and_download(self, prompt_id, output_path, timeout=1800, progress_cb=None):
        start = time.time()
        while time.time() - start < timeout:
            elapsed = int(time.time() - start)
            if progress_cb:
                progress_cb(f"LTX generating... {elapsed}s")
            try:
                resp = requests.get(f"{self.url}/history/{prompt_id}", timeout=30)
                history = resp.json()
            except Exception:
                time.sleep(5)
                continue
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_out in outputs.values():
                    for item in node_out.get("videos", []):
                        fname = item.get("filename", "")
                        subfolder = item.get("subfolder", "")
                        if fname.endswith(".mp4"):
                            view_url = f"{self.url}/view?filename={fname}&type=output"
                            if subfolder:
                                view_url += f"&subfolder={subfolder}"
                            if progress_cb:
                                progress_cb(f"Downloading {fname}...")
                            r = requests.get(view_url, timeout=600, stream=True)
                            r.raise_for_status()
                            with open(output_path, "wb") as f:
                                for chunk in r.iter_content(8192):
                                    f.write(chunk)
                            return str(output_path)
            time.sleep(5)
        raise TimeoutError(f"LTX timed out after {timeout}s")


class KokoroTTS:
    def speak(self, text, output_path, voice="bm_george"):
        resp = requests.post(
            f"{KOKORO_URL}/api/tts",
            json={"text": text, "voice": voice},
            timeout=60,
        )
        resp.raise_for_status()
        Path(output_path).write_bytes(resp.content)
        return str(output_path)


class VideoStitcher:
    def stitch(self, scenes, bg_music_path, output_path, progress_cb=None):
        from moviepy.editor import (
            VideoFileClip, AudioFileClip,
            concatenate_videoclips, CompositeAudioClip,
        )
        try:
            from moviepy.audio.fx.all import audio_loop as moviepy_audio_loop
        except ImportError:
            moviepy_audio_loop = None

        scene_clips = []
        for i, scene in enumerate(scenes):
            if progress_cb:
                progress_cb(f"Merging scene {i + 1}/3...")
            video = VideoFileClip(scene["video"])
            audio = AudioFileClip(scene["audio"])
            if audio.duration > video.duration:
                audio = audio.subclip(0, video.duration)
            scene_clips.append(video.set_audio(audio))

        if progress_cb:
            progress_cb("Concatenating 3 scenes...")
        final = concatenate_videoclips(scene_clips, method="compose")

        if bg_music_path and Path(bg_music_path).exists():
            if progress_cb:
                progress_cb("Mixing background music...")
            bg = AudioFileClip(str(bg_music_path)).volumex(0.15)
            if moviepy_audio_loop and bg.duration < final.duration:
                bg = moviepy_audio_loop(bg, duration=final.duration)
            else:
                bg = bg.subclip(0, min(bg.duration, final.duration))
            if final.audio:
                final = final.set_audio(CompositeAudioClip([final.audio, bg]))
            else:
                final = final.set_audio(bg)

        if progress_cb:
            progress_cb("Writing final MP4...")
        final.write_videofile(
            str(output_path), verbose=False, logger=None,
            codec="libx264", audio_codec="aac",
        )
        for clip in scene_clips:
            clip.close()
        final.close()
        return str(output_path)


def ensure_dirs():
    for d in (TEMP_DIR, OUTPUT_DIR, ASSETS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def download_bg_music(log_cb=None):
    bg_path = ASSETS_DIR / "bg_music.mp3"
    if bg_path.exists():
        return str(bg_path)
    if log_cb:
        log_cb("Downloading background music (one-time)...")
    try:
        r = requests.get(BG_MUSIC_URL, timeout=60, stream=True)
        r.raise_for_status()
        with open(bg_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return str(bg_path)
    except Exception as e:
        if log_cb:
            log_cb(f"BG music download failed: {e}")
        return None


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FitSweetTreat Video Automation")
        self.root.geometry("1100x800")
        ensure_dirs()
        self.vault = CredentialVault()
        self.db = Database()
        self.credentials = self.vault.load_credentials()
        self._pipeline_running = False
        self._build_ui()

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tab_gen = ttk.Frame(nb)
        self.tab_queue = ttk.Frame(nb)
        self.tab_settings = ttk.Frame(nb)
        self.tab_logs = ttk.Frame(nb)
        nb.add(self.tab_gen, text="Generate")
        nb.add(self.tab_queue, text="Queue")
        nb.add(self.tab_settings, text="Settings")
        nb.add(self.tab_logs, text="Logs")
        self._build_generate_tab()
        self._build_queue_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    def _build_generate_tab(self):
        f = ttk.Frame(self.tab_gen, padding=12)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Recipe Prompt", font=("Arial", 12, "bold")).pack(anchor="w")
        ttk.Label(f, text="Describe the dish, ingredients, macros, and style.", foreground="#555").pack(anchor="w")
        self.prompt_input = tk.Text(f, height=7, width=95, wrap=tk.WORD)
        self.prompt_input.pack(fill=tk.X, pady=(5, 8))
        btn_row = ttk.Frame(f)
        btn_row.pack(fill=tk.X)
        self.gen_btn = ttk.Button(btn_row, text="Generate Video  >>>", command=self._start_pipeline)
        self.gen_btn.pack(side=tk.LEFT, padx=5)
        self.status_lbl = ttk.Label(btn_row, text="Ready", foreground="#007700")
        self.status_lbl.pack(side=tk.LEFT, padx=15)
        self.progress = ttk.Progressbar(f, mode="indeterminate", length=600)
        self.progress.pack(fill=tk.X, pady=6)
        ttk.Label(f, text="George's 3-Scene Plan (live):", font=("Arial", 11, "bold")).pack(anchor="w", pady=(8, 2))
        self.plan_text = scrolledtext.ScrolledText(f, height=20, width=95, state=tk.DISABLED, wrap=tk.WORD)
        self.plan_text.pack(fill=tk.BOTH, expand=True)

    def _build_queue_tab(self):
        f = ttk.Frame(self.tab_queue, padding=12)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Pending Review", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 8))
        cols = ("ID", "Recipe", "Video Path", "Created")
        self.queue_tree = ttk.Treeview(f, columns=cols, show="headings", height=15)
        self.queue_tree.heading("ID", text="ID")
        self.queue_tree.heading("Recipe", text="Recipe")
        self.queue_tree.heading("Video Path", text="Video Path")
        self.queue_tree.heading("Created", text="Created")
        self.queue_tree.column("ID", width=40)
        self.queue_tree.column("Recipe", width=200)
        self.queue_tree.column("Video Path", width=420)
        self.queue_tree.column("Created", width=160)
        self.queue_tree.pack(fill=tk.BOTH, expand=True)
        bf = ttk.Frame(f)
        bf.pack(fill=tk.X, pady=8)
        ttk.Button(bf, text="Refresh", command=self._refresh_queue).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Approve + Schedule", command=self._approve_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Delete", command=self._delete_selected).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Open File", command=self._open_video).pack(side=tk.LEFT, padx=4)
        self._refresh_queue()

    def _build_settings_tab(self):
        f = ttk.Frame(self.tab_settings, padding=12)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="API Credentials", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))
        self._cred_entries = {}
        for label, key in [
            ("Gemini API Key", "gemini_api_key"),
            ("TikTok API Key", "tiktok_api_key"),
            ("Instagram Token", "instagram_api_token"),
            ("YouTube API Key", "youtube_api_key"),
        ]:
            ttk.Label(f, text=label + ":").pack(anchor="w")
            e = ttk.Entry(f, width=65, show="*")
            e.pack(anchor="w", pady=(2, 8))
            e.insert(0, self.credentials.get(key, ""))
            self._cred_entries[key] = e
        ttk.Button(f, text="Save Credentials", command=self._save_credentials).pack(pady=8, anchor="w")
        ttk.Separator(f).pack(fill=tk.X, pady=10)
        ttk.Label(f, text=f"ComfyUI endpoint: {COMFYUI_URL}").pack(anchor="w")
        ttk.Label(f, text=f"KokoroTTS endpoint: {KOKORO_URL}").pack(anchor="w")
        ttk.Label(f, text=f"Gemini model: {GEMINI_MODEL}").pack(anchor="w")
        ttk.Label(f, text="Voice: bm_george").pack(anchor="w")

    def _build_logs_tab(self):
        f = ttk.Frame(self.tab_logs, padding=12)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="System Logs", font=("Arial", 12, "bold")).pack(anchor="w")
        self.logs_text = scrolledtext.ScrolledText(f, height=35, wrap=tk.WORD)
        self.logs_text.pack(fill=tk.BOTH, expand=True, pady=5)
        self.logs_text.config(state=tk.DISABLED)
        self._log("App started. Ready.")

    def _save_credentials(self):
        creds = {k: e.get() for k, e in self._cred_entries.items()}
        self.vault.save_credentials(creds)
        self.credentials = creds
        messagebox.showinfo("Saved", "Credentials saved securely.")
        self._log("Credentials updated.")

    def _start_pipeline(self):
        if self._pipeline_running:
            messagebox.showwarning("Busy", "Pipeline already running.")
            return
        prompt = self.prompt_input.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("Input", "Enter a recipe prompt first.")
            return
        api_key = self.credentials.get("gemini_api_key") or self._cred_entries["gemini_api_key"].get()
        if not api_key:
            messagebox.showerror("Error", "Set your Gemini API key in Settings first.")
            return
        self._pipeline_running = True
        self.gen_btn.config(state=tk.DISABLED)
        self.progress.start(12)
        threading.Thread(target=self._run_pipeline, args=(prompt, api_key), daemon=True).start()

    def _run_pipeline(self, prompt, api_key):
        try:
            self._status("Step 1/6  Calling Gemini (George)...")
            george = GeminiGeorge(api_key)
            plan = george.generate_scenes(prompt)
            self._show_plan(plan)
            recipe = plan.get("recipe_name", "Unknown Recipe")
            self._log(f"George returned plan: {recipe}")

            scenes = plan.get("video_scenes", [])
            if len(scenes) != 3:
                raise ValueError(f"Expected 3 scenes, got {len(scenes)}")

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            comfy = ComfyUIBridge()
            tts = KokoroTTS()
            stitcher = VideoStitcher()
            bg_music = download_bg_music(self._log)

            self._status("Step 2/6  Submitting 3 video jobs to LTX 2.3...")
            prompt_ids = []
            for sc in scenes:
                self._log(f"  Submitting scene {sc['scene']}...")
                pid = comfy.submit(sc["videoPrompt"])
                prompt_ids.append(pid)
                self._log(f"  Scene {sc['scene']} -> {pid}")

            self._status("Step 3/6  Generating voice audio (KokoroTTS)...")
            audio_paths = []
            for i, sc in enumerate(scenes):
                self._log(f"  TTS scene {sc['scene']}: {sc['voiceText'][:55]}...")
                ap = TEMP_DIR / f"audio_{run_id}_s{i+1}.wav"
                tts.speak(sc["voiceText"], ap)
                audio_paths.append(str(ap))
                self._log(f"  Audio {i+1} saved.")

            self._status("Step 4/6  Waiting for LTX videos (5-15 min each)...")
            video_paths = []
            for i, pid in enumerate(prompt_ids):
                self._log(f"  Polling scene {i+1} (pid: {pid})...")
                vp = TEMP_DIR / f"video_{run_id}_s{i+1}.mp4"
                comfy.wait_and_download(
                    pid, vp,
                    progress_cb=lambda msg, n=i: self._status(f"Step 4/6  Scene {n+1}: {msg}"),
                )
                video_paths.append(str(vp))
                self._log(f"  Scene {i+1} video downloaded.")

            self._status("Step 5/6  Stitching scenes + adding BG music...")
            scene_data = [{"video": video_paths[i], "audio": audio_paths[i]} for i in range(3)]
            final_path = OUTPUT_DIR / f"final_{run_id}.mp4"
            stitcher.stitch(scene_data, bg_music, final_path, progress_cb=self._status)
            self._log(f"Final video: {final_path}")

            self._status("Step 6/6  Adding to review queue...")
            vid_id = self.db.add_to_queue(recipe, plan, str(final_path))
            self._log(f"Added to queue as #{vid_id}.")

            self._status(f"Done! '{recipe}' ready for review.")
            self.root.after(0, lambda: messagebox.showinfo(
                "Video Ready",
                f"Done! '{recipe}' is in the Queue tab.\n\nFile: {final_path}"
            ))
            self.root.after(0, self._refresh_queue)

        except Exception as exc:
            import traceback
            self._log(f"PIPELINE ERROR: {exc}")
            self._log(traceback.format_exc())
            self._status(f"Error: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Pipeline Error", str(exc)))
        finally:
            self._pipeline_running = False
            self.root.after(0, lambda: self.gen_btn.config(state=tk.NORMAL))
            self.root.after(0, self.progress.stop)

    def _show_plan(self, plan):
        def _update():
            self.plan_text.config(state=tk.NORMAL)
            self.plan_text.delete("1.0", tk.END)
            self.plan_text.insert("1.0", json.dumps(plan, indent=2))
            self.plan_text.config(state=tk.DISABLED)
        self.root.after(0, _update)

    def _refresh_queue(self):
        for row in self.queue_tree.get_children():
            self.queue_tree.delete(row)
        for row in self.db.get_pending():
            self.queue_tree.insert("", tk.END, values=row)

    def _approve_selected(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a video first.")
            return
        vid_id = self.queue_tree.item(sel[0])["values"][0]
        self.db.approve(vid_id)
        self._refresh_queue()
        self._log(f"Video #{vid_id} approved.")
        messagebox.showinfo("Approved", f"Video #{vid_id} approved.")

    def _delete_selected(self):
        sel = self.queue_tree.selection()
        if not sel:
            return
        vid_id = self.queue_tree.item(sel[0])["values"][0]
        self.db.delete(vid_id)
        self._refresh_queue()
        self._log(f"Video #{vid_id} deleted.")

    def _open_video(self):
        sel = self.queue_tree.selection()
        if not sel:
            return
        path = self.queue_tree.item(sel[0])["values"][2]
        if path and Path(str(path)).exists():
            os.startfile(path)
        else:
            messagebox.showwarning("Not Found", f"File not found:\n{path}")

    def _status(self, msg):
        self.root.after(0, lambda: self.status_lbl.config(text=msg))
        self._log(msg)

    def _log(self, message):
        def _write():
            if not hasattr(self, "logs_text"):
                return
            self.logs_text.config(state=tk.NORMAL)
            ts = datetime.now().strftime("%H:%M:%S")
            self.logs_text.insert(tk.END, f"[{ts}] {message}\n")
            self.logs_text.see(tk.END)
            self.logs_text.config(state=tk.DISABLED)
        self.root.after(0, _write)


def main():
    root = tk.Tk()
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
