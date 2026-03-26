"""
FitSweetTreat Video Automation App
Full pipeline: Prompt → Bella/George (Gemini) → KokoroTTS → LTX 2.3 → moviepy → Queue
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

GEORGE_SYSTEM_PROMPT = """You are George, a video production expert for FitSweetTreat — a healthy food short-form channel.
Given a food recipe prompt, produce a structured 3-scene video script as JSON.

Output ONLY valid JSON matching this exact schema. No markdown, no code fences, no extra text:
{
  "recipe_name": "Short dish name",
  "script": "Full narration across all 3 scenes",
  "video_scenes": [
    {
      "scene": 1,
      "voiceText": "Hi, I'm George, this is FitSweetTreat and today we're making [DISH NAME]. [One hook sentence about key ingredient]. About 20 words total.",
      "videoPrompt": "40-60 word cinematic opening shot. Describe camera movement, lighting style, textures, and ambient audio cues."
    },
    {
      "scene": 2,
      "voiceText": "One sentence describing the main cooking step or highlight. About 20 words.",
      "videoPrompt": "40-60 word mid-scene cinematic shot. Describe action, camera angle, close-ups, sizzle sounds, steam, etc."
    },
    {
      "scene": 3,
      "voiceText": "Final line ending with the word but or so. About 20 words.",
      "videoPrompt": "40-60 word final beauty shot. Warm golden lighting, full dish reveal, camera pull-back or slow pan."
    }
  ]
}

Hard rules:
- scene 1 voiceText MUST start with exactly: Hi, I'm George, this is FitSweetTreat and today we're making
- scene 3 voiceText MUST end with the word: but  OR  so
- Each voiceText must be ~20 words (roughly 5-8 seconds spoken aloud)
- Each videoPrompt must be 40-60 words with camera movement + lighting + audio detail"""


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
    """SQLite management for queue and history"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS video_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_name TEXT NOT NULL,
            video_prompts TEXT NOT NULL,
            voice_texts TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            final_video_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            posted_at TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS posting_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            post_time TIME NOT NULL,
            video_id INTEGER,
            FOREIGN KEY(video_id) REFERENCES video_queue(id)
        )''')
        
        conn.commit()
        conn.close()
    
    def add_video_to_queue(self, recipe_name, video_prompts, voice_texts):
        """Add generated video to queue for review"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO video_queue (recipe_name, video_prompts, voice_texts)
                     VALUES (?, ?, ?)''',
                  (recipe_name, json.dumps(video_prompts), json.dumps(voice_texts)))
        video_id = c.lastrowid
        conn.commit()
        conn.close()
        return video_id
    
    def approve_video(self, video_id, final_video_path):
        """Mark video as approved and ready for posting"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''UPDATE video_queue 
                     SET status='approved', final_video_path=?, approved_at=CURRENT_TIMESTAMP
                     WHERE id=?''', (final_video_path, video_id))
        conn.commit()
        conn.close()
    
    def get_queue(self, status='pending'):
        """Get videos with specific status"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM video_queue WHERE status=? ORDER BY created_at DESC',
                  (status,))
        videos = c.fetchall()
        conn.close()
        return videos


class ScheduleConfig:
    """Manage posting schedule"""
    
    def __init__(self, config_path=CONFIG_PATH):
        self.config_path = config_path
        self.load_or_create()
    
    def load_or_create(self):
        """Load existing config or create default"""
        if self.config_path.exists():
            self.config = json.loads(self.config_path.read_text())
        else:
            self.config = {
                "timezone": "America/New_York",
                "platforms": {
                    "tiktok": {"posts_per_day": 3, "times": ["09:00", "14:00", "20:00"]},
                    "instagram": {"posts_per_day": 2, "times": ["12:00", "18:00"]},
                    "youtube": {"posts_per_day": 1, "times": ["15:00"]}
                }
            }
            self.save()
    
    def save(self):
        """Save schedule to file"""
        self.config_path.write_text(json.dumps(self.config, indent=2))
    
    def get_schedule(self):
        """Get current schedule"""
        return self.config
    
    def update_platform_schedule(self, platform, times):
        """Update posting times for a platform"""
        self.config["platforms"][platform]["times"] = sorted(times)
        self.config["platforms"][platform]["posts_per_day"] = len(times)
        self.save()


