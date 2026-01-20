#!/usr/bin/env python3
"""
Example usage scripts for the Email Automation System
Demonstrates common operations and workflows
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to import modules
sys.path.append(str(Path(__file__).parent.parent))

from config import Config
from main import EmailAutomationApp
from db.models import Recipient


async def example_basic_setup():
    """Example: Basic system setup and validation"""
    print("=== Basic Setup Example ===")
    
    try:
        # Initialize configuration
        config = Config()
        print("✓ Configuration loaded")
        
        # Initialize application
        app = EmailAutomationApp(config)
        await app.initialize()
        print("✓ Application initialized")
        
        # Test authentication
        token_valid = await app.authenticator.validate_token()
        print(f"✓ Authentication: {'Valid' if token_valid else 'Invalid'}")
        
        # Check database
        from db.models import RecipientRepository
        recipient_repo = RecipientRepository(app.db_manager)
        active_count = len(await recipient_repo.get_all_by_status('active'))
        print(f"✓ Database: {active_count} active recipients")
        
        await app.cleanup()
        print("✓ Setup validation complete")
        
    except Exception as e:
        print(f"✗ Setup failed: {e}")


async def example_add_single_recipient():
    """Example: Add a single recipient to email sequence"""
    print("\n=== Add Single Recipient Example ===")
    
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        # Define recipient data
        recipient_data = {
            'first_name': 'John',
            'company': 'Example Corp',
            'role': 'CEO',
            'email': 'john.doe@example.com'  # Use a test email
        }
        
        # Add recipient to sequence
        success = await app.scheduler.add_recipient_to_sequence(recipient_data)
        
        if success:
            print(f"✓ Added {recipient_data['email']} to email sequence")
            
            # Get sequence status
            from db.models import RecipientRepository
            recipient_repo = RecipientRepository(app.db_manager)
            recipient = await recipient_repo.get_by_email(recipient_data['email'])
            
            if recipient:
                from scheduler.sequence_manager import SequenceManager
                from db.models import EmailSequenceRepository
                sequence_repo = EmailSequenceRepository(app.db_manager)
                sequence_manager = SequenceManager(config, recipient_repo, sequence_repo)
                
                status = await sequence_manager.get_sequence_status(recipient.id)
                print(f"✓ Sequence created with {len(status['steps'])} steps")
        else:
            print("✗ Failed to add recipient")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"✗ Error: {e}")


async def example_bulk_add_recipients():
    """Example: Add multiple recipients programmatically"""
    print("\n=== Bulk Add Recipients Example ===")
    
    # Sample recipient data
    recipients_data = [
        {
            'first_name': 'Alice',
            'company': 'Tech Innovations',
            'role': 'CTO',
            'email': 'alice@techinnovations.com'
        },
        {
            'first_name': 'Bob',
            'company': 'Marketing Solutions',
            'role': 'VP Marketing',
            'email': 'bob@marketingsolutions.com'
        },
        {
            'first_name': 'Carol',
            'company': 'Sales Dynamics',
            'role': 'Sales Director',
            'email': 'carol@salesdynamics.com'
        }
    ]
    
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        successful = 0
        failed = 0
        
        for recipient_data in recipients_data:
            try:
                success = await app.scheduler.add_recipient_to_sequence(recipient_data)
                if success:
                    successful += 1
                    print(f"✓ Added {recipient_data['email']}")
                else:
                    failed += 1
                    print(f"✗ Failed to add {recipient_data['email']}")
                    
            except Exception as e:
                failed += 1
                print(f"✗ Error adding {recipient_data['email']}: {e}")
        
        print(f"\nBulk add completed: {successful} successful, {failed} failed")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"✗ Bulk add error: {e}")


async def example_email_preview():
    """Example: Preview email templates without sending"""
    print("\n=== Email Preview Example ===")
    
    try:
        from email.template_engine import EmailTemplateEngine
        
        template_engine = EmailTemplateEngine()
        
        # Sample recipient for preview
        sample_recipient = Recipient(
            first_name="John",
            company="Acme Corporation",
            role="VP of Sales",
            email="john@acme.com"
        )
        
        # Preview all email steps
        for step in [1, 2, 3]:
            try:
                preview = template_engine.render_email(step, sample_recipient)
                
                print(f"\n--- Email Step {step} Preview ---")
                print(f"Subject: {preview['subject']}")
                print(f"To: {preview['recipient_email']}")
                print("Content: [HTML content rendered successfully]")
                
            except Exception as e:
                print(f"✗ Error previewing step {step}: {e}")
        
        print("\n✓ Email preview complete")
        
    except Exception as e:
        print(f"✗ Preview error: {e}")


async def example_system_status():
    """Example: Get comprehensive system status"""
    print("\n=== System Status Example ===")
    
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        # Get scheduler status
        scheduler_status = await app.scheduler.get_scheduler_status()
        print(f"Scheduler Running: {scheduler_status.get('scheduler_running', False)}")
        print(f"Pending Emails: {scheduler_status.get('pending_emails', 0)}")
        
        # Get reply tracker status
        reply_status = app.reply_tracker.get_monitoring_status()
        print(f"Reply Monitoring: {reply_status.get('monitoring_active', False)}")
        print(f"Known Recipients: {reply_status.get('known_recipients_count', 0)}")
        
        # Get recipient statistics
        from db.models import RecipientRepository
        recipient_repo = RecipientRepository(app.db_manager)
        
        stats = {}
        for status in ['pending', 'active', 'replied', 'stopped']:
            recipients = await recipient_repo.get_all_by_status(status)
            stats[status] = len(recipients)
        
        print(f"\nRecipient Statistics:")
        for status, count in stats.items():
            print(f"  {status.title()}: {count}")
        
        # Calculate reply rate
        total_contacted = stats['active'] + stats['replied'] + stats['stopped']
        if total_contacted > 0:
            reply_rate = (stats['replied'] / total_contacted) * 100
            print(f"  Reply Rate: {reply_rate:.1f}%")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"✗ Status error: {e}")


async def example_sequence_management():
    """Example: Manage email sequences"""
    print("\n=== Sequence Management Example ===")
    
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        from db.models import RecipientRepository, EmailSequenceRepository
        from scheduler.sequence_manager import SequenceManager
        
        recipient_repo = RecipientRepository(app.db_manager)
        sequence_repo = EmailSequenceRepository(app.db_manager)
        sequence_manager = SequenceManager(config, recipient_repo, sequence_repo)
        
        # Get all active recipients
        active_recipients = await recipient_repo.get_all_by_status('active')
        
        if active_recipients:
            recipient = active_recipients[0]  # Use first active recipient
            
            print(f"Managing sequence for: {recipient.email}")
            
            # Get sequence status
            status = await sequence_manager.get_sequence_status(recipient.id)
            print(f"Current status: {status['recipient_status']}")
            print(f"Total steps: {status['total_steps']}")
            
            for step in status['steps']:
                print(f"  Step {step['step']}: {step['status']}")
                if step['scheduled_at']:
                    print(f"    Scheduled: {step['scheduled_at']}")
                if step['sent_at']:
                    print(f"    Sent: {step['sent_at']}")
            
            # Example: Pause sequence
            print(f"\nPausing sequence for {recipient.email}")
            pause_success = await sequence_manager.pause_sequence(recipient.id)
            print(f"Pause result: {'Success' if pause_success else 'Failed'}")
            
            # Example: Resume sequence
            print(f"Resuming sequence for {recipient.email}")
            resume_success = await sequence_manager.resume_sequence(recipient.id)
            print(f"Resume result: {'Success' if resume_success else 'Failed'}")
            
        else:
            print("No active recipients found for sequence management example")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"✗ Sequence management error: {e}")


async def example_analytics():
    """Example: Generate analytics and reports"""
    print("\n=== Analytics Example ===")
    
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        from db.models import RecipientRepository, EmailSequenceRepository
        from scheduler.sequence_manager import SequenceManager
        
        recipient_repo = RecipientRepository(app.db_manager)
        sequence_repo = EmailSequenceRepository(app.db_manager)
        sequence_manager = SequenceManager(config, recipient_repo, sequence_repo)
        
        # Get sequence analytics
        analytics = await sequence_manager.get_sequence_analytics()
        
        print("=== Email Sequence Analytics ===")
        print(f"Total Recipients: {analytics.get('total_recipients', 0)}")
        
        status_breakdown = analytics.get('status_breakdown', {})
        print(f"\nStatus Breakdown:")
        for status, count in status_breakdown.items():
            print(f"  {status.title()}: {count}")
        
        print(f"\nReply Rate: {analytics.get('reply_rate', 0):.1f}%")
        print(f"Completion Rate: {analytics.get('completion_rate', 0):.1f}%")
        
        step_analytics = analytics.get('step_analytics', {})
        print(f"\nStep Performance:")
        for step, data in step_analytics.items():
            print(f"  Step {step}:")
            print(f"    Sent: {data.get('sent', 0)}")
            print(f"    Pending: {data.get('pending', 0)}")
            print(f"    Replied: {data.get('replied', 0)}")
        
        await app.cleanup()
        
    except Exception as e:
        print(f"✗ Analytics error: {e}")


async def example_error_handling():
    """Example: Demonstrate error handling"""
    print("\n=== Error Handling Example ===")
    
    try:
        from error_handler import error_handler, EmailAutomationError, ErrorCategory, ErrorSeverity
        
        # Simulate different types of errors
        errors_to_test = [
            EmailAutomationError(
                "Test authentication error",
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.HIGH
            ),
            EmailAutomationError(
                "Test rate limiting error",
                ErrorCategory.RATE_LIMITING,
                ErrorSeverity.LOW
            ),
            EmailAutomationError(
                "Test database error",
                ErrorCategory.DATABASE,
                ErrorSeverity.CRITICAL
            )
        ]
        
        for error in errors_to_test:
            print(f"\nTesting error: {error.category.value}")
            result = error_handler.handle_error(error)
            print(f"  Handled: {result['error_handled']}")
            print(f"  Recoverable: {result['recoverable']}")
            print(f"  Recovery attempted: {result['recovery_attempted']}")
        
        # Get error statistics
        stats = error_handler.get_error_statistics()
        print(f"\nError Statistics:")
        print(f"  Total errors: {stats['total_errors']}")
        print(f"  Unique types: {stats['unique_error_types']}")
        
        if stats['category_breakdown']:
            print("  Category breakdown:")
            for category, count in stats['category_breakdown'].items():
                print(f"    {category}: {count}")
        
    except Exception as e:
        print(f"✗ Error handling example error: {e}")


async def main():
    """Run all examples"""
    print("Email Automation System - Usage Examples")
    print("=" * 50)
    
    examples = [
        ("Basic Setup", example_basic_setup),
        ("Add Single Recipient", example_add_single_recipient),
        ("Bulk Add Recipients", example_bulk_add_recipients),
        ("Email Preview", example_email_preview),
        ("System Status", example_system_status),
        ("Sequence Management", example_sequence_management),
        ("Analytics", example_analytics),
        ("Error Handling", example_error_handling)
    ]
    
    for name, example_func in examples:
        try:
            await example_func()
        except Exception as e:
            print(f"\n✗ Example '{name}' failed: {e}")
        
        print("\n" + "-" * 50)
    
    print("\nAll examples completed!")


if __name__ == "__main__":
    # Check if configuration exists
    if not os.path.exists('.env'):
        print("Error: .env file not found!")
        print("Please copy .env.example to .env and configure your settings.")
        sys.exit(1)
    
    asyncio.run(main())