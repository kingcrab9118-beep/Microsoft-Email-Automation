"""
Reply detection and tracking system
Monitors inbox for replies and manages sequence cancellation
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
import re

from auth.graph_auth import GraphAPIClient
from db.models import RecipientRepository, EmailSequenceRepository
from db.database import DatabaseManager
from config import Config


class ReplyTracker:
    """Monitors inbox for replies and manages sequence cancellation"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager, scheduler=None):
        self.config = config
        self.db_manager = db_manager
        self.scheduler = scheduler  # Will be set later to avoid circular imports
        self.logger = logging.getLogger(__name__)
        
        # Initialize repositories
        self.recipient_repo = RecipientRepository(db_manager)
        self.sequence_repo = EmailSequenceRepository(db_manager)
        
        # Graph API client will be injected
        self.graph_client: Optional[GraphAPIClient] = None
        
        # Reply detection settings
        self.check_interval = timedelta(minutes=config.reply_check_interval_minutes)
        self.last_check_time = datetime.now() - timedelta(hours=1)  # Start with 1 hour ago
        
        # Tracking data
        self.processed_message_ids: Set[str] = set()
        self.known_recipients: Dict[str, int] = {}  # email -> recipient_id mapping
        
        # Reply detection patterns
        self.reply_subject_patterns = [
            r'^RE:\s*',
            r'^Re:\s*',
            r'^re:\s*',
            r'^FW:\s*',
            r'^Fw:\s*',
            r'^fw:\s*',
            r'^FWD:\s*',
            r'^Fwd:\s*',
            r'^fwd:\s*'
        ]
        
        self.logger.info("Reply tracker initialized")
    
    def set_graph_client(self, graph_client: GraphAPIClient):
        """Set the Graph API client"""
        self.graph_client = graph_client
    
    def set_scheduler(self, scheduler):
        """Set the scheduler reference"""
        self.scheduler = scheduler
    
    async def start_monitoring(self):
        """Start the reply monitoring loop"""
        self.logger.info("Starting reply monitoring")
        
        # Load known recipients
        await self._load_known_recipients()
        
        # Start monitoring loop
        while True:
            try:
                await self.scan_inbox()
                await asyncio.sleep(self.check_interval.total_seconds())
                
            except Exception as e:
                self.logger.error(f"Error in reply monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def scan_inbox(self):
        """Scan inbox for new replies"""
        try:
            if not self.graph_client:
                self.logger.error("Graph API client not configured")
                return
            
            # Get messages since last check
            messages = await self._get_recent_messages()
            
            if not messages:
                self.logger.debug("No new messages found")
                return
            
            self.logger.info(f"Scanning {len(messages)} messages for replies")
            
            # Process each message
            replies_found = 0
            for message in messages:
                if await self._process_message(message):
                    replies_found += 1
            
            if replies_found > 0:
                self.logger.info(f"Detected {replies_found} replies")
            
            # Update last check time
            self.last_check_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Error scanning inbox: {e}")
    
    async def _get_recent_messages(self) -> List[Dict[str, Any]]:
        """Get messages from inbox since last check"""
        try:
            # Format datetime for Graph API
            since_time = self.last_check_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # Query parameters
            params = {
                '$filter': f"receivedDateTime ge {since_time}",
                '$select': 'id,subject,from,toRecipients,receivedDateTime,conversationId,internetMessageId,inReplyTo',
                '$orderby': 'receivedDateTime desc',
                '$top': 100  # Limit to prevent overwhelming
            }
            
            # Get messages from inbox
            endpoint = f"users/{self.config.sender_email}/mailFolders/inbox/messages"
            response = await self.graph_client.get(endpoint, params)
            
            messages = response.get('value', [])
            
            self.logger.debug(f"Retrieved {len(messages)} messages since {since_time}")
            return messages
            
        except Exception as e:
            self.logger.error(f"Error retrieving recent messages: {e}")
            return []
    
    async def _process_message(self, message: Dict[str, Any]) -> bool:
        """Process a single message to check if it's a reply"""
        try:
            message_id = message.get('id')
            
            # Skip if already processed
            if message_id in self.processed_message_ids:
                return False
            
            # Mark as processed
            self.processed_message_ids.add(message_id)
            
            # Check if this is a reply
            if await self._is_reply_message(message):
                # Identify the recipient who replied
                recipient_id = await self._identify_replying_recipient(message)
                
                if recipient_id:
                    # Handle the reply
                    await self._handle_reply(recipient_id, message)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error processing message {message.get('id', 'unknown')}: {e}")
            return False
    
    async def _is_reply_message(self, message: Dict[str, Any]) -> bool:
        """Determine if a message is a reply to our emails"""
        try:
            # Check 1: inReplyTo field
            in_reply_to = message.get('inReplyTo')
            if in_reply_to:
                # Check if this is a reply to one of our sent messages
                sequence = await self.sequence_repo.get_by_message_id(in_reply_to)
                if sequence:
                    self.logger.debug(f"Reply detected via inReplyTo field: {in_reply_to}")
                    return True
            
            # Check 2: Subject line patterns
            subject = message.get('subject', '')
            for pattern in self.reply_subject_patterns:
                if re.match(pattern, subject, re.IGNORECASE):
                    self.logger.debug(f"Reply detected via subject pattern: {subject}")
                    return True
            
            # Check 3: From address is a known recipient
            from_address = self._extract_email_address(message.get('from', {}))
            if from_address and from_address in self.known_recipients:
                self.logger.debug(f"Reply detected from known recipient: {from_address}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking if message is reply: {e}")
            return False
    
    async def _identify_replying_recipient(self, message: Dict[str, Any]) -> Optional[int]:
        """Identify which recipient sent the reply"""
        try:
            # Get sender email address
            from_address = self._extract_email_address(message.get('from', {}))
            
            if not from_address:
                return None
            
            # Look up recipient ID
            recipient_id = self.known_recipients.get(from_address.lower())
            
            if not recipient_id:
                # Try to find in database (in case cache is stale)
                recipient = await self.recipient_repo.get_by_email(from_address)
                if recipient:
                    recipient_id = recipient.id
                    self.known_recipients[from_address.lower()] = recipient_id
            
            return recipient_id
            
        except Exception as e:
            self.logger.error(f"Error identifying replying recipient: {e}")
            return None
    
    def _extract_email_address(self, from_field: Dict[str, Any]) -> Optional[str]:
        """Extract email address from Graph API from field"""
        try:
            email_address = from_field.get('emailAddress', {})
            return email_address.get('address', '').lower()
        except Exception:
            return None
    
    async def _handle_reply(self, recipient_id: int, message: Dict[str, Any]):
        """Handle a detected reply"""
        try:
            # Get recipient info
            recipient = await self.recipient_repo.get_by_id(recipient_id)
            if not recipient:
                self.logger.error(f"Recipient {recipient_id} not found")
                return
            
            # Log the reply
            from_address = self._extract_email_address(message.get('from', {}))
            subject = message.get('subject', '')
            received_time = message.get('receivedDateTime', '')
            
            self.logger.info(f"Reply detected from {from_address} (recipient {recipient_id}): {subject}")
            
            # Cancel future emails for this recipient
            if self.scheduler:
                cancelled_count = await self.scheduler.cancel_future_emails(recipient_id)
                self.logger.info(f"Cancelled {cancelled_count} future emails for recipient {recipient_id}")
            else:
                # Fallback: cancel directly via repository
                await self.sequence_repo.mark_replied(recipient_id)
                await self.recipient_repo.update_status(recipient_id, 'replied')
            
            # Store reply information (optional: for analytics)
            await self._store_reply_info(recipient_id, message)
            
        except Exception as e:
            self.logger.error(f"Error handling reply from recipient {recipient_id}: {e}")
    
    async def _store_reply_info(self, recipient_id: int, message: Dict[str, Any]):
        """Store reply information for analytics (optional)"""
        try:
            # This could be expanded to store detailed reply analytics
            # For now, just log the essential information
            reply_info = {
                'recipient_id': recipient_id,
                'message_id': message.get('id'),
                'subject': message.get('subject', ''),
                'received_at': message.get('receivedDateTime', ''),
                'conversation_id': message.get('conversationId', '')
            }
            
            self.logger.debug(f"Reply info stored: {reply_info}")
            
        except Exception as e:
            self.logger.error(f"Error storing reply info: {e}")
    
    async def _load_known_recipients(self):
        """Load known recipients into memory for faster lookup"""
        try:
            # Get all active recipients
            active_recipients = await self.recipient_repo.get_all_by_status('active')
            
            # Build email -> recipient_id mapping
            for recipient in active_recipients:
                self.known_recipients[recipient.email.lower()] = recipient.id
            
            self.logger.info(f"Loaded {len(self.known_recipients)} known recipients")
            
        except Exception as e:
            self.logger.error(f"Error loading known recipients: {e}")
    
    async def refresh_known_recipients(self):
        """Refresh the known recipients cache"""
        self.known_recipients.clear()
        await self._load_known_recipients()
    
    async def manual_reply_check(self, recipient_email: str) -> Dict[str, Any]:
        """Manually check for replies from a specific recipient"""
        try:
            # Get recent messages from this sender
            params = {
                '$filter': f"from/emailAddress/address eq '{recipient_email}'",
                '$select': 'id,subject,from,receivedDateTime,inReplyTo',
                '$orderby': 'receivedDateTime desc',
                '$top': 10
            }
            
            endpoint = f"users/{self.config.sender_email}/mailFolders/inbox/messages"
            response = await self.graph_client.get(endpoint, params)
            
            messages = response.get('value', [])
            
            result = {
                'recipient_email': recipient_email,
                'messages_found': len(messages),
                'replies_detected': 0,
                'messages': []
            }
            
            for message in messages:
                is_reply = await self._is_reply_message(message)
                
                message_info = {
                    'subject': message.get('subject', ''),
                    'received_at': message.get('receivedDateTime', ''),
                    'is_reply': is_reply
                }
                
                result['messages'].append(message_info)
                
                if is_reply:
                    result['replies_detected'] += 1
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in manual reply check for {recipient_email}: {e}")
            return {'error': str(e)}
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status"""
        return {
            'monitoring_active': True,
            'last_check_time': self.last_check_time.isoformat(),
            'check_interval_minutes': self.config.reply_check_interval_minutes,
            'known_recipients_count': len(self.known_recipients),
            'processed_messages_count': len(self.processed_message_ids),
            'reply_patterns_count': len(self.reply_subject_patterns)
        }
    
    async def test_reply_detection(self) -> Dict[str, Any]:
        """Test reply detection functionality"""
        try:
            # Test Graph API connectivity
            test_result = {
                'graph_api_connected': False,
                'inbox_accessible': False,
                'recent_messages_count': 0,
                'known_recipients_loaded': len(self.known_recipients) > 0,
                'error': None
            }
            
            if not self.graph_client:
                test_result['error'] = 'Graph API client not configured'
                return test_result
            
            # Test basic connectivity
            try:
                endpoint = f"users/{self.config.sender_email}/mailFolders/inbox"
                response = await self.graph_client.get(endpoint)
                test_result['graph_api_connected'] = True
                test_result['inbox_accessible'] = True
                
                # Test message retrieval
                messages = await self._get_recent_messages()
                test_result['recent_messages_count'] = len(messages)
                
            except Exception as e:
                test_result['error'] = str(e)
            
            return test_result
            
        except Exception as e:
            return {'error': str(e)}