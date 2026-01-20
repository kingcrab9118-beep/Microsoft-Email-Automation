"""
Data models for Microsoft 365 Email Automation System
Provides ORM-like functionality for database operations
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from email_validator import validate_email, EmailNotValidError

from .database import DatabaseManager


@dataclass
class Recipient:
    """Recipient data model"""
    id: Optional[int] = None
    first_name: str = ""
    company: str = ""
    role: str = ""
    email: str = ""
    status: str = "pending"  # pending, active, replied, stopped
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate recipient data"""
        try:
            # Check required fields
            if not all([self.first_name, self.company, self.role, self.email]):
                return False
            
            # Validate email format
            validate_email(self.email)
            
            # Validate status
            valid_statuses = ['pending', 'active', 'replied', 'stopped']
            if self.status not in valid_statuses:
                return False
            
            return True
            
        except EmailNotValidError:
            return False
        except Exception:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'first_name': self.first_name,
            'company': self.company,
            'role': self.role,
            'email': self.email,
            'status': self.status,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Recipient':
        """Create instance from dictionary"""
        return cls(
            id=data.get('id'),
            first_name=data.get('first_name', ''),
            company=data.get('company', ''),
            role=data.get('role', ''),
            email=data.get('email', ''),
            status=data.get('status', 'pending'),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )


@dataclass
class EmailSequence:
    """Email sequence data model"""
    id: Optional[int] = None
    recipient_id: int = 0
    step: int = 1  # 1, 2, or 3
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    message_id: Optional[str] = None
    replied: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def validate(self) -> bool:
        """Validate email sequence data"""
        try:
            # Check required fields
            if not self.recipient_id or not self.scheduled_at:
                return False
            
            # Validate step
            if self.step not in [1, 2, 3]:
                return False
            
            # If sent, must have sent_at timestamp
            if self.message_id and not self.sent_at:
                return False
            
            return True
            
        except Exception:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'recipient_id': self.recipient_id,
            'step': self.step,
            'scheduled_at': self.scheduled_at,
            'sent_at': self.sent_at,
            'message_id': self.message_id,
            'replied': self.replied,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmailSequence':
        """Create instance from dictionary"""
        return cls(
            id=data.get('id'),
            recipient_id=data.get('recipient_id', 0),
            step=data.get('step', 1),
            scheduled_at=data.get('scheduled_at'),
            sent_at=data.get('sent_at'),
            message_id=data.get('message_id'),
            replied=bool(data.get('replied', False)),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )


