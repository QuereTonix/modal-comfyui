"""
Interactive credential setup wizard
Walks user through obtaining each API key with exact instructions
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import webbrowser
from pathlib import Path


class CredentialWizard:
    """Step-by-step API credential collection"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FitSweetTreat - Credential Setup Wizard")
        self.root.geometry("900x700")
        self.credentials = {}
        
        self._build_wizard()
    
    def _build_wizard(self):
        """Build the wizard interface"""
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Each tab is a platform
        self._build_gemini_tab(notebook)
        self._build_tiktok_tab(notebook)
        self._build_instagram_tab(notebook)
        self._build_youtube_tab(notebook)
        self._build_summary_tab(notebook)
    
    def _build_gemini_tab(self, notebook):
        """Google Gemini API setup"""
        frame = ttk.Frame(notebook, padding=15)
        notebook.add(frame, text="1. Gemini API")
        
        ttk.Label(frame, text="Google Gemini API Setup", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        instructions = """
STEP 1: Go to Google AI Studio
Click the button below to open the official page:

STEP 2: Sign in with your Google account
- Click "Sign in" if not already logged in
- Use your personal Google account

STEP 3: Create an API key
- Click "Create API key" button
- It will be generated instantly

STEP 4: Copy the API key
- Look for a long string like:
  AIzaSyABC123DEF456GHI789JKL012MNO345PQR
- Click "Copy" to copy it

STEP 5: Paste below
"""
        ttk.Label(frame, text=instructions, justify="left", font=("Courier", 9)).pack(anchor="w", pady=10)
        
        ttk.Button(frame, text="📌 Open Google AI Studio", command=lambda: webbrowser.open(
            "https://makersuite.google.com/app/apikey"
        )).pack(anchor="w", pady=10)
        
        ttk.Label(frame, text="Your Gemini API Key:").pack(anchor="w", pady=(20, 5))
        self.gemini_entry = ttk.Entry(frame, width=60)
        self.gemini_entry.pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="✓ Save & Next", command=lambda: self._save_gemini()).pack(anchor="w", pady=10)
    
    def _build_tiktok_tab(self, notebook):
        """TikTok API setup"""
        frame = ttk.Frame(notebook, padding=15)
        notebook.add(frame, text="2. TikTok API")
        
        ttk.Label(frame, text="TikTok API Setup", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        instructions = """
STEP 1: Go to TikTok Developer Portal
Click the button below:

STEP 2: Create a TikTok Developer Account
- Sign up with your email or TikTok account
- Verify your email

STEP 3: Create a New Application
- Go to "My Apps" section
- Click "Create Application"
- Give it a name (e.g., "FitSweetTreat")
- Accept terms and create

STEP 4: Get Your Credentials
- In your app dashboard, find:
  • Client Key (API Key)
  • Client Secret
  • Access Token (if available)

STEP 5: Paste Below
Format: Copy all three separated by commas or paste as shown
"""
        ttk.Label(frame, text=instructions, justify="left", font=("Courier", 9)).pack(anchor="w", pady=10)
        
        ttk.Button(frame, text="📌 Open TikTok Developer Console", command=lambda: webbrowser.open(
            "https://developers.tiktok.com/console/apps"
        )).pack(anchor="w", pady=10)
        
        ttk.Label(frame, text="TikTok Client Key:").pack(anchor="w", pady=(20, 5))
        self.tiktok_key_entry = ttk.Entry(frame, width=60)
        self.tiktok_key_entry.pack(anchor="w", pady=5)
        
        ttk.Label(frame, text="TikTok Client Secret:").pack(anchor="w", pady=(10, 5))
        self.tiktok_secret_entry = ttk.Entry(frame, width=60, show="*")
        self.tiktok_secret_entry.pack(anchor="w", pady=5)
        
        ttk.Label(frame, text="TikTok Access Token:").pack(anchor="w", pady=(10, 5))
        self.tiktok_token_entry = ttk.Entry(frame, width=60, show="*")
        self.tiktok_token_entry.pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="✓ Save & Next", command=lambda: self._save_tiktok()).pack(anchor="w", pady=10)
    
    def _build_instagram_tab(self, notebook):
        """Instagram API setup"""
        frame = ttk.Frame(notebook, padding=15)
        notebook.add(frame, text="3. Instagram API")
        
        ttk.Label(frame, text="Instagram Graph API Setup", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        instructions = """
STEP 1: Go to Meta Developers
Click the button below:

STEP 2: Create a Meta App
- Click "My Apps" → "Create App"
- Choose "Business" type
- Fill in app name and contact email

STEP 3: Add Instagram Product
- In app dashboard, find "Add Product"
- Search for and add "Instagram Graph API"

STEP 4: Get Instagram Business Account
- You need a Facebook Page connected to Instagram
- Go to App Roles → Business Accounts
- Select your Instagram business account

STEP 5: Generate Access Token
- Go to Settings → Basic
- Find "App ID" and "App Secret"
- Go to Tools → Graph API Explorer
- Switch to your app
- Get the "Page Access Token"

STEP 6: Get Instagram Business Account ID
- In Graph API Explorer:
  - Query: GET /me/instagram_business_accounts
  - Copy the business_account id returned

STEP 7: Paste Below
"""
        ttk.Label(frame, text=instructions, justify="left", font=("Courier", 9)).pack(anchor="w", pady=10)
        
        ttk.Button(frame, text="📌 Open Meta Developers Console", command=lambda: webbrowser.open(
            "https://developers.facebook.com/apps"
        )).pack(anchor="w", pady=10)
        
        ttk.Label(frame, text="Instagram Access Token:").pack(anchor="w", pady=(20, 5))
        self.instagram_token_entry = ttk.Entry(frame, width=60, show="*")
        self.instagram_token_entry.pack(anchor="w", pady=5)
        
        ttk.Label(frame, text="Instagram Business Account ID:").pack(anchor="w", pady=(10, 5))
        self.instagram_id_entry = ttk.Entry(frame, width=60)
        self.instagram_id_entry.pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="✓ Save & Next", command=lambda: self._save_instagram()).pack(anchor="w", pady=10)
    
    def _build_youtube_tab(self, notebook):
        """YouTube API setup"""
        frame = ttk.Frame(notebook, padding=15)
        notebook.add(frame, text="4. YouTube API")
        
        ttk.Label(frame, text="YouTube Data API Setup", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        instructions = """
STEP 1: Go to Google Cloud Console
Click the button below:

STEP 2: Create a New Project
- Click "Select a Project" at top
- Click "New Project"
- Name it "FitSweetTreat" or similar

STEP 3: Enable YouTube Data API v3
- Search for "YouTube Data API v3"
- Click it and press "Enable"

STEP 4: Create OAuth Credentials
- Go to "Credentials" in left menu
- Click "Create Credentials" → "OAuth 2.0 Client ID"
- Choose "Desktop Application"
- Download the JSON file

STEP 5: Get Your Channel ID
- Go to YouTube Studio (youtube.com/studio)
- Click your profile → "Settings"
- Go to "Channel" → "Advanced settings"
- Copy your Channel ID (looks like: UCxxx...)

STEP 6: Paste Below
Copy values from OAuth JSON file
"""
        ttk.Label(frame, text=instructions, justify="left", font=("Courier", 9)).pack(anchor="w", pady=10)
        
        ttk.Button(frame, text="📌 Open Google Cloud Console", command=lambda: webbrowser.open(
            "https://console.cloud.google.com/apis/dashboard"
        )).pack(anchor="w", pady=10)
        
        ttk.Label(frame, text="YouTube API Key (from OAuth JSON):").pack(anchor="w", pady=(20, 5))
        self.youtube_key_entry = ttk.Entry(frame, width=60)
        self.youtube_key_entry.pack(anchor="w", pady=5)
        
        ttk.Label(frame, text="YouTube Channel ID:").pack(anchor="w", pady=(10, 5))
        self.youtube_channel_entry = ttk.Entry(frame, width=60)
        self.youtube_channel_entry.pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="✓ Save & Next", command=lambda: self._save_youtube()).pack(anchor="w", pady=10)
    
    def _build_summary_tab(self, notebook):
        """Summary and save"""
        frame = ttk.Frame(notebook, padding=15)
        notebook.add(frame, text="5. Summary")
        
        ttk.Label(frame, text="Credential Summary", font=("Arial", 12, "bold")).pack(anchor="w", pady=10)
        
        info = """
You have successfully entered all credentials!

These will be encrypted and stored locally in:
  credentials.vault

The encryption key is stored in:
  .vault_key

⚠️  IMPORTANT:
- Never share your credentials with anyone
- Keep .vault_key file safe
- You can't recover credentials if you lose the key
- Back up .vault_key in a safe location

Your credentials are ready to use in the app.
Click "Save All & Exit" to finish.
"""
        ttk.Label(frame, text=info, justify="left", font=("Courier", 9)).pack(anchor="w", pady=10)
        
        ttk.Button(frame, text="💾 Save All & Exit", command=self._save_all).pack(anchor="w", pady=10)
    
    def _save_gemini(self):
        value = self.gemini_entry.get()
        if not value:
            messagebox.showwarning("Input", "Please enter Gemini API Key")
            return
        self.credentials["gemini_api_key"] = value
        messagebox.showinfo("Saved", "Gemini API Key saved!")
    
    def _save_tiktok(self):
        key = self.tiktok_key_entry.get()
        secret = self.tiktok_secret_entry.get()
        token = self.tiktok_token_entry.get()
        
        if not all([key, secret, token]):
            messagebox.showwarning("Input", "Please enter all TikTok credentials")
            return
        
        self.credentials["tiktok_api_key"] = key
        self.credentials["tiktok_api_secret"] = secret
        self.credentials["tiktok_access_token"] = token
        messagebox.showinfo("Saved", "TikTok credentials saved!")
    
    def _save_instagram(self):
        token = self.instagram_token_entry.get()
        bid = self.instagram_id_entry.get()
        
        if not all([token, bid]):
            messagebox.showwarning("Input", "Please enter Instagram token and account ID")
            return
        
        self.credentials["instagram_api_token"] = token
        self.credentials["instagram_business_id"] = bid
        messagebox.showinfo("Saved", "Instagram credentials saved!")
    
    def _save_youtube(self):
        key = self.youtube_key_entry.get()
        channel = self.youtube_channel_entry.get()
        
        if not all([key, channel]):
            messagebox.showwarning("Input", "Please enter YouTube API key and channel ID")
            return
        
        self.credentials["youtube_api_key"] = key
        self.credentials["youtube_channel_id"] = channel
        messagebox.showinfo("Saved", "YouTube credentials saved!")
    
    def _save_all(self):
        """Save all credentials and close"""
        from video_automation_app import CredentialVault
        
        vault = CredentialVault()
        vault.save_credentials(self.credentials)
        
        messagebox.showinfo("Success", "All credentials encrypted and saved!\n\nYou can now run the main app.")
        self.root.destroy()
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    wizard = CredentialWizard()
    wizard.run()
