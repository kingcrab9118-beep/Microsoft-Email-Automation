"""
Email sender implementation using Microsoft Graph API
Handles email composition, sending, and tracking
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from auth.graph_auth import GraphAPIClient
from db.models import Recipient, EmailSequence
from .template_engine import EmailTemplateEngine
from config import Config


class EmailSender:
    """Handles email sending via Microsoft Graph API"""
    
    def __init__(self, config: Config, graph_client: GraphAPIClient):
        self.config = config
        self.graph_client = graph_client
        self.template_engine = EmailTemplateEngine()
        self.logger = logging.getLogger(__name__)
    
    async def send_email(self, recipient: Recipient, step: int, custom_variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send personalized email to recipient"""
        try:
            # Render email content
            email_content = self.template_engine.render_email(step, recipient, custom_variables)
            
            # Create Graph API message payload
            message_payload = self._create_message_payload(
                recipient=recipient,
                subject=email_content['subject'],
                html_content=email_content['html_content']
            )
            
            # Send email via Graph API
            response = await self._send_via_graph_api(message_payload)
            
            # Extract message ID from response
            message_id = self._extract_message_id(response)
            
            result = {
                'success': True,
                'message_id': message_id,
                'recipient_email': recipient.email,
                'step': step,
                'sent_at': datetime.now(),
                'subject': email_content['subject']
            }
            
            self.logger.info(f"Successfully sent email step {step} to {recipient.email} (Message ID: {message_id})")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to send email step {step} to {recipient.email}: {e}")
            return {
                'success': False,
                'error': str(e),
                'recipient_email': recipient.email,
                'step': step
            }
    
    def _create_message_payload(self, recipient: Recipient, subject: str, html_content: str) -> Dict[str, Any]:
        """Create Microsoft Graph API message payload"""
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_content
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": recipient.email,
                            "name": f"{recipient.first_name} ({recipient.role} at {recipient.company})"
                        }
                    }
                ],
                "from": {
                    "emailAddress": {
                        "address": self.config.sender_email,
                        "name": "[Your Name]"  # TODO: Make this configurable
                    }
                },
                "importance": "normal",
                "isDeliveryReceiptRequested": False,
                "isReadReceiptRequested": False
            },
            "saveToSentItems": True
        }
        
        return payload
    
    async def _send_via_graph_api(self, message_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send email via Microsoft Graph API"""
        try:
            # Use the sendMail endpoint
            endpoint = f"users/{self.config.sender_email}/sendMail"
            response = await self.graph_client.post(endpoint, message_payload)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Graph API send request failed: {e}")
            raise
    
    def _extract_message_id(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract message ID from Graph API response"""
        # The sendMail endpoint doesn't return a message ID directly
        # We need to generate a tracking ID or use a different approach
        # For now, we'll generate a unique identifier based on timestamp
        import uuid
        return str(uuid.uuid4())
    
    async def send_test_email(self, test_recipient_email: str) -> Dict[str, Any]:
        """Send a test email to verify configuration"""
        try:
            # Create test recipient
            test_recipient = Recipient(
                first_name="Test",
                company="Test Company",
                role="Test Role",
                email=test_recipient_email
            )
            
            # Create simple test message
            test_payload = {
                "message": {
                    "subject": "Email Automation System - Test Email",
                    "body": {
                        "contentType": "HTML",
                        "content": """
                        <html>
                        <body>
                            <h2>Email Automation System Test</h2>
                            <p>This is a test email from the Microsoft 365 Email Automation System.</p>
                            <p>If you received this email, the system is configured correctly and can send emails via Microsoft Graph API.</p>
                            <p><strong>Test Details:</strong></p>
                            <ul>
                                <li>Sent at: {}</li>
                                <li>Sender: {}</li>
                                <li>Authentication: {}</li>
                            </ul>
                            <p>You can safely delete this email.</p>
                        </body>
                        </html>
                        """.format(
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            self.config.sender_email,
                            self.config.auth_method
                        )
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": test_recipient_email,
                                "name": "Test Recipient"
                            }
                        }
                    ]
                },
                "saveToSentItems": True
            }
            
            # Send test email
            endpoint = f"users/{self.config.sender_email}/sendMail"
            response = await self.graph_client.post(endpoint, test_payload)
            
            self.logger.info(f"Test email sent successfully to {test_recipient_email}")
            
            return {
                'success': True,
                'message': f'Test email sent to {test_recipient_email}',
                'sent_at': datetime.now()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to send test email: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def validate_sender_email(self) -> bool:
        """Validate that the configured sender email is accessible"""
        try:
            # Try to get user profile for the sender email
            endpoint = f"users/{self.config.sender_email}"
            response = await self.graph_client.get(endpoint)
            
            if response and 'mail' in response:
                self.logger.info(f"Sender email validation successful: {self.config.sender_email}")
                return True
            else:
                self.logger.error(f"Sender email validation failed: {self.config.sender_email}")
                return False
                
        except Exception as e:
            self.logger.error(f"Sender email validation error: {e}")
            return False
    
    def get_email_preview(self, recipient: Recipient, step: int, custom_variables: Dict[str, Any] = None) -> Dict[str, str]:
        """Get preview of email without sending"""
        try:
            return self.template_engine.render_email(step, recipient, custom_variables)
        except Exception as e:
            self.logger.error(f"Failed to generate email preview: {e}")
            raise
    
    async def get_sending_statistics(self) -> Dict[str, Any]:
        """Get email sending statistics (placeholder for future implementation)"""
        # This would typically query the database for sending stats
        # For now, return basic info
        return {
            'sender_email': self.config.sender_email,
            'auth_method': self.config.auth_method,
            'templates_available': len(self.template_engine.template_files),
            'rate_limit_per_minute': self.config.rate_limit_per_minute
        }


class EmailBatch:
    """Handles batch email operations"""
    
    def __init__(self, email_sender: EmailSender):
        self.email_sender = email_sender
        self.logger = logging.getLogger(__name__)
    
    async def send_batch(self, email_sequences: list, max_concurrent: int = 5) -> Dict[str, Any]:
        """Send multiple emails with concurrency control"""
        import asyncio
        
        results = {
            'total': len(email_sequences),
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def send_single_email(sequence_data):
            async with semaphore:
                try:
                    recipient, step, custom_vars = sequence_data
                    result = await self.email_sender.send_email(recipient, step, custom_vars)
                    
                    if result['success']:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'recipient': recipient.email,
                            'error': result.get('error', 'Unknown error')
                        })
                    
                    return result
                    
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'recipient': sequence_data[0].email if sequence_data else 'Unknown',
                        'error': str(e)
                    })
                    return {'success': False, 'error': str(e)}
        
        # Execute batch sending
        tasks = [send_single_email(seq) for seq in email_sequences]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.logger.info(f"Batch sending completed: {results['successful']} successful, {results['failed']} failed")
        
        return results