"""
Microsoft Graph API OAuth2 authentication module
Supports both client credentials and delegated authentication flows
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

import msal
import requests

from config import Config


class GraphAuthenticator:
    """Handles OAuth2 authentication with Microsoft Graph API"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize MSAL application
        self.app = msal.ConfidentialClientApplication(
            client_id=config.microsoft_client_id,
            client_credential=config.microsoft_client_secret,
            authority=config.authority_url
        )
        
        # Token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._token_cache: Dict[str, Any] = {}
    
    async def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary"""
        try:
            # Check if current token is still valid
            if self._is_token_valid():
                return self._access_token
            
            # Get new token based on authentication method
            if self.config.auth_method == "client_credentials":
                token_data = await self._authenticate_client_credentials()
            elif self.config.auth_method == "delegated":
                token_data = await self._authenticate_delegated()
            else:
                raise ValueError(f"Unsupported authentication method: {self.config.auth_method}")
            
            # Cache the token
            self._cache_token(token_data)
            
            self.logger.info(f"Successfully obtained access token using {self.config.auth_method} flow")
            return self._access_token
            
        except Exception as e:
            self.logger.error(f"Failed to obtain access token: {e}")
            raise
    
    async def _authenticate_client_credentials(self) -> Dict[str, Any]:
        """Authenticate using client credentials flow (app-only)"""
        try:
            # Acquire token for client credentials flow
            result = self.app.acquire_token_for_client(scopes=self.config.scopes)
            
            if "access_token" not in result:
                error_msg = result.get("error_description", "Unknown authentication error")
                raise Exception(f"Client credentials authentication failed: {error_msg}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Client credentials authentication failed: {e}")
            raise
    
    async def _authenticate_delegated(self) -> Dict[str, Any]:
        """Authenticate using delegated flow (user context)"""
        try:
            # First, try to get token from cache
            accounts = self.app.get_accounts()
            
            if accounts:
                # Try silent authentication first
                result = self.app.acquire_token_silent(
                    scopes=self.config.scopes,
                    account=accounts[0]
                )
                
                if result and "access_token" in result:
                    return result
            
            # If silent auth fails, need interactive authentication
            # For production, you would implement device code flow or other appropriate method
            raise NotImplementedError(
                "Interactive authentication not implemented. "
                "For delegated authentication, please implement device code flow or use client credentials."
            )
            
        except Exception as e:
            self.logger.error(f"Delegated authentication failed: {e}")
            raise
    
    def _cache_token(self, token_data: Dict[str, Any]):
        """Cache token data"""
        self._access_token = token_data["access_token"]
        
        # Calculate expiration time (subtract 5 minutes for safety)
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
        
        # Store full token data for potential refresh
        self._token_cache = token_data
    
    def _is_token_valid(self) -> bool:
        """Check if current token is still valid"""
        if not self._access_token or not self._token_expires_at:
            return False
        
        return datetime.now() < self._token_expires_at
    
    async def validate_token(self) -> bool:
        """Validate current token by making a test API call"""
        try:
            token = await self.get_access_token()
            
            # Make a simple API call to validate token
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Test with a simple user profile call (works for both auth methods)
            response = requests.get(
                f"{self.config.graph_api_base_url}/me",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                self.logger.info("Token validation successful")
                return True
            else:
                self.logger.warning(f"Token validation failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Token validation error: {e}")
            return False
    
    async def get_authenticated_headers(self) -> Dict[str, str]:
        """Get headers with authentication for API requests"""
        token = await self.get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def clear_token_cache(self):
        """Clear cached token data"""
        self._access_token = None
        self._token_expires_at = None
        self._token_cache = {}
        self.logger.info("Token cache cleared")
    
    async def test_permissions(self) -> Dict[str, bool]:
        """Test required permissions for the application"""
        permissions_status = {
            'mail_send': False,
            'mail_read': False,
            'user_read': False
        }
        
        try:
            headers = await self.get_authenticated_headers()
            
            # Test Mail.Send permission by checking if we can access mail settings
            try:
                response = requests.get(
                    f"{self.config.graph_api_base_url}/me/mailboxSettings",
                    headers=headers,
                    timeout=10
                )
                permissions_status['mail_send'] = response.status_code == 200
            except Exception:
                pass
            
            # Test Mail.Read permission by checking if we can access messages
            try:
                response = requests.get(
                    f"{self.config.graph_api_base_url}/me/messages?$top=1",
                    headers=headers,
                    timeout=10
                )
                permissions_status['mail_read'] = response.status_code == 200
            except Exception:
                pass
            
            # Test User.Read permission
            try:
                response = requests.get(
                    f"{self.config.graph_api_base_url}/me",
                    headers=headers,
                    timeout=10
                )
                permissions_status['user_read'] = response.status_code == 200
            except Exception:
                pass
            
            self.logger.info(f"Permission test results: {permissions_status}")
            return permissions_status
            
        except Exception as e:
            self.logger.error(f"Permission testing failed: {e}")
            return permissions_status


class GraphAPIClient:
    """HTTP client for Microsoft Graph API with authentication"""
    
    def __init__(self, authenticator: GraphAuthenticator):
        self.authenticator = authenticator
        self.config = authenticator.config
        self.logger = logging.getLogger(__name__)
        self.base_url = self.config.graph_api_base_url
    
    async def get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated GET request"""
        headers = await self.authenticator.get_authenticated_headers()
        
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                headers=headers,
                params=params,
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"GET request failed for {endpoint}: {e}")
            raise
    
    async def post(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated POST request"""
        headers = await self.authenticator.get_authenticated_headers()
        
        try:
            response = requests.post(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                headers=headers,
                json=data,
                timeout=30
            )
            
            response.raise_for_status()
            
            # Some POST requests don't return JSON content
            if response.content:
                return response.json()
            else:
                return {"status": "success"}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"POST request failed for {endpoint}: {e}")
            raise
    
    async def patch(self, endpoint: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated PATCH request"""
        headers = await self.authenticator.get_authenticated_headers()
        
        try:
            response = requests.patch(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                headers=headers,
                json=data,
                timeout=30
            )
            
            response.raise_for_status()
            
            if response.content:
                return response.json()
            else:
                return {"status": "success"}
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"PATCH request failed for {endpoint}: {e}")
            raise