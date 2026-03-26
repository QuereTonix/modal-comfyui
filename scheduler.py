"""
Scheduling engine for automatic posting at specified times
"""

import threading
import schedule
import time
from datetime import datetime, time as dt_time
from pathlib import Path


class PostingScheduler:
    """Manage scheduled posts across multiple platforms"""
    
    def __init__(self, db, social_media_scheduler, schedule_config):
        self.db = db
        self.social_media = social_media_scheduler
        self.schedule_config = schedule_config
        self.running = False
        self.scheduler_thread = None
    
    def start(self):
        """Start the scheduler in background"""
        if self.running:
            return
        
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
    
    def _run_scheduler(self):
        """Main scheduler loop"""
        # Load schedule config
        config = self.schedule_config.get_schedule()
        
        # Schedule jobs for each platform
        for platform, settings in config.get("platforms", {}).items():
            for post_time in settings.get("times", []):
                schedule.every().day.at(post_time).do(
                    self._post_from_queue, platform
                )
        
        # Run the scheduler
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def _post_from_queue(self, platform):
        """Post next approved video from queue"""
        # Get next approved video
        conn_str = "SELECT * FROM video_queue WHERE status='approved' ORDER BY approved_at ASC LIMIT 1"
        
        try:
            # Query would come from db.execute()
            # For now, this is a placeholder showing the structure
            
            # Video should have:
            # - id
            # - recipe_name
            # - final_video_path
            # - created_at
            
            # Then call social_media.post_to_all_platforms()
            # Update status to 'posted'
            
            pass
        except Exception as e:
            # Log error
            pass
    
    def schedule_immediate_post(self, video_id, platforms=["tiktok", "instagram", "youtube"]):
        """Immediately post without waiting for scheduled time"""
        threading.Thread(
            target=self._do_immediate_post,
            args=(video_id, platforms),
            daemon=True
        ).start()
    
    def _do_immediate_post(self, video_id, platforms):
        """Execute immediate post"""
        try:
            # Get video from database
            # Call social_media.post_to_all_platforms()
            # Update status to 'posted'
            pass
        except Exception as e:
            # Log error
            pass


class TimeHelper:
    """Utility for time/timezone handling"""
    
    @staticmethod
    def get_next_post_time(post_time_str, timezone_str="America/New_York"):
        """Calculate next posting time"""
        from datetime import datetime, timedelta
        import pytz
        
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        
        # Parse HH:MM
        hour, minute = map(int, post_time_str.split(":"))
        
        # Create datetime for today at specified time
        next_post = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time has passed, move to tomorrow
        if next_post <= now:
            next_post += timedelta(days=1)
        
        return next_post
    
    @staticmethod
    def is_time_to_post(post_time_str, timezone_str="America/New_York"):
        """Check if current time matches posting time"""
        from datetime import datetime, timedelta
        import pytz
        
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        
        # Parse HH:MM
        hour, minute = map(int, post_time_str.split(":"))
        
        # Check if current time is within 1 minute window of post time
        post_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        time_diff = abs((now - post_dt).total_seconds())
        
        return time_diff < 60