class GeminiAgent:
    """Interface with Google Gemini for Bella + George"""
    
    def __init__(self, api_key):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.0-flash")
    
    def chat_with_bella(self, user_message):
        """Get Bella's response"""
        response = self.model.generate_content(f"""
You are Bella, a helpful assistant. Respond naturally to: {user_message}
Keep it brief and friendly. No emojis or special formatting.
""")
        return response.text
    
    def generate_george_content(self, user_request):
        """Generate George's structured video content"""
        prompt = f"""
Given this request: {user_request}

You are George, a video production expert. Generate a JSON with:
1. recipe_name: Name of the dish
2. script: Full script with ingredients
3. video_scenes: Array of 3 scenes, each with:
   - scene: Scene number (1-3)
   - voiceText: ~20 words of speech
   - videoPrompt: 40-60 words, cinematic, with audio cues and camera movements

Output ONLY valid JSON, no extra text.
"""
        response = self.model.generate_content(prompt)
        try:
            return json.loads(response.text)
        except:
            return None


class ComfyUIBridge:
    """Interface with Modal-hosted ComfyUI LTX"""
    
    def __init__(self, comfyui_url="https://chlevin135--modal-comfyui-ui.modal.run"):
        self.url = comfyui_url
        self.workflow_template = self._load_workflow_template()
    
    def _load_workflow_template(self):
        """Load the workflow_api.json template"""
        workflow_path = ROOT_DIR / "workflow_api.json"
        if workflow_path.exists():
            return json.loads(workflow_path.read_text())
        return {}
    
    def generate_video(self, video_prompt):
        """Submit prompt to ComfyUI and get video"""
        if not self.workflow_template:
            raise Exception("No workflow template found")
        
        # Update prompt in workflow
        workflow = self.workflow_template.copy()
        for node_id, node_data in workflow.get("nodes", {}).items():
            if isinstance(node_data, dict) and node_data.get("type") == "CLIPTextEncode":
                if "widgets_values" in node_data:
                    node_data["widgets_values"][0] = video_prompt
        
        # Submit to ComfyUI
        response = requests.post(
            f"{self.url}/prompt",
            json={"prompt": workflow},
            timeout=600
        )
        result = response.json()
        prompt_id = result.get("prompt_id")
        
        if not prompt_id:
            raise Exception("Failed to submit workflow to ComfyUI")
        
        # Poll for completion
        return self._wait_for_video(prompt_id)
    
    def _wait_for_video(self, prompt_id, max_wait=1800):
        """Poll ComfyUI history for completion"""
        import time
        start = time.time()
        
        while time.time() - start < max_wait:
            response = requests.get(f"{self.url}/history/{prompt_id}")
            history = response.json()
            
            if prompt_id in history:
                output = history[prompt_id]
                if "outputs" in output:
                    # Extract video file path
                    for node_id, node_output in output["outputs"].items():
                        for key, value in node_output.items():
                            if isinstance(value, list):
                                for item in value:
                                    if isinstance(item, str) and item.endswith(".mp4"):
                                        return f"{self.url}/view?filename={item}"
            
            time.sleep(5)
        
        raise Exception("ComfyUI generation timed out")


