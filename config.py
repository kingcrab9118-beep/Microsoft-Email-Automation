"""
Configuration management for Microsoft 365 Email Automation System
Loads settings from environment variables with validation
"""

import os
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Configuration class that loads and validates environment variables"""
    
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()
        
        # Microsoft Graph API Configuration
        self.microsoft_tenant_id = self._get_required_env("MICROSOFT_TENANT_ID")
        self.microsoft_client_id = self._get_required_env("MICROSOFT_CLIENT_ID")
        self.microsoft_client_secret = self._get_required_env("MICROSOFT_CLIENT_SECRET")
        self.sender_email = self._get_required_env("SENDER_EMAIL")
        
        # Authentication method: 'client_credentials' or 'delegated'
        self.auth_method = os.getenv("AUTH_METHOD", "client_credentials")
        if self.auth_method not in ["client_credentials", "delegated"]:
            raise ValueError("AUTH_METHOD must be 'client_credentials' or 'delegated'")
        
        # Database Configuration
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///email_automation.db")
        
        # Rate Limiting Configuration
        self.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
        self.rate_limit_per_day = int(os.getenv("RATE_LIMIT_PER_DAY", "10000"))
        
        # Email Sequence Configuration
        self.follow_up_1_delay_days = int(os.getenv("FOLLOW_UP_1_DELAY_DAYS", "14"))
        self.follow_up_2_enabled = os.getenv("FOLLOW_UP_2_ENABLED", "true").lower() == "true"
        self.follow_up_2_delay_days = int(os.getenv("FOLLOW_UP_2_DELAY_DAYS", "10"))
        
        # Reply Detection Configuration
        self.reply_check_interval_minutes = int(os.getenv("REPLY_CHECK_INTERVAL_MINUTES", "15"))
        
        # Microsoft Graph API Scopes
        if self.auth_method == "client_credentials":
            self.scopes = ["https://graph.microsoft.com/.default"]
        else:
            self.scopes = [
                "https://graph.microsoft.com/Mail.Send",
                "https://graph.microsoft.com/Mail.Read",
                "https://graph.microsoft.com/User.Read"
            ]
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error"""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value
    
    @property
    def graph_api_base_url(self) -> str:
        """Microsoft Graph API base URL"""
        return "https://graph.microsoft.com/v1.0"
    
    @property
    def authority_url(self) -> str:
        """Microsoft authority URL for authentication"""
        return f"https://login.microsoftonline.com/{self.microsoft_tenant_id}"
    
    def validate_configuration(self) -> bool:
        """Validate all configuration settings"""
        try:
            # Check required fields are not empty
            required_fields = [
                self.microsoft_tenant_id,
                self.microsoft_client_id,
                self.microsoft_client_secret,
                self.sender_email
            ]
            
            if not all(required_fields):
                return False
            
            # Validate email format (basic check)
            if "@" not in self.sender_email:
                return False
            
            # Validate numeric values
            if self.rate_limit_per_minute <= 0 or self.rate_limit_per_day <= 0:
                return False
            
            if self.follow_up_1_delay_days <= 0 or self.follow_up_2_delay_days <= 0:
                return False
            
            return True
            
        except Exception:
            return False