#!/usr/bin/env python
"""
FitSweetTreat Video Automation - Quick Start

This script sets up everything you need to run the app:
1. Checks if credentials are configured
2. Launches credential wizard if needed
3. Starts the main app
"""

import sys
import subprocess
from pathlib import Path


def main():
    print("=" * 60)
    print("🎬 FitSweetTreat Video Automation - Starting Up")
    print("=" * 60)
    
    root_dir = Path(__file__).resolve().parent
    
    # Check if credentials exist
    creds_file = root_dir / "credentials.vault"
    
    if not creds_file.exists():
        print("\n🔐 No credentials found!")
        print("Launching credential wizard...\n")
        
        try:
            subprocess.run([sys.executable, str(root_dir / "credential_wizard.py")], check=True)
        except Exception as e:
            print(f"❌ Credential wizard failed: {e}")
            print("\nPlease run: python credential_wizard.py")
            return
    
    # Launch main app
    print("\n✅ Launching FitSweetTreat App...")
    try:
        subprocess.run([sys.executable, str(root_dir / "video_automation_app.py")], check=True)
    except Exception as e:
        print(f"❌ App launch failed: {e}")
        return


if __name__ == "__main__":
    main()