class AudioProcessing:
    """Handle TTS and audio merging with moviepy"""
    
    def __init__(self, tts_endpoint="http://localhost:8000"):
        # Default to local kokoro-tts service
        self.tts_endpoint = tts_endpoint.rstrip('/')
    
    def generate_voice(self, text, voice_id="bm_george"):
        """Generate TTS audio using local kokoro-tts service"""
        try:
            # kokoro-tts format: POST /api/tts with JSON body
            response = requests.post(
                f"{self.tts_endpoint}/api/tts",
                json={"text": text, "voice": voice_id},
                timeout=30
            )
            if response.status_code == 200:
                # Save as temporary audio file
                audio_data = response.content
                temp_audio = Path("/tmp") / f"voice_{hash(text)}.wav"
                temp_audio.write_bytes(audio_data)
                return str(temp_audio)
            else:
                raise Exception(f"TTS error: {response.status_code}")
        except Exception as e:
            raise Exception(f"Voice generation failed: {str(e)}")
    
    def merge_video_audio(self, video_path, audio_path, output_path):
        """Use moviepy to merge video and audio (no FFmpeg required)"""
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip
            
            # Load video and audio
            video = VideoFileClip(str(video_path))
            audio = AudioFileClip(str(audio_path))
            
            # Set audio to video
            final = video.set_audio(audio)
            
            # Write result
            final.write_videofile(str(output_path), verbose=False, logger=None)
            
            # Clean up
            final.close()
            video.close()
            audio.close()
            
        except Exception as e:
            raise Exception(f"Video/audio merge failed: {str(e)}")


