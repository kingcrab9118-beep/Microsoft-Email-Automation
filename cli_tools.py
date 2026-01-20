"""
Command-line tools and utilities for email automation system
Provides helper functions for CLI operations
"""

import asyncio
import json
import csv
from typing import List, Dict, Any
from pathlib import Path

from config import Config
from main import EmailAutomationApp


async def bulk_add_recipients_from_csv(csv_file_path: str) -> Dict[str, Any]:
    """Add multiple recipients from CSV file"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        results = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        # Read CSV file
        with open(csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            for row in reader:
                results['total'] += 1
                
                try:
                    # Validate required fields
                    required_fields = ['first_name', 'company', 'role', 'email']
                    if not all(field in row and row[field].strip() for field in required_fields):
                        results['failed'] += 1
                        results['errors'].append({
                            'row': results['total'],
                            'email': row.get('email', 'unknown'),
                            'error': 'Missing required fields'
                        })
                        continue
                    
                    # Clean data
                    recipient_data = {
                        'first_name': row['first_name'].strip(),
                        'company': row['company'].strip(),
                        'role': row['role'].strip(),
                        'email': row['email'].strip().lower()
                    }
                    
                    # Add recipient
                    success = await app.scheduler.add_recipient_to_sequence(recipient_data)
                    
                    if success:
                        results['successful'] += 1
                        print(f"✓ Added {recipient_data['email']}")
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'row': results['total'],
                            'email': recipient_data['email'],
                            'error': 'Failed to add to sequence'
                        })
                        print(f"✗ Failed to add {recipient_data['email']}")
                
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append({
                        'row': results['total'],
                        'email': row.get('email', 'unknown'),
                        'error': str(e)
                    })
                    print(f"✗ Error processing row {results['total']}: {e}")
        
        await app.cleanup()
        
        print(f"\nBulk import completed:")
        print(f"  Total: {results['total']}")
        print(f"  Successful: {results['successful']}")
        print(f"  Failed: {results['failed']}")
        
        return results
        
    except Exception as e:
        print(f"Error in bulk import: {e}")
        return {'error': str(e)}


async def export_recipients_to_csv(output_file_path: str) -> bool:
    """Export all recipients to CSV file"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        from db.models import RecipientRepository
        recipient_repo = RecipientRepository(app.db_manager)
        
        # Get all recipients
        all_recipients = []
        for status in ['pending', 'active', 'replied', 'stopped']:
            recipients = await recipient_repo.get_all_by_status(status)
            all_recipients.extend(recipients)
        
        # Write to CSV
        with open(output_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'first_name', 'company', 'role', 'email', 'status', 'created_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for recipient in all_recipients:
                writer.writerow({
                    'id': recipient.id,
                    'first_name': recipient.first_name,
                    'company': recipient.company,
                    'role': recipient.role,
                    'email': recipient.email,
                    'status': recipient.status,
                    'created_at': recipient.created_at
                })
        
        await app.cleanup()
        
        print(f"✓ Exported {len(all_recipients)} recipients to {output_file_path}")
        return True
        
    except Exception as e:
        print(f"Error exporting recipients: {e}")
        return False


async def generate_analytics_report() -> Dict[str, Any]:
    """Generate comprehensive analytics report"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        from db.models import RecipientRepository, EmailSequenceRepository
        from scheduler.sequence_manager import SequenceManager
        
        recipient_repo = RecipientRepository(app.db_manager)
        sequence_repo = EmailSequenceRepository(app.db_manager)
        sequence_manager = SequenceManager(config, recipient_repo, sequence_repo)
        
        # Get analytics
        analytics = await sequence_manager.get_sequence_analytics()
        
        # Get reply statistics
        reply_stats = await app.sequence_stopper.get_reply_statistics()
        
        # Combine reports
        report = {
            'generated_at': asyncio.get_event_loop().time(),
            'sequence_analytics': analytics,
            'reply_statistics': reply_stats,
            'configuration': {
                'follow_up_1_delay_days': config.follow_up_1_delay_days,
                'follow_up_2_enabled': config.follow_up_2_enabled,
                'follow_up_2_delay_days': config.follow_up_2_delay_days,
                'rate_limit_per_minute': config.rate_limit_per_minute
            }
        }
        
        await app.cleanup()
        
        return report
        
    except Exception as e:
        print(f"Error generating analytics report: {e}")
        return {'error': str(e)}


def create_sample_csv(output_path: str = "sample_recipients.csv"):
    """Create a sample CSV file for bulk import"""
    sample_data = [
        {
            'first_name': 'John',
            'company': 'Acme Corporation',
            'role': 'CEO',
            'email': 'john.doe@acme.com'
        },
        {
            'first_name': 'Jane',
            'company': 'Tech Solutions Inc',
            'role': 'VP of Sales',
            'email': 'jane.smith@techsolutions.com'
        },
        {
            'first_name': 'Mike',
            'company': 'Global Industries',
            'role': 'Director of Marketing',
            'email': 'mike.johnson@globalind.com'
        }
    ]
    
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['first_name', 'company', 'role', 'email']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in sample_data:
                writer.writerow(row)
        
        print(f"✓ Created sample CSV file: {output_path}")
        print("Edit this file with your recipient data, then use:")
        print(f"python cli_tools.py bulk-import {output_path}")
        
        return True
        
    except Exception as e:
        print(f"Error creating sample CSV: {e}")
        return False


async def main():
    """CLI tools main function"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Email Automation CLI Tools')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Bulk import command
    import_parser = subparsers.add_parser('bulk-import', help='Import recipients from CSV')
    import_parser.add_argument('csv_file', help='Path to CSV file')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export recipients to CSV')
    export_parser.add_argument('output_file', help='Output CSV file path')
    
    # Analytics command
    analytics_parser = subparsers.add_parser('analytics', help='Generate analytics report')
    analytics_parser.add_argument('--output', help='Output JSON file (optional)')
    
    # Sample CSV command
    sample_parser = subparsers.add_parser('create-sample', help='Create sample CSV file')
    sample_parser.add_argument('--output', default='sample_recipients.csv', help='Output file path')
    
    args = parser.parse_args()
    
    if args.command == 'bulk-import':
        await bulk_add_recipients_from_csv(args.csv_file)
    elif args.command == 'export':
        await export_recipients_to_csv(args.output_file)
    elif args.command == 'analytics':
        report = await generate_analytics_report()
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"✓ Analytics report saved to {args.output}")
        else:
            print(json.dumps(report, indent=2, default=str))
    elif args.command == 'create-sample':
        create_sample_csv(args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())