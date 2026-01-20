"""
Email sequence management with advanced timing controls and logic
Handles complex sequence workflows and timing configurations
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from config import Config
from db.models import Recipient, EmailSequence, RecipientRepository, EmailSequenceRepository


class SequenceStatus(Enum):
    """Email sequence status enumeration"""
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REPLIED = "replied"


class SequenceStep(Enum):
    """Email sequence step enumeration"""
    INITIAL = 1
    FOLLOW_UP_1 = 2
    FOLLOW_UP_2 = 3


class SequenceManager:
    """Advanced email sequence management with timing controls"""
    
    def __init__(self, config: Config, recipient_repo: RecipientRepository, sequence_repo: EmailSequenceRepository):
        self.config = config
        self.recipient_repo = recipient_repo
        self.sequence_repo = sequence_repo
        self.logger = logging.getLogger(__name__)
        
        # Sequence configuration
        self.sequence_config = {
            SequenceStep.INITIAL: {
                'delay_days': 0,  # Send immediately
                'delay_hours': 0,
                'delay_minutes': 1,  # Small delay for processing
                'required': True
            },
            SequenceStep.FOLLOW_UP_1: {
                'delay_days': config.follow_up_1_delay_days,
                'delay_hours': 0,
                'delay_minutes': 0,
                'required': True
            },
            SequenceStep.FOLLOW_UP_2: {
                'delay_days': config.follow_up_2_delay_days,
                'delay_hours': 0,
                'delay_minutes': 0,
                'required': config.follow_up_2_enabled
            }
        }
        
        self.logger.info("Sequence manager initialized with timing controls")
    
    async def create_complete_sequence(self, recipient_id: int) -> bool:
        """Create complete email sequence for a recipient"""
        try:
            recipient = await self.recipient_repo.get_by_id(recipient_id)
            if not recipient:
                self.logger.error(f"Recipient {recipient_id} not found")
                return False
            
            # Check if sequence already exists
            existing_sequences = await self._get_recipient_sequences(recipient_id)
            if existing_sequences:
                self.logger.warning(f"Sequence already exists for recipient {recipient_id}")
                return False
            
            # Create sequence steps
            base_time = datetime.now()
            
            for step_enum in SequenceStep:
                step_config = self.sequence_config[step_enum]
                
                if not step_config['required']:
                    continue
                
                # Calculate scheduled time
                scheduled_time = self._calculate_scheduled_time(
                    base_time, 
                    step_config,
                    step_enum.value
                )
                
                # Create sequence entry
                sequence = EmailSequence(
                    recipient_id=recipient_id,
                    step=step_enum.value,
                    scheduled_at=scheduled_time
                )
                
                await self.sequence_repo.create(sequence)
                
                self.logger.debug(f"Created sequence step {step_enum.value} for recipient {recipient_id} at {scheduled_time}")
            
            # Update recipient status
            await self.recipient_repo.update_status(recipient_id, 'active')
            
            self.logger.info(f"Created complete email sequence for recipient {recipient_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create sequence for recipient {recipient_id}: {e}")
            return False
    
    def _calculate_scheduled_time(self, base_time: datetime, step_config: Dict[str, Any], step: int) -> datetime:
        """Calculate scheduled time for a sequence step"""
        if step == 1:
            # Initial email - schedule immediately with small delay
            return base_time + timedelta(
                minutes=step_config['delay_minutes']
            )
        else:
            # Follow-up emails - calculate from base time
            return base_time + timedelta(
                days=step_config['delay_days'],
                hours=step_config['delay_hours'],
                minutes=step_config['delay_minutes']
            )
    
    async def _get_recipient_sequences(self, recipient_id: int) -> List[EmailSequence]:
        """Get all sequences for a recipient"""
        # This would typically be a method in the repository
        # For now, we'll implement a basic version
        try:
            # Query database for sequences
            query = "SELECT * FROM email_sequence WHERE recipient_id = ? ORDER BY step"
            results = await self.sequence_repo.db_manager.execute_query(query, (recipient_id,))
            
            sequences = []
            for row in results:
                sequences.append(EmailSequence(
                    id=row[0],
                    recipient_id=row[1],
                    step=row[2],
                    scheduled_at=row[3],
                    sent_at=row[4],
                    message_id=row[5],
                    replied=bool(row[6]),
                    created_at=row[7],
                    updated_at=row[8]
                ))
            
            return sequences
            
        except Exception as e:
            self.logger.error(f"Error getting sequences for recipient {recipient_id}: {e}")
            return []
    
    async def get_sequence_status(self, recipient_id: int) -> Dict[str, Any]:
        """Get detailed status of a recipient's email sequence"""
        try:
            recipient = await self.recipient_repo.get_by_id(recipient_id)
            if not recipient:
                return {'error': f'Recipient {recipient_id} not found'}
            
            sequences = await self._get_recipient_sequences(recipient_id)
            
            sequence_info = {
                'recipient_id': recipient_id,
                'recipient_email': recipient.email,
                'recipient_status': recipient.status,
                'total_steps': len(sequences),
                'steps': []
            }
            
            for sequence in sequences:
                step_info = {
                    'step': sequence.step,
                    'scheduled_at': sequence.scheduled_at.isoformat() if sequence.scheduled_at else None,
                    'sent_at': sequence.sent_at.isoformat() if sequence.sent_at else None,
                    'message_id': sequence.message_id,
                    'replied': sequence.replied,
                    'status': self._get_step_status(sequence)
                }
                sequence_info['steps'].append(step_info)
            
            return sequence_info
            
        except Exception as e:
            self.logger.error(f"Error getting sequence status for recipient {recipient_id}: {e}")
            return {'error': str(e)}
    
    def _get_step_status(self, sequence: EmailSequence) -> str:
        """Determine the status of a sequence step"""
        if sequence.replied:
            return 'replied'
        elif sequence.sent_at:
            return 'sent'
        elif sequence.scheduled_at and sequence.scheduled_at <= datetime.now():
            return 'due'
        else:
            return 'scheduled'
    
    async def modify_sequence_timing(self, recipient_id: int, step: int, new_scheduled_time: datetime) -> bool:
        """Modify the scheduled time for a specific sequence step"""
        try:
            # Find the sequence
            sequences = await self._get_recipient_sequences(recipient_id)
            target_sequence = None
            
            for seq in sequences:
                if seq.step == step and not seq.sent_at:  # Only modify unsent emails
                    target_sequence = seq
                    break
            
            if not target_sequence:
                self.logger.error(f"No modifiable sequence found for recipient {recipient_id}, step {step}")
                return False
            
            # Update scheduled time
            query = """
            UPDATE email_sequence 
            SET scheduled_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """
            
            await self.sequence_repo.db_manager.execute_update(
                query, (new_scheduled_time, target_sequence.id)
            )
            
            self.logger.info(f"Modified sequence timing for recipient {recipient_id}, step {step} to {new_scheduled_time}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error modifying sequence timing: {e}")
            return False
    
    async def pause_sequence(self, recipient_id: int) -> bool:
        """Pause all future emails in a sequence"""
        try:
            # Update recipient status
            await self.recipient_repo.update_status(recipient_id, 'stopped')
            
            self.logger.info(f"Paused sequence for recipient {recipient_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error pausing sequence for recipient {recipient_id}: {e}")
            return False
    
    async def resume_sequence(self, recipient_id: int) -> bool:
        """Resume a paused sequence"""
        try:
            # Update recipient status
            await self.recipient_repo.update_status(recipient_id, 'active')
            
            self.logger.info(f"Resumed sequence for recipient {recipient_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error resuming sequence for recipient {recipient_id}: {e}")
            return False
    
    async def cancel_sequence(self, recipient_id: int, reason: str = "manual_cancellation") -> bool:
        """Cancel all future emails in a sequence"""
        try:
            # Cancel future emails
            cancelled_count = await self.sequence_repo.cancel_future_emails(recipient_id)
            
            # Update recipient status
            status = 'replied' if reason == 'reply_detected' else 'stopped'
            await self.recipient_repo.update_status(recipient_id, status)
            
            self.logger.info(f"Cancelled sequence for recipient {recipient_id} (reason: {reason}, cancelled {cancelled_count} emails)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cancelling sequence for recipient {recipient_id}: {e}")
            return False
    
    async def get_sequence_analytics(self) -> Dict[str, Any]:
        """Get analytics for all email sequences"""
        try:
            # Get all recipients
            all_recipients = await self.recipient_repo.get_all_by_status('active')
            all_recipients.extend(await self.recipient_repo.get_all_by_status('replied'))
            all_recipients.extend(await self.recipient_repo.get_all_by_status('stopped'))
            
            analytics = {
                'total_recipients': len(all_recipients),
                'status_breakdown': {
                    'active': 0,
                    'replied': 0,
                    'stopped': 0,
                    'pending': 0
                },
                'step_analytics': {
                    1: {'sent': 0, 'pending': 0, 'replied': 0},
                    2: {'sent': 0, 'pending': 0, 'replied': 0},
                    3: {'sent': 0, 'pending': 0, 'replied': 0}
                },
                'reply_rate': 0.0,
                'completion_rate': 0.0
            }
            
            # Count by status
            for recipient in all_recipients:
                analytics['status_breakdown'][recipient.status] += 1
            
            # Get sequence statistics
            total_sent = 0
            total_replied = 0
            
            for recipient in all_recipients:
                sequences = await self._get_recipient_sequences(recipient.id)
                
                for sequence in sequences:
                    step = sequence.step
                    if sequence.sent_at:
                        analytics['step_analytics'][step]['sent'] += 1
                        total_sent += 1
                    elif sequence.replied:
                        analytics['step_analytics'][step]['replied'] += 1
                        total_replied += 1
                    else:
                        analytics['step_analytics'][step]['pending'] += 1
            
            # Calculate rates
            if total_sent > 0:
                analytics['reply_rate'] = (analytics['status_breakdown']['replied'] / total_sent) * 100
            
            if len(all_recipients) > 0:
                completed = analytics['status_breakdown']['replied'] + analytics['status_breakdown']['stopped']
                analytics['completion_rate'] = (completed / len(all_recipients)) * 100
            
            return analytics
            
        except Exception as e:
            self.logger.error(f"Error getting sequence analytics: {e}")
            return {'error': str(e)}
    
    async def optimize_sequence_timing(self, recipient_id: int) -> Dict[str, Any]:
        """Optimize sequence timing based on recipient behavior (future enhancement)"""
        # This is a placeholder for future ML-based optimization
        # For now, return current timing
        try:
            sequences = await self._get_recipient_sequences(recipient_id)
            
            optimization_suggestions = {
                'current_timing': {},
                'suggested_timing': {},
                'confidence': 0.0,
                'reason': 'Optimization not yet implemented'
            }
            
            for sequence in sequences:
                optimization_suggestions['current_timing'][sequence.step] = {
                    'scheduled_at': sequence.scheduled_at.isoformat() if sequence.scheduled_at else None
                }
            
            return optimization_suggestions
            
        except Exception as e:
            self.logger.error(f"Error optimizing sequence timing: {e}")
            return {'error': str(e)}
    
    def get_sequence_configuration(self) -> Dict[str, Any]:
        """Get current sequence configuration"""
        config_dict = {}
        
        for step_enum, config in self.sequence_config.items():
            config_dict[f"step_{step_enum.value}"] = {
                'delay_days': config['delay_days'],
                'delay_hours': config['delay_hours'],
                'delay_minutes': config['delay_minutes'],
                'required': config['required']
            }
        
        return {
            'sequence_steps': config_dict,
            'follow_up_2_enabled': self.config.follow_up_2_enabled,
            'total_possible_steps': len([s for s in self.sequence_config.values() if s['required']])
        }