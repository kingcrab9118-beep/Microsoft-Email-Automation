"""
Authentication configuration validation and setup verification
"""

import logging
from typing import Dict, List, Tuple

from config import Config
from .graph_auth import GraphAuthenticator


class AuthenticationValidator:
    """Validates authentication configuration and setup"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate authentication configuration"""
        errors = []
        
        # Check required environment variables
        required_vars = [
            ('MICROSOFT_TENANT_ID', self.config.microsoft_tenant_id),
            ('MICROSOFT_CLIENT_ID', self.config.microsoft_client_id),
            ('MICROSOFT_CLIENT_SECRET', self.config.microsoft_client_secret),
            ('SENDER_EMAIL', self.config.sender_email)
        ]
        
        for var_name, var_value in required_vars:
            if not var_value or var_value.startswith('your-'):
                errors.append(f"{var_name} is not properly configured (still contains placeholder value)")
        
        # Validate authentication method
        if self.config.auth_method not in ['client_credentials', 'delegated']:
            errors.append(f"Invalid AUTH_METHOD: {self.config.auth_method}. Must be 'client_credentials' or 'delegated'")
        
        # Validate email format
        if self.config.sender_email and '@' not in self.config.sender_email:
            errors.append("SENDER_EMAIL is not a valid email address")
        
        # Validate tenant ID format (basic check)
        if self.config.microsoft_tenant_id and len(self.config.microsoft_tenant_id) < 10:
            errors.append("MICROSOFT_TENANT_ID appears to be invalid (too short)")
        
        # Validate client ID format (basic check)
        if self.config.microsoft_client_id and len(self.config.microsoft_client_id) < 10:
            errors.append("MICROSOFT_CLIENT_ID appears to be invalid (too short)")
        
        success = len(errors) == 0
        
        if success:
            self.logger.info("Authentication configuration validation passed")
        else:
            self.logger.error(f"Authentication configuration validation failed: {errors}")
        
        return success, errors
    
    async def test_authentication(self) -> Tuple[bool, Dict[str, any]]:
        """Test authentication by attempting to get a token and validate permissions"""
        test_results = {
            'token_acquired': False,
            'token_valid': False,
            'permissions': {},
            'errors': []
        }
        
        try:
            # Create authenticator
            authenticator = GraphAuthenticator(self.config)
            
            # Test token acquisition
            try:
                token = await authenticator.get_access_token()
                test_results['token_acquired'] = True
                self.logger.info("Successfully acquired access token")
                
                # Test token validation
                token_valid = await authenticator.validate_token()
                test_results['token_valid'] = token_valid
                
                if token_valid:
                    # Test permissions
                    permissions = await authenticator.test_permissions()
                    test_results['permissions'] = permissions
                    
                    # Check if all required permissions are available
                    required_permissions = ['mail_send', 'mail_read']
                    missing_permissions = [
                        perm for perm in required_permissions 
                        if not permissions.get(perm, False)
                    ]
                    
                    if missing_permissions:
                        test_results['errors'].append(
                            f"Missing required permissions: {missing_permissions}"
                        )
                else:
                    test_results['errors'].append("Token validation failed")
                    
            except Exception as e:
                test_results['errors'].append(f"Token acquisition failed: {str(e)}")
                self.logger.error(f"Token acquisition failed: {e}")
        
        except Exception as e:
            test_results['errors'].append(f"Authentication test failed: {str(e)}")
            self.logger.error(f"Authentication test failed: {e}")
        
        success = (
            test_results['token_acquired'] and 
            test_results['token_valid'] and 
            len(test_results['errors']) == 0
        )
        
        return success, test_results
    
    def get_setup_instructions(self) -> str:
        """Get detailed setup instructions for Microsoft Graph API"""
        instructions = """
Microsoft Graph API Setup Instructions
=====================================

1. Azure App Registration Setup:
   a. Go to Azure Portal (https://portal.azure.com)
   b. Navigate to "Azure Active Directory" > "App registrations"
   c. Click "New registration"
   d. Enter application name (e.g., "Email Automation System")
   e. Select "Accounts in this organizational directory only"
   f. Click "Register"

2. Configure Authentication:
   a. In your app registration, go to "Authentication"
   b. For client credentials flow: No additional setup needed
   c. For delegated flow: Add redirect URIs as needed

3. Configure API Permissions:
   a. Go to "API permissions"
   b. Click "Add a permission" > "Microsoft Graph"
   
   For Client Credentials (Application permissions):
   - Mail.Send (to send emails)
   - Mail.Read (to read mailbox for replies)
   
   For Delegated (Delegated permissions):
   - Mail.Send (to send emails on behalf of user)
   - Mail.Read (to read user's mailbox)
   - User.Read (to read user profile)
   
   c. Click "Grant admin consent" (required for application permissions)

4. Create Client Secret:
   a. Go to "Certificates & secrets"
   b. Click "New client secret"
   c. Enter description and select expiration
   d. Copy the secret value (you won't see it again!)

5. Get Configuration Values:
   a. Tenant ID: Found in "Overview" section
   b. Client ID: Found in "Overview" section (Application ID)
   c. Client Secret: The value you copied in step 4

6. Update Environment Variables:
   Copy .env.example to .env and update these values:
   - MICROSOFT_TENANT_ID=<your-tenant-id>
   - MICROSOFT_CLIENT_ID=<your-client-id>
   - MICROSOFT_CLIENT_SECRET=<your-client-secret>
   - SENDER_EMAIL=<email-address-that-will-send-emails>

7. Test Configuration:
   Run the authentication test to verify everything is working:
   python -c "from auth.validator import AuthenticationValidator; from config import Config; import asyncio; asyncio.run(AuthenticationValidator(Config()).test_authentication())"

Common Issues:
- "AADSTS70011": The provided request must include a 'scope' parameter
  Solution: Ensure you're using the correct scopes for your auth method
  
- "AADSTS65001": The user or administrator has not consented to use the application
  Solution: Grant admin consent for the required permissions
  
- "AADSTS700016": Application not found in directory
  Solution: Verify your tenant ID and client ID are correct
  
- "AADSTS7000215": Invalid client secret is provided
  Solution: Verify your client secret is correct and not expired
"""
        return instructions
    
    def print_configuration_status(self):
        """Print current configuration status"""
        print("\n" + "="*50)
        print("AUTHENTICATION CONFIGURATION STATUS")
        print("="*50)
        
        # Validate configuration
        config_valid, config_errors = self.validate_configuration()
        
        print(f"Configuration Valid: {'✓' if config_valid else '✗'}")
        
        if config_errors:
            print("\nConfiguration Errors:")
            for error in config_errors:
                print(f"  ✗ {error}")
        
        print(f"\nCurrent Settings:")
        print(f"  Tenant ID: {'✓' if self.config.microsoft_tenant_id and not self.config.microsoft_tenant_id.startswith('your-') else '✗'}")
        print(f"  Client ID: {'✓' if self.config.microsoft_client_id and not self.config.microsoft_client_id.startswith('your-') else '✗'}")
        print(f"  Client Secret: {'✓' if self.config.microsoft_client_secret and not self.config.microsoft_client_secret.startswith('your-') else '✗'}")
        print(f"  Sender Email: {'✓' if self.config.sender_email and not self.config.sender_email.startswith('sender@') else '✗'}")
        print(f"  Auth Method: {self.config.auth_method}")
        
        if not config_valid:
            print(f"\nTo fix configuration issues:")
            print(f"1. Copy .env.example to .env")
            print(f"2. Follow the setup instructions")
            print(f"3. Update the placeholder values in .env")
        
        print("="*50 + "\n")