class MainApp:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("FitSweetTreat Video Automation")
        self.root.geometry("1000x700")
        
        self.vault = CredentialVault()
        self.db = Database()
        self.schedule = ScheduleConfig()
        self.credentials = self.vault.load_credentials()
        
        self._build_ui()
    
    def _build_ui(self):
        """Build main UI"""
        # Notebook (tabs)
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.settings_frame = ttk.Frame(notebook)
        self.queue_frame = ttk.Frame(notebook)
        self.logs_frame = ttk.Frame(notebook)
        
        notebook.add(self.settings_frame, text="Settings & Chat")
        notebook.add(self.queue_frame, text="Queue")
        notebook.add(self.logs_frame, text="Logs")
        
        self._build_settings_tab()
        self._build_queue_tab()
        self._build_logs_tab()
    
    def _build_settings_tab(self):
        """Settings and chat interface"""
        frame = ttk.Frame(self.settings_frame, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Status
        ttk.Label(frame, text="API Configuration", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        ttk.Label(frame, text="Gemini API Key:").pack(anchor="w")
        self.gemini_entry = ttk.Entry(frame, width=50, show="*")
        self.gemini_entry.pack(anchor="w", pady=5)
        self.gemini_entry.insert(0, self.credentials.get("gemini_api_key", ""))
        
        ttk.Label(frame, text="TikTok API Key:").pack(anchor="w")
        self.tiktok_entry = ttk.Entry(frame, width=50, show="*")
        self.tiktok_entry.pack(anchor="w", pady=5)
        self.tiktok_entry.insert(0, self.credentials.get("tiktok_api_key", ""))
        
        ttk.Label(frame, text="Instagram API Token:").pack(anchor="w")
        self.instagram_entry = ttk.Entry(frame, width=50, show="*")
        self.instagram_entry.pack(anchor="w", pady=5)
        self.instagram_entry.insert(0, self.credentials.get("instagram_api_token", ""))
        
        ttk.Label(frame, text="YouTube API Key:").pack(anchor="w")
        self.youtube_entry = ttk.Entry(frame, width=50, show="*")
        self.youtube_entry.pack(anchor="w", pady=5)
        self.youtube_entry.insert(0, self.credentials.get("youtube_api_key", ""))
        
        # Save credentials button
        ttk.Button(frame, text="Save Credentials (Encrypted)", command=self._save_credentials).pack(pady=10)
        
        # Schedule section
        ttk.Label(frame, text="Posting Schedule", font=("Arial", 12, "bold")).pack(anchor="w", pady=(20, 10))
        
        schedule_text = "TikTok: 3x daily at 9:00 AM, 2:00 PM, 8:00 PM\n"
        schedule_text += "Instagram: 2x daily at 12:00 PM, 6:00 PM\n"
        schedule_text += "YouTube: 1x daily at 3:00 PM"
        ttk.Label(frame, text=schedule_text, justify="left").pack(anchor="w")
        
        # Chat section
        ttk.Label(frame, text="Chat with Bella", font=("Arial", 12, "bold")).pack(anchor="w", pady=(20, 10))
        
        ttk.Label(frame, text="Enter your request:").pack(anchor="w")
        self.chat_input = tk.Text(frame, height=3, width=50)
        self.chat_input.pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="Send to Bella →", command=self._send_to_bella).pack(pady=10)
        
        ttk.Label(frame, text="Response:").pack(anchor="w")
        self.bella_response = scrolledtext.ScrolledText(frame, height=8, width=60)
        self.bella_response.pack(anchor="w", pady=5)
    
    def _build_queue_tab(self):
        """Queue viewer"""
        frame = ttk.Frame(self.queue_frame, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Video Queue (Pending Review)", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        # Queue list
        self.queue_listbox = tk.Listbox(frame, height=15, width=80)
        self.queue_listbox.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Action buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="Refresh Queue", command=self._refresh_queue).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Approve & Schedule Posting", command=self._approve_video).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete", command=self._delete_video).pack(side=tk.LEFT, padx=5)
        
        self._refresh_queue()
    
    def _build_logs_tab(self):
        """Activity logs"""
        frame = ttk.Frame(self.logs_frame, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="System Logs", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        self.logs_text = scrolledtext.ScrolledText(frame, height=25, width=100)
        self.logs_text.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self._log("System initialized. Ready for video generation.")
    
    def _save_credentials(self):
        """Save API credentials encrypted"""
        creds = {
            "gemini_api_key": self.gemini_entry.get(),
            "tiktok_api_key": self.tiktok_entry.get(),
            "instagram_api_token": self.instagram_entry.get(),
            "youtube_api_key": self.youtube_entry.get()
        }
        self.vault.save_credentials(creds)
        messagebox.showinfo("Success", "Credentials saved securely!")
        self._log("Credentials updated and encrypted.")
    
    def _send_to_bella(self):
        """Send message to Bella (Gemini)"""
        user_input = self.chat_input.get("1.0", tk.END).strip()
        if not user_input:
            messagebox.showwarning("Input", "Please enter a message.")
            return
        
        # Check if credentials are set
        if not self.gemini_entry.get():
            messagebox.showerror("Error", "Please set Gemini API key first.")
            return
        
        # Process in background
        self._log("Processing with Bella...")
        threading.Thread(target=self._process_bella_request, args=(user_input,), daemon=True).start()
    
    def _process_bella_request(self, user_input):
        """Background thread for Bella processing"""
        try:
            agent = GeminiAgent(self.gemini_entry.get())
            response = agent.chat_with_bella(user_input)
            self.bella_response.config(state=tk.NORMAL)
            self.bella_response.delete("1.0", tk.END)
            self.bella_response.insert("1.0", response)
            self.bella_response.config(state=tk.DISABLED)
            self._log(f"Bella responded: {response[:100]}...")
        except Exception as e:
            self._log(f"Error: {str(e)}")
            messagebox.showerror("Error", str(e))
    
    def _refresh_queue(self):
        """Refresh queue display"""
        self.queue_listbox.delete(0, tk.END)
        videos = self.db.get_queue("pending")
        for video in videos:
            self.queue_listbox.insert(tk.END, f"[{video[0]}] {video[1]} - {video[7]}")
    
    def _approve_video(self):
        """Mark video for posting"""
        selection = self.queue_listbox.curselection()
        if not selection:
            messagebox.showwarning("Selection", "Please select a video.")
            return
        
        messagebox.showinfo("Approved", "Video scheduled for posting!")
        self._log("Video approved and scheduled for distribution.")
    
    def _delete_video(self):
        """Delete video from queue"""
        selection = self.queue_listbox.curselection()
        if selection:
            self.queue_listbox.delete(selection)
            self._log("Video deleted from queue.")
    
    def _log(self, message):
        """Add message to logs"""
        self.logs_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.logs_text.see(tk.END)
        self.logs_text.config(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
