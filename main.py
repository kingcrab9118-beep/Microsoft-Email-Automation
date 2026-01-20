#!/usr/bin/env python3
"""
Microsoft 365 Email Automation System
Main application entry point with CLI interface
"""

import asyncio
import logging
import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any

from config import Config
from db.database import DatabaseManager
from scheduler.scheduler import SequenceScheduler
from replies.reply_tracker import ReplyTracker
from auth.graph_auth import GraphAuthenticator, GraphAPIClient
from auth.validator import AuthenticationValidator
from email.sender import EmailSender
from replies.reply_matcher import ReplyMatcher, SequenceStopper


def setup_logging(log_level: str = "INFO"):
    """Configure structured logging for the application"""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('email_automation.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


class EmailAutomationApp:
    """Main application class"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Core components
        self.db_manager = None
        self.authenticator = None
        self.graph_client = None
        self.email_sender = None
        self.scheduler = None
        self.reply_tracker = None
        self.reply_matcher = None
        self.sequence_stopper = None
    
    async def initialize(self):
        """Initialize all application components"""
        try:
            # Initialize database
            self.db_manager = DatabaseManager(self.config.database_url)
            await self.db_manager.initialize()
            self.logger.info("Database initialized successfully")
            
            # Initialize authentication
            self.authenticator = GraphAuthenticator(self.config)
            self.graph_client = GraphAPIClient(self.authenticator)
            self.logger.info("Authentication initialized")
            
            # Initialize email sender
            self.email_sender = EmailSender(self.config, self.graph_client)
            self.logger.info("Email sender initialized")
            
            # Initialize scheduler
            self.scheduler = SequenceScheduler(self.config, self.db_manager)
            self.scheduler.set_email_sender(self.email_sender)
            self.logger.info("Scheduler initialized")
            
            # Initialize reply tracking
            self.reply_tracker = ReplyTracker(self.config, self.db_manager, self.scheduler)
            self.reply_tracker.set_graph_client(self.graph_client)
            
            # Initialize reply matching
            from db.models import RecipientRepository, EmailSequenceRepository
            recipient_repo = RecipientRepository(self.db_manager)
            sequence_repo = EmailSequenceRepository(self.db_manager)
            
            self.reply_matcher = ReplyMatcher(sequence_repo, recipient_repo)
            self.sequence_stopper = SequenceStopper(sequence_repo, recipient_repo)
            
            self.logger.info("Reply tracking initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            raise
    
    async def start_daemon(self):
        """Start the application in daemon mode"""
        try:
            # Start the scheduler
            self.scheduler.start()
            self.logger.info("Email sequence scheduler started")
            
            # Start reply tracking
            reply_task = asyncio.create_task(self.reply_tracker.start_monitoring())
            self.logger.info("Reply tracking started")
            
            # Keep the application running
            self.logger.info("Email automation system is running. Press Ctrl+C to stop.")
            
            try:
                await reply_task
            except asyncio.CancelledError:
                self.logger.info("Reply tracking cancelled")
            
        except KeyboardInterrupt:
            self.logger.info("Shutting down email automation system...")
        except Exception as e:
            self.logger.error(f"Error in daemon mode: {e}")
            raise
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Cleanup application resources"""
        try:
            if self.scheduler:
                self.scheduler.shutdown()
            
            if self.db_manager:
                await self.db_manager.close()
            
            self.logger.info("Application cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


async def cmd_validate_config(args):
    """Validate configuration command"""
    try:
        config = Config()
        validator = AuthenticationValidator(config)
        
        print("\n" + "="*60)
        print("EMAIL AUTOMATION SYSTEM - CONFIGURATION VALIDATION")
        print("="*60)
        
        # Print configuration status
        validator.print_configuration_status()
        
        # Test authentication if config is valid
        config_valid, config_errors = validator.validate_configuration()
        
        if config_valid:
            print("Testing authentication...")
            auth_success, auth_results = await validator.test_authentication()
            
            if auth_success:
                print("✓ Authentication test passed!")
                print(f"✓ Permissions: {auth_results['permissions']}")
            else:
                print("✗ Authentication test failed!")
                for error in auth_results.get('errors', []):
                    print(f"  - {error}")
        else:
            print("\nSkipping authentication test due to configuration errors.")
            print("\nSetup Instructions:")
            print(validator.get_setup_instructions())
        
    except Exception as e:
        print(f"Error validating configuration: {e}")
        sys.exit(1)


async def cmd_add_recipient(args):
    """Add recipient command"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        recipient_data = {
            'first_name': args.first_name,
            'company': args.company,
            'role': args.role,
            'email': args.email
        }
        
        success = await app.scheduler.add_recipient_to_sequence(recipient_data)
        
        if success:
            print(f"✓ Successfully added {args.email} to email sequence")
        else:
            print(f"✗ Failed to add {args.email} to email sequence")
            sys.exit(1)
        
        await app.cleanup()
        
    except Exception as e:
        print(f"Error adding recipient: {e}")
        sys.exit(1)


async def cmd_send_test_email(args):
    """Send test email command"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        result = await app.email_sender.send_test_email(args.email)
        
        if result['success']:
            print(f"✓ Test email sent successfully to {args.email}")
        else:
            print(f"✗ Failed to send test email: {result.get('error', 'Unknown error')}")
            sys.exit(1)
        
        await app.cleanup()
        
    except Exception as e:
        print(f"Error sending test email: {e}")
        sys.exit(1)


async def cmd_status(args):
    """Show system status command"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        # Get scheduler status
        scheduler_status = await app.scheduler.get_scheduler_status()
        
        # Get reply tracker status
        reply_status = app.reply_tracker.get_monitoring_status()
        
        # Get database stats
        from db.models import RecipientRepository
        recipient_repo = RecipientRepository(app.db_manager)
        
        active_recipients = await recipient_repo.get_all_by_status('active')
        replied_recipients = await recipient_repo.get_all_by_status('replied')
        stopped_recipients = await recipient_repo.get_all_by_status('stopped')
        
        print("\n" + "="*50)
        print("EMAIL AUTOMATION SYSTEM STATUS")
        print("="*50)
        
        print(f"\nScheduler:")
        print(f"  Running: {'✓' if scheduler_status.get('scheduler_running') else '✗'}")
        print(f"  Pending emails: {scheduler_status.get('pending_emails', 0)}")
        print(f"  Jobs count: {scheduler_status.get('jobs_count', 0)}")
        
        print(f"\nReply Tracking:")
        print(f"  Active: {'✓' if reply_status.get('monitoring_active') else '✗'}")
        print(f"  Last check: {reply_status.get('last_check_time', 'Never')}")
        print(f"  Known recipients: {reply_status.get('known_recipients_count', 0)}")
        
        print(f"\nRecipients:")
        print(f"  Active: {len(active_recipients)}")
        print(f"  Replied: {len(replied_recipients)}")
        print(f"  Stopped: {len(stopped_recipients)}")
        
        total = len(active_recipients) + len(replied_recipients) + len(stopped_recipients)
        if total > 0:
            reply_rate = (len(replied_recipients) / total) * 100
            print(f"  Reply rate: {reply_rate:.1f}%")
        
        print("="*50 + "\n")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"Error getting status: {e}")
        sys.exit(1)


async def cmd_run_daemon(args):
    """Run daemon command"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        await app.start_daemon()
        
    except Exception as e:
        print(f"Error running daemon: {e}")
        sys.exit(1)


def create_parser():
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description='Microsoft 365 Email Automation System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s validate                                    # Validate configuration
  %(prog)s add-recipient "John" "Acme Corp" "CEO" "john@acme.com"  # Add recipient
  %(prog)s test-email "test@example.com"               # Send test email
  %(prog)s status                                      # Show system status
  %(prog)s run                                         # Run daemon mode
        """
    )
    
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Set logging level')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    
    # Add recipient command
    add_parser = subparsers.add_parser('add-recipient', help='Add recipient to email sequence')
    add_parser.add_argument('first_name', help='First name')
    add_parser.add_argument('company', help='Company name')
    add_parser.add_argument('role', help='Job role/title')
    add_parser.add_argument('email', help='Email address')
    
    # Test email command
    test_parser = subparsers.add_parser('test-email', help='Send test email')
    test_parser.add_argument('email', help='Test email address')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status')
    
    # Run daemon command
    run_parser = subparsers.add_parser('run', help='Run in daemon mode')
    
    return parser


async def main():
    """Main application entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Handle commands
    if args.command == 'validate':
        await cmd_validate_config(args)
    elif args.command == 'add-recipient':
        await cmd_add_recipient(args)
    elif args.command == 'test-email':
        await cmd_send_test_email(args)
    elif args.command == 'status':
        await cmd_status(args)
    elif args.command == 'run':
        await cmd_run_daemon(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())