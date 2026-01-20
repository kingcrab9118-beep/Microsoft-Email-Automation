"""
Email sequence scheduler using APScheduler
Manages timing and execution of email sequences
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import Config
from db.database import DatabaseManager
from db.models import Recipient, EmailSequence, RecipientRepository, EmailSequenceRepository
from email.sender import EmailSender
from utils.rate_limiter import AdaptiveRateLimiter


class SequenceScheduler:
    """Manages email sequence scheduling and execution"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        
        # Initialize repositories
        self.recipient_repo = RecipientRepository(db_manager)
        self.sequence_repo = EmailSequenceRepository(db_manager)
        
        # Initialize rate limiter
        self.rate_limiter = AdaptiveRateLimiter(config)
        
        # Email sender will be injected
        self.email_sender: Optional[EmailSender] = None
        
        # Configure APScheduler
        self._setup_scheduler()
        
        self.logger.info("Email sequence scheduler initialized")
    
    def _setup_scheduler(self):
        """Configure APScheduler with persistence"""
        # Job store configuration (using SQLite for persistence)
        jobstores = {
            'default': SQLAlchemyJobStore(url=self.config.database_url, tablename='scheduler_jobs')
        }
        
        # Executor configuration
        executors = {
            'default': AsyncIOExecutor()
        }
        
        # Job defaults
        job_defaults = {
            'coalesce': False,
            'max_instances': 3,
            'misfire_grace_time': 300  # 5 minutes
        }
        
        # Create scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Add event listeners
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
    
    def set_email_sender(self, email_sender: EmailSender):
        """Set the email sender instance"""
        self.email_sender = email_sender
    
    def start(self):
        """Start the scheduler"""
        try:
            self.scheduler.start()
            self.logger.info("Email sequence scheduler started")
            
            # Schedule periodic tasks
            self._schedule_periodic_tasks()
            
        except Exception as e:
            self.logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def shutdown(self):
        """Shutdown the scheduler"""
        try:
            self.scheduler.shutdown(wait=True)
            self.logger.info("Email sequence scheduler stopped")
        except Exception as e:
            self.logger.error(f"Error shutting down scheduler: {e}")
    
    def _schedule_periodic_tasks(self):
        """Schedule recurring tasks"""
        # Process due emails every minute
        self.scheduler.add_job(
            self.process_due_emails,
            'interval',
            minutes=1,
            id='process_due_emails',
            replace_existing=True
        )
        
        # Cleanup old jobs daily
        self.scheduler.add_job(
            self._cleanup_old_jobs,
            'cron',
            hour=2,  # 2 AM daily
            id='cleanup_old_jobs',
            replace_existing=True
        )
    
    async def schedule_initial_email(self, recipient_id: int) -> bool:
        """Schedule the initial email for a recipient"""
        try:
            # Get recipient
            recipient = await self.recipient_repo.get_by_id(recipient_id)
            if not recipient:
                self.logger.error(f"Recipient {recipient_id} not found")
                return False
            
            # Schedule immediately (or with small delay)
            scheduled_time = datetime.now() + timedelta(seconds=30)
            
            # Create email sequence entry
            sequence = EmailSequence(
                recipient_id=recipient_id,
                step=1,
                scheduled_at=scheduled_time
            )
            
            sequence_id = await self.sequence_repo.create(sequence)
            
            # Update recipient status to active
            await self.recipient_repo.update_status(recipient_id, 'active')
            
            self.logger.info(f"Scheduled initial email for recipient {recipient_id} at {scheduled_time}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to schedule initial email for recipient {recipient_id}: {e}")
            return False
    
    async def schedule_follow_up(self, recipient_id: int, step: int, delay_days: int) -> bool:
        """Schedule a follow-up email"""
        try:
            # Calculate scheduled time
            scheduled_time = datetime.now() + timedelta(days=delay_days)
            
            # Create email sequence entry
            sequence = EmailSequence(
                recipient_id=recipient_id,
                step=step,
                scheduled_at=scheduled_time
            )
            
            sequence_id = await self.sequence_repo.create(sequence)
            
            self.logger.info(f"Scheduled follow-up email step {step} for recipient {recipient_id} at {scheduled_time}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to schedule follow-up step {step} for recipient {recipient_id}: {e}")
            return False
    
    async def process_due_emails(self):
        """Process all emails that are due to be sent"""
        try:
            # Get due emails
            due_emails = await self.sequence_repo.get_due_emails()
            
            if not due_emails:
                return
            
            self.logger.info(f"Processing {len(due_emails)} due emails")
            
            # Process each email
            for sequence in due_emails:
                await self._process_single_email(sequence)
            
        except Exception as e:
            self.logger.error(f"Error processing due emails: {e}")
    
    async def _process_single_email(self, sequence: EmailSequence):
        """Process a single email sequence"""
        try:
            # Check rate limits
            if not await self.rate_limiter.can_send_email():
                self.logger.info(f"Rate limit reached, skipping email sequence {sequence.id}")
                return
            
            # Get recipient
            recipient = await self.recipient_repo.get_by_id(sequence.recipient_id)
            if not recipient:
                self.logger.error(f"Recipient {sequence.recipient_id} not found for sequence {sequence.id}")
                return
            
            # Check if recipient is still active (not replied or stopped)
            if recipient.status in ['replied', 'stopped']:
                self.logger.info(f"Skipping email for recipient {recipient.id} (status: {recipient.status})")
                return
            
            # Send email
            if self.email_sender:
                result = await self.email_sender.send_email(recipient, sequence.step)
                
                if result['success']:
                    # Mark as sent
                    await self.sequence_repo.mark_sent(
                        sequence.id,
                        result['message_id'],
                        result['sent_at']
                    )
                    
                    # Record rate limiting
                    await self.rate_limiter.record_send_result(True)
                    
                    # Schedule next follow-up if applicable
                    await self._schedule_next_follow_up(recipient.id, sequence.step)
                    
                    self.logger.info(f"Successfully sent email step {sequence.step} to {recipient.email}")
                    
                else:
                    # Record failure
                    await self.rate_limiter.record_send_result(False, result.get('error', ''))
                    self.logger.error(f"Failed to send email step {sequence.step} to {recipient.email}: {result.get('error')}")
            
            else:
                self.logger.error("Email sender not configured")
        
        except Exception as e:
            self.logger.error(f"Error processing email sequence {sequence.id}: {e}")
    
    async def _schedule_next_follow_up(self, recipient_id: int, current_step: int):
        """Schedule the next follow-up email in the sequence"""
        try:
            next_step = current_step + 1
            
            if next_step == 2:
                # Schedule follow-up 1
                delay_days = self.config.follow_up_1_delay_days
                await self.schedule_follow_up(recipient_id, next_step, delay_days)
                
            elif next_step == 3 and self.config.follow_up_2_enabled:
                # Schedule follow-up 2 if enabled
                delay_days = self.config.follow_up_2_delay_days
                await self.schedule_follow_up(recipient_id, next_step, delay_days)
            
        except Exception as e:
            self.logger.error(f"Error scheduling next follow-up for recipient {recipient_id}: {e}")
    
    async def cancel_future_emails(self, recipient_id: int) -> int:
        """Cancel all future emails for a recipient (when they reply)"""
        try:
            # Cancel in database
            cancelled_count = await self.sequence_repo.cancel_future_emails(recipient_id)
            
            # Update recipient status
            await self.recipient_repo.update_status(recipient_id, 'replied')
            
            self.logger.info(f"Cancelled {cancelled_count} future emails for recipient {recipient_id}")
            return cancelled_count
            
        except Exception as e:
            self.logger.error(f"Error cancelling future emails for recipient {recipient_id}: {e}")
            return 0
    
    async def pause_recipient_sequence(self, recipient_id: int) -> bool:
        """Pause email sequence for a recipient"""
        try:
            await self.recipient_repo.update_status(recipient_id, 'stopped')
            self.logger.info(f"Paused email sequence for recipient {recipient_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error pausing sequence for recipient {recipient_id}: {e}")
            return False
    
    async def resume_recipient_sequence(self, recipient_id: int) -> bool:
        """Resume email sequence for a recipient"""
        try:
            await self.recipient_repo.update_status(recipient_id, 'active')
            self.logger.info(f"Resumed email sequence for recipient {recipient_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error resuming sequence for recipient {recipient_id}: {e}")
            return False
    
    def _job_executed(self, event):
        """Handle job execution events"""
        self.logger.debug(f"Job {event.job_id} executed successfully")
    
    def _job_error(self, event):
        """Handle job error events"""
        self.logger.error(f"Job {event.job_id} failed: {event.exception}")
    
    async def _cleanup_old_jobs(self):
        """Clean up old completed jobs"""
        try:
            # Remove jobs older than 30 days
            cutoff_date = datetime.now() - timedelta(days=30)
            
            # This would typically involve cleaning up the job store
            # For now, just log the cleanup attempt
            self.logger.info("Performed scheduled cleanup of old jobs")
            
        except Exception as e:
            self.logger.error(f"Error during job cleanup: {e}")
    
    async def get_scheduler_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        try:
            # Get pending sequences
            due_emails = await self.sequence_repo.get_due_emails()
            
            # Get rate limiter status
            rate_status = self.rate_limiter.get_adaptive_status()
            
            return {
                'scheduler_running': self.scheduler.running,
                'pending_emails': len(due_emails),
                'rate_limiter': rate_status,
                'jobs_count': len(self.scheduler.get_jobs()),
                'next_run_time': self.scheduler.get_job('process_due_emails').next_run_time.isoformat() if self.scheduler.get_job('process_due_emails') else None
            }
            
        except Exception as e:
            self.logger.error(f"Error getting scheduler status: {e}")
            return {'error': str(e)}
    
    async def add_recipient_to_sequence(self, recipient_data: Dict[str, str]) -> bool:
        """Add a new recipient and start their email sequence"""
        try:
            # Create recipient
            recipient = Recipient(
                first_name=recipient_data['first_name'],
                company=recipient_data['company'],
                role=recipient_data['role'],
                email=recipient_data['email']
            )
            
            if not recipient.validate():
                self.logger.error(f"Invalid recipient data: {recipient_data}")
                return False
            
            # Check if recipient already exists
            existing = await self.recipient_repo.get_by_email(recipient.email)
            if existing:
                self.logger.warning(f"Recipient {recipient.email} already exists")
                return False
            
            # Create recipient in database
            recipient_id = await self.recipient_repo.create(recipient)
            
            # Schedule initial email
            success = await self.schedule_initial_email(recipient_id)
            
            if success:
                self.logger.info(f"Added recipient {recipient.email} to email sequence")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error adding recipient to sequence: {e}")
            return False