class RecipientRepository:
    """Repository for recipient operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
    
    async def create(self, recipient: Recipient) -> int:
        """Create new recipient"""
        if not recipient.validate():
            raise ValueError("Invalid recipient data")
        
        query = """
        INSERT INTO recipients (first_name, company, role, email, status)
        VALUES (?, ?, ?, ?, ?)
        """
        params = (
            recipient.first_name,
            recipient.company,
            recipient.role,
            recipient.email,
            recipient.status
        )
        
        try:
            recipient_id = await self.db_manager.execute_insert(query, params)
            self.logger.info(f"Created recipient {recipient_id} for {recipient.email}")
            return recipient_id
            
        except Exception as e:
            self.logger.error(f"Failed to create recipient: {e}")
            raise
    
    async def get_by_id(self, recipient_id: int) -> Optional[Recipient]:
        """Get recipient by ID"""
        query = "SELECT * FROM recipients WHERE id = ?"
        results = await self.db_manager.execute_query(query, (recipient_id,))
        
        if results:
            row = results[0]
            return Recipient(
                id=row[0],
                first_name=row[1],
                company=row[2],
                role=row[3],
                email=row[4],
                status=row[5],
                created_at=row[6],
                updated_at=row[7]
            )
        return None
    
    async def get_by_email(self, email: str) -> Optional[Recipient]:
        """Get recipient by email"""
        query = "SELECT * FROM recipients WHERE email = ?"
        results = await self.db_manager.execute_query(query, (email,))
        
        if results:
            row = results[0]
            return Recipient(
                id=row[0],
                first_name=row[1],
                company=row[2],
                role=row[3],
                email=row[4],
                status=row[5],
                created_at=row[6],
                updated_at=row[7]
            )
        return None
    
    async def update_status(self, recipient_id: int, status: str) -> bool:
        """Update recipient status"""
        valid_statuses = ['pending', 'active', 'replied', 'stopped']
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}")
        
        query = """
        UPDATE recipients 
        SET status = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
        """
        
        affected_rows = await self.db_manager.execute_update(query, (status, recipient_id))
        success = affected_rows > 0
        
        if success:
            self.logger.info(f"Updated recipient {recipient_id} status to {status}")
        
        return success
    
    async def get_all_by_status(self, status: str) -> List[Recipient]:
        """Get all recipients by status"""
        query = "SELECT * FROM recipients WHERE status = ? ORDER BY created_at"
        results = await self.db_manager.execute_query(query, (status,))
        
        recipients = []
        for row in results:
            recipients.append(Recipient(
                id=row[0],
                first_name=row[1],
                company=row[2],
                role=row[3],
                email=row[4],
                status=row[5],
                created_at=row[6],
                updated_at=row[7]
            ))
        
        return recipients


class EmailSequenceRepository:
    """Repository for email sequence operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
    
    async def create(self, sequence: EmailSequence) -> int:
        """Create new email sequence entry"""
        if not sequence.validate():
            raise ValueError("Invalid email sequence data")
        
        query = """
        INSERT INTO email_sequence (recipient_id, step, scheduled_at)
        VALUES (?, ?, ?)
        """
        params = (
            sequence.recipient_id,
            sequence.step,
            sequence.scheduled_at
        )
        
        try:
            sequence_id = await self.db_manager.execute_insert(query, params)
            self.logger.info(f"Created email sequence {sequence_id} for recipient {sequence.recipient_id}, step {sequence.step}")
            return sequence_id
            
        except Exception as e:
            self.logger.error(f"Failed to create email sequence: {e}")
            raise
    
    async def get_due_emails(self, current_time: datetime = None) -> List[EmailSequence]:
        """Get emails that are due to be sent"""
        if current_time is None:
            current_time = datetime.now()
        
        query = """
        SELECT * FROM email_sequence 
        WHERE scheduled_at <= ? AND sent_at IS NULL AND replied = FALSE
        ORDER BY scheduled_at
        """
        
        results = await self.db_manager.execute_query(query, (current_time,))
        
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
    
    async def mark_sent(self, sequence_id: int, message_id: str, sent_at: datetime = None) -> bool:
        """Mark email as sent"""
        if sent_at is None:
            sent_at = datetime.now()
        
        query = """
        UPDATE email_sequence 
        SET sent_at = ?, message_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """
        
        affected_rows = await self.db_manager.execute_update(
            query, (sent_at, message_id, sequence_id)
        )
        success = affected_rows > 0
        
        if success:
            self.logger.info(f"Marked email sequence {sequence_id} as sent with message ID {message_id}")
        
        return success
    
    async def mark_replied(self, recipient_id: int) -> bool:
        """Mark all future emails for recipient as replied"""
        query = """
        UPDATE email_sequence 
        SET replied = TRUE, updated_at = CURRENT_TIMESTAMP
        WHERE recipient_id = ? AND sent_at IS NULL
        """
        
        affected_rows = await self.db_manager.execute_update(query, (recipient_id,))
        
        if affected_rows > 0:
            self.logger.info(f"Marked {affected_rows} future emails as replied for recipient {recipient_id}")
        
        return affected_rows > 0
    
    async def get_by_message_id(self, message_id: str) -> Optional[EmailSequence]:
        """Get email sequence by message ID"""
        query = "SELECT * FROM email_sequence WHERE message_id = ?"
        results = await self.db_manager.execute_query(query, (message_id,))
        
        if results:
            row = results[0]
            return EmailSequence(
                id=row[0],
                recipient_id=row[1],
                step=row[2],
                scheduled_at=row[3],
                sent_at=row[4],
                message_id=row[5],
                replied=bool(row[6]),
                created_at=row[7],
                updated_at=row[8]
            )
        return None
    
    async def cancel_future_emails(self, recipient_id: int) -> int:
        """Cancel all unsent emails for a recipient"""
        query = """
        DELETE FROM email_sequence 
        WHERE recipient_id = ? AND sent_at IS NULL
        """
        
        affected_rows = await self.db_manager.execute_update(query, (recipient_id,))
        
        if affected_rows > 0:
            self.logger.info(f"Cancelled {affected_rows} future emails for recipient {recipient_id}")
        
        return affected_rows