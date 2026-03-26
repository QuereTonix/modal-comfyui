"""
Social media platform integrations
TikTok, Instagram, YouTube publishing
"""

import requests
import json
from pathlib import Path


class TikTokAPI:
    """TikTok API integration"""
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://open-api.tiktok.com/v1"
    
    def upload_video(self, video_path, caption=""):
        """Upload video to TikTok"""
        try:
            with open(video_path, "rb") as f:
                files = {"video": f}
                data = {
                    "access_token": self.api_key,
                    "video_title": caption[:150],
                    "video_description": caption
                }
                response = requests.post(
                    f"{self.base_url}/video/upload/",
                    files=files,
                    data=data,
                    timeout=300
                )
                if response.status_code == 200:
                    return response.json().get("data", {}).get("video_id")
                else:
                    raise Exception(f"TikTok API error: {response.text}")
        except Exception as e:
            raise Exception(f"TikTok upload failed: {str(e)}")
    
    def publish_video(self, video_id):
        """Publish uploaded video"""
        try:
            data = {
                "access_token": self.api_key,
                "video_id": video_id,
                "privacy_level": "PUBLIC"
            }
            response = requests.post(
                f"{self.base_url}/video/publish/",
                json=data,
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            raise Exception(f"TikTok publish failed: {str(e)}")


class InstagramAPI:
    """Instagram Graph API integration"""
    
    def __init__(self, access_token, business_account_id):
        self.access_token = access_token
        self.business_account_id = business_account_id
        self.base_url = "https://graph.instagram.com/v18.0"
    
    def upload_video(self, video_path, caption=""):
        """Upload video to Instagram"""
        try:
            with open(video_path, "rb") as f:
                files = {"file": f}
                params = {
                    "access_token": self.access_token,
                    "caption": caption,
                    "media_type": "VIDEO"
                }
                response = requests.post(
                    f"{self.base_url}/{self.business_account_id}/media",
                    files=files,
                    params=params,
                    timeout=300
                )
                if response.status_code == 200:
                    return response.json().get("id")
                else:
                    raise Exception(f"Instagram API error: {response.text}")
        except Exception as e:
            raise Exception(f"Instagram upload failed: {str(e)}")
    
    def publish_video(self, media_id):
        """Publish uploaded video"""
        try:
            params = {"access_token": self.access_token}
            response = requests.post(
                f"{self.base_url}/{self.business_account_id}/media_publish",
                json={"creation_id": media_id},
                params=params,
                timeout=30
            )
            return response.status_code == 200
        except Exception as e:
            raise Exception(f"Instagram publish failed: {str(e)}")


class YouTubeAPI:
    """YouTube Data API integration"""
    
    def __init__(self, api_key, channel_id):
        self.api_key = api_key
        self.channel_id = channel_id
        self.base_url = "https://www.googleapis.com/youtube/v3"
    
    def upload_video(self, video_path, title="", description=""):
        """Upload video to YouTube"""
        try:
            # This requires OAuth flow for actual upload
            # For now, returns a placeholder
            raise NotImplementedError("YouTube upload requires OAuth setup")
        except Exception as e:
            raise Exception(f"YouTube upload failed: {str(e)}")
    
    def get_upload_url(self):
        """Get resumable upload URL"""
        headers = {"X-Goog-Upload-Protocol": "resumable"}
        params = {
            "part": "snippet,status",
            "key": self.api_key,
            "uploadType": "resumable"
        }
        try:
            response = requests.post(
                f"{self.base_url}/videos",
                headers=headers,
                params=params,
                timeout=30
            )
            return response.headers.get("location")
        except Exception as e:
            raise Exception(f"YouTube URL retrieval failed: {str(e)}")


class SocialMediaScheduler:
    """Manage scheduled posting to all platforms"""
    
    def __init__(self, credentials):
        self.tiktok = TikTokAPI(credentials.get("tiktok_api_key", ""))
        self.instagram = InstagramAPI(
            credentials.get("instagram_api_token", ""),
            credentials.get("instagram_business_id", "")
        )
        self.youtube = YouTubeAPI(
            credentials.get("youtube_api_key", ""),
            credentials.get("youtube_channel_id", "")
        )
    
    def post_to_all_platforms(self, video_path, caption="", platforms=["tiktok", "instagram", "youtube"]):
        """Post video to specified platforms"""
        results = {}
        
        if "tiktok" in platforms:
            try:
                video_id = self.tiktok.upload_video(video_path, caption)
                self.tiktok.publish_video(video_id)
                results["tiktok"] = "success"
            except Exception as e:
                results["tiktok"] = f"error: {str(e)}"
        
        if "instagram" in platforms:
            try:
                media_id = self.instagram.upload_video(video_path, caption)
                self.instagram.publish_video(media_id)
                results["instagram"] = "success"
            except Exception as e:
                results["instagram"] = f"error: {str(e)}"
        
        if "youtube" in platforms:
            try:
                url = self.youtube.get_upload_url()
                results["youtube"] = f"upload_url: {url}"
            except Exception as e:
                results["youtube"] = f"error: {str(e)}"
        
        return results
