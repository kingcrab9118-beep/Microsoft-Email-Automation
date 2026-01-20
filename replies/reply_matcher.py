"""
Advanced reply matching and sequence stopping logic
Handles complex reply detection scenarios and sequence management
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum

from db.models import EmailSequence, Recipient, EmailSequenceRepository, RecipientRepository


class ReplyConfidence(Enum):
    """Reply detection confidence levels"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ReplyMatch:
    """Represents a matched reply with confidence and metadata"""
    recipient_id: int
    message_id: str
    confidence: ReplyConfidence
    matching_method: str
    original_sequence_id: Optional[int] = None
    reply_subject: str = ""
    reply_timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = None


class ReplyMatcher:
    """Advanced reply matching with multiple detection methods"""
    
    def __init__(self, sequence_repo: EmailSequenceRepository, recipient_repo: RecipientRepository):
        self.sequence_repo = sequence_repo
        self.recipient_repo = recipient_repo
        self.logger = logging.getLogger(__name__)
        
        # Reply detection patterns (more comprehensive)
        self.reply_patterns = {
            'subject_prefixes': [
                r'^RE:\s*',
                r'^Re:\s*', 
                r'^re:\s*',
                r'^AW:\s*',  # German
                r'^Aw:\s*',
                r'^SV:\s*',  # Swedish/Norwegian
                r'^Sv:\s*',
                r'^VS:\s*',  # Danish
                r'^Vs:\s*',
                r'^回复:\s*',  # Chinese
                r'^答复:\s*',
                r'^Répondre:\s*',  # French
                r'^R:\s*',   # Portuguese
                r'^RES:\s*', # Portuguese
                r'^Odp:\s*', # Polish
                r'^Отв:\s*', # Russian
            ],
            'forward_prefixes': [
                r'^FW:\s*',
                r'^Fw:\s*',
                r'^fw:\s*',
                r'^FWD:\s*',
                r'^Fwd:\s*',
                r'^fwd:\s*',
                r'^WG:\s*',  # German
                r'^Wg:\s*',
                r'^TR:\s*',  # Turkish
                r'^Tr:\s*',
                r'^转发:\s*', # Chinese
                r'^Fwd:\s*',
            ]
        }
        
        # Common auto-reply indicators
        self.auto_reply_indicators = [
            'out of office',
            'automatic reply',
            'auto-reply',
            'vacation',
            'away message',
            'currently unavailable',
            'will be back',
            'maternity leave',
            'sick leave',
            'do not reply',
            'no-reply',
            'noreply',
            'automated response',
            'delivery failure',
            'undeliverable',
            'mail delivery subsystem'
        ]
        
        # Positive reply indicators
        self.positive_reply_indicators = [
            'thank you',
            'thanks',
            'interested',
            'tell me more',
            'sounds good',
            'let\'s talk',
            'schedule',
            'meeting',
            'call me',
            'phone',
            'discuss',
            'more information',
            'details'
        ]
        
        # Negative reply indicators  
        self.negative_reply_indicators = [
            'not interested',
            'no thank you',
            'remove me',
            'unsubscribe',
            'stop emailing',
            'don\'t contact',
            'not the right time',
            'already have',
            'not looking',
            'not a fit'
        ]
        
        self.logger.info("Reply matcher initialized with comprehensive detection patterns")
    
    async def match_reply(self, message: Dict[str, Any]) -> Optional[ReplyMatch]:
        """Match a message to determine if it's a reply and to which recipient"""
        try:
            # Extract message details
            message_id = message.get('id', '')
            subject = message.get('subject', '')
            from_address = self._extract_email_address(message.get('from', {}))
            received_time = self._parse_datetime(message.get('receivedDateTime'))
            in_reply_to = message.get('inReplyTo', '')
            body_preview = message.get('bodyPreview', '')
            
            if not from_address:
                return None
            
            # Try different matching methods in order of confidence
            
            # Method 1: Direct message ID matching (highest confidence)
            match = await self._match_by_message_id(in_reply_to, from_address, message_id, subject, received_time)
            if match:
                return match
            
            # Method 2: Subject line analysis (medium confidence)
            match = await self._match_by_subject(subject, from_address, message_id, received_time)
            if match:
                return match
            
            # Method 3: Sender analysis (lower confidence)
            match = await self._match_by_sender(from_address, subject, message_id, received_time, body_preview)
            if match:
                return match
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error matching reply: {e}")
            return None
    
    async def _match_by_message_id(self, in_reply_to: str, from_address: str, message_id: str, 
                                 subject: str, received_time: datetime) -> Optional[ReplyMatch]:
        """Match reply using inReplyTo message ID"""
        if not in_reply_to:
            return None
        
        try:
            # Find original sequence by message ID
            sequence = await self.sequence_repo.get_by_message_id(in_reply_to)
            if not sequence:
                return None
            
            # Verify sender matches recipient
            recipient = await self.recipient_repo.get_by_id(sequence.recipient_id)
            if not recipient or recipient.email.lower() != from_address.lower():
                return None
            
            return ReplyMatch(
                recipient_id=sequence.recipient_id,
                message_id=message_id,
                confidence=ReplyConfidence.HIGH,
                matching_method="message_id",
                original_sequence_id=sequence.id,
                reply_subject=subject,
                reply_timestamp=received_time,
                metadata={'in_reply_to': in_reply_to}
            )
            
        except Exception as e:
            self.logger.error(f"Error in message ID matching: {e}")
            return None
    
    async def _match_by_subject(self, subject: str, from_address: str, message_id: str, 
                              received_time: datetime) -> Optional[ReplyMatch]:
        """Match reply using subject line patterns"""
        try:
            # Check if subject indicates a reply
            is_reply_subject = False
            for pattern in self.reply_patterns['subject_prefixes']:
                if re.match(pattern, subject, re.IGNORECASE):
                    is_reply_subject = True
                    break
            
            if not is_reply_subject:
                return None
            
            # Find recipient by email
            recipient = await self.recipient_repo.get_by_email(from_address)
            if not recipient:
                return None
            
            # Check if recipient has active sequences
            if recipient.status not in ['active', 'pending']:
                return None
            
            return ReplyMatch(
                recipient_id=recipient.id,
                message_id=message_id,
                confidence=ReplyConfidence.MEDIUM,
                matching_method="subject_pattern",
                reply_subject=subject,
                reply_timestamp=received_time,
                metadata={'subject_pattern_matched': True}
            )
            
        except Exception as e:
            self.logger.error(f"Error in subject matching: {e}")
            return None
    
    async def _match_by_sender(self, from_address: str, subject: str, message_id: str, 
                             received_time: datetime, body_preview: str) -> Optional[ReplyMatch]:
        """Match reply using sender analysis"""
        try:
            # Find recipient by email
            recipient = await self.recipient_repo.get_by_email(from_address)
            if not recipient:
                return None
            
            # Only consider if recipient has active sequences
            if recipient.status not in ['active', 'pending']:
                return None
            
            # Check if this looks like an auto-reply (should be ignored)
            if self._is_auto_reply(subject, body_preview):
                self.logger.debug(f"Ignoring auto-reply from {from_address}: {subject}")
                return None
            
            # Check recency - only consider messages within reasonable timeframe
            if received_time and received_time < datetime.now() - timedelta(days=30):
                return None
            
            return ReplyMatch(
                recipient_id=recipient.id,
                message_id=message_id,
                confidence=ReplyConfidence.LOW,
                matching_method="sender_analysis",
                reply_subject=subject,
                reply_timestamp=received_time,
                metadata={
                    'body_preview': body_preview[:100],
                    'reply_sentiment': self._analyze_reply_sentiment(subject, body_preview)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error in sender matching: {e}")
            return None
    
    def _is_auto_reply(self, subject: str, body_preview: str) -> bool:
        """Check if message appears to be an auto-reply"""
        combined_text = f"{subject} {body_preview}".lower()
        
        for indicator in self.auto_reply_indicators:
            if indicator in combined_text:
                return True
        
        return False
    
    def _analyze_reply_sentiment(self, subject: str, body_preview: str) -> str:
        """Basic sentiment analysis of reply"""
        combined_text = f"{subject} {body_preview}".lower()
        
        positive_score = sum(1 for indicator in self.positive_reply_indicators if indicator in combined_text)
        negative_score = sum(1 for indicator in self.negative_reply_indicators if indicator in combined_text)
        
        if positive_score > negative_score:
            return "positive"
        elif negative_score > positive_score:
            return "negative"
        else:
            return "neutral"
    
    def _extract_email_address(self, from_field: Dict[str, Any]) -> Optional[str]:
        """Extract email address from Graph API from field"""
        try:
            email_address = from_field.get('emailAddress', {})
            return email_address.get('address', '').lower()
        except Exception:
            return None
    
    def _parse_datetime(self, datetime_str: str) -> Optional[datetime]:
        """Parse datetime string from Graph API"""
        try:
            if datetime_str:
                # Remove timezone info for simplicity
                clean_str = datetime_str.replace('Z', '').split('.')[0]
                return datetime.fromisoformat(clean_str)
        except Exception:
            pass
        return None


class SequenceStopper:
    """Handles stopping email sequences when replies are detected"""
    
    def __init__(self, sequence_repo: EmailSequenceRepository, recipient_repo: RecipientRepository):
        self.sequence_repo = sequence_repo
        self.recipient_repo = recipient_repo
        self.logger = logging.getLogger(__name__)
    
    async def stop_sequence(self, reply_match: ReplyMatch, scheduler=None) -> Dict[str, Any]:
        """Stop email sequence for a recipient who replied"""
        try:
            result = {
                'recipient_id': reply_match.recipient_id,
                'cancelled_emails': 0,
                'status_updated': False,
                'confidence': reply_match.confidence.value,
                'matching_method': reply_match.matching_method,
                'error': None
            }
            
            # Get recipient info
            recipient = await self.recipient_repo.get_by_id(reply_match.recipient_id)
            if not recipient:
                result['error'] = f'Recipient {reply_match.recipient_id} not found'
                return result
            
            # Cancel future emails
            cancelled_count = await self.sequence_repo.cancel_future_emails(reply_match.recipient_id)
            result['cancelled_emails'] = cancelled_count
            
            # Update recipient status
            await self.recipient_repo.update_status(reply_match.recipient_id, 'replied')
            result['status_updated'] = True
            
            # If scheduler is available, also cancel scheduled jobs
            if scheduler:
                try:
                    await scheduler.cancel_future_emails(reply_match.recipient_id)
                except Exception as e:
                    self.logger.warning(f"Could not cancel scheduler jobs: {e}")
            
            # Log the action
            self.logger.info(
                f"Stopped sequence for {recipient.email} "
                f"(confidence: {reply_match.confidence.value}, "
                f"method: {reply_match.matching_method}, "
                f"cancelled: {cancelled_count} emails)"
            )
            
            # Store reply analytics
            await self._store_reply_analytics(reply_match, recipient)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error stopping sequence for recipient {reply_match.recipient_id}: {e}")
            return {
                'recipient_id': reply_match.recipient_id,
                'error': str(e),
                'cancelled_emails': 0,
                'status_updated': False
            }
    
    async def _store_reply_analytics(self, reply_match: ReplyMatch, recipient: Recipient):
        """Store reply analytics for reporting"""
        try:
            # This could be expanded to store in a dedicated analytics table
            # For now, just log structured data
            analytics_data = {
                'event': 'reply_detected',
                'timestamp': datetime.now().isoformat(),
                'recipient_id': reply_match.recipient_id,
                'recipient_email': recipient.email,
                'company': recipient.company,
                'role': recipient.role,
                'reply_confidence': reply_match.confidence.value,
                'matching_method': reply_match.matching_method,
                'reply_subject': reply_match.reply_subject,
                'reply_timestamp': reply_match.reply_timestamp.isoformat() if reply_match.reply_timestamp else None,
                'metadata': reply_match.metadata or {}
            }
            
            self.logger.info(f"Reply analytics: {analytics_data}")
            
        except Exception as e:
            self.logger.error(f"Error storing reply analytics: {e}")
    
    async def bulk_stop_sequences(self, reply_matches: List[ReplyMatch], scheduler=None) -> Dict[str, Any]:
        """Stop multiple sequences efficiently"""
        results = {
            'total_processed': len(reply_matches),
            'successful_stops': 0,
            'failed_stops': 0,
            'total_cancelled_emails': 0,
            'errors': []
        }
        
        for reply_match in reply_matches:
            try:
                result = await self.stop_sequence(reply_match, scheduler)
                
                if result.get('error'):
                    results['failed_stops'] += 1
                    results['errors'].append({
                        'recipient_id': reply_match.recipient_id,
                        'error': result['error']
                    })
                else:
                    results['successful_stops'] += 1
                    results['total_cancelled_emails'] += result.get('cancelled_emails', 0)
                    
            except Exception as e:
                results['failed_stops'] += 1
                results['errors'].append({
                    'recipient_id': reply_match.recipient_id,
                    'error': str(e)
                })
        
        self.logger.info(f"Bulk sequence stop completed: {results['successful_stops']} successful, {results['failed_stops']} failed")
        
        return results
    
    async def get_reply_statistics(self) -> Dict[str, Any]:
        """Get statistics about replies and stopped sequences"""
        try:
            # Get all replied recipients
            replied_recipients = await self.recipient_repo.get_all_by_status('replied')
            
            stats = {
                'total_replies': len(replied_recipients),
                'reply_rate': 0.0,
                'companies_replied': set(),
                'roles_replied': set(),
                'recent_replies': []
            }
            
            # Get total active + replied for rate calculation
            active_recipients = await self.recipient_repo.get_all_by_status('active')
            stopped_recipients = await self.recipient_repo.get_all_by_status('stopped')
            
            total_contacted = len(replied_recipients) + len(active_recipients) + len(stopped_recipients)
            
            if total_contacted > 0:
                stats['reply_rate'] = (len(replied_recipients) / total_contacted) * 100
            
            # Analyze replied recipients
            for recipient in replied_recipients:
                stats['companies_replied'].add(recipient.company)
                stats['roles_replied'].add(recipient.role)
            
            # Convert sets to lists for JSON serialization
            stats['companies_replied'] = list(stats['companies_replied'])
            stats['roles_replied'] = list(stats['roles_replied'])
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting reply statistics: {e}")
            return {'error': str(e)}