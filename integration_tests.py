"""
Integration tests for the email automation system
Tests complete workflows and component integration
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, Any

from config import Config
from main import EmailAutomationApp
from auth.validator import AuthenticationValidator


class IntegrationTester:
    """Integration test runner"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.test_results = []
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests"""
        print("\n" + "="*60)
        print("EMAIL AUTOMATION SYSTEM - INTEGRATION TESTS")
        print("="*60)
        
        tests = [
            ("Configuration Validation", self.test_configuration),
            ("Database Initialization", self.test_database),
            ("Authentication", self.test_authentication),
            ("Email Templates", self.test_email_templates),
            ("Rate Limiting", self.test_rate_limiting),
            ("Scheduler Integration", self.test_scheduler),
            ("Reply Detection", self.test_reply_detection),
            ("End-to-End Workflow", self.test_end_to_end)
        ]
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            print(f"\nRunning: {test_name}")
            try:
                result = await test_func()
                if result['success']:
                    print(f"✓ {test_name} - PASSED")
                    passed += 1
                else:
                    print(f"✗ {test_name} - FAILED: {result.get('error', 'Unknown error')}")
                    failed += 1
                
                self.test_results.append({
                    'test': test_name,
                    'success': result['success'],
                    'details': result
                })
                
            except Exception as e:
                print(f"✗ {test_name} - ERROR: {e}")
                failed += 1
                self.test_results.append({
                    'test': test_name,
                    'success': False,
                    'error': str(e)
                })
        
        summary = {
            'total_tests': len(tests),
            'passed': passed,
            'failed': failed,
            'success_rate': (passed / len(tests)) * 100,
            'results': self.test_results
        }
        
        print(f"\n" + "="*60)
        print(f"TEST SUMMARY: {passed}/{len(tests)} passed ({summary['success_rate']:.1f}%)")
        print("="*60)
        
        return summary
    
    async def test_configuration(self) -> Dict[str, Any]:
        """Test configuration loading and validation"""
        try:
            config = Config()
            validator = AuthenticationValidator(config)
            
            # Test configuration validation
            config_valid, errors = validator.validate_configuration()
            
            return {
                'success': config_valid,
                'error': '; '.join(errors) if errors else None,
                'details': {
                    'config_loaded': True,
                    'validation_errors': errors
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_database(self) -> Dict[str, Any]:
        """Test database initialization and operations"""
        try:
            config = Config()
            app = EmailAutomationApp(config)
            
            # Test database initialization
            await app.initialize()
            
            # Test basic database operations
            from db.models import RecipientRepository, Recipient
            recipient_repo = RecipientRepository(app.db_manager)
            
            # Test create recipient
            test_recipient = Recipient(
                first_name="Test",
                company="Test Company",
                role="Test Role",
                email="test@example.com"
            )
            
            recipient_id = await recipient_repo.create(test_recipient)
            
            # Test retrieve recipient
            retrieved = await recipient_repo.get_by_id(recipient_id)
            
            # Cleanup
            await app.cleanup()
            
            return {
                'success': retrieved is not None and retrieved.email == test_recipient.email,
                'details': {
                    'database_initialized': True,
                    'create_operation': recipient_id is not None,
                    'retrieve_operation': retrieved is not None
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_authentication(self) -> Dict[str, Any]:
        """Test authentication functionality"""
        try:
            config = Config()
            validator = AuthenticationValidator(config)
            
            # Test authentication
            auth_success, auth_results = await validator.test_authentication()
            
            return {
                'success': auth_success,
                'error': '; '.join(auth_results.get('errors', [])) if not auth_success else None,
                'details': auth_results
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_email_templates(self) -> Dict[str, Any]:
        """Test email template system"""
        try:
            from email.template_engine import EmailTemplateEngine
            from db.models import Recipient
            
            template_engine = EmailTemplateEngine()
            
            # Test template validation
            validation_results = template_engine.validate_all_templates()
            all_valid = all(validation_results.values())
            
            if not all_valid:
                return {
                    'success': False,
                    'error': f'Invalid templates: {[k for k, v in validation_results.items() if not v]}',
                    'details': validation_results
                }
            
            # Test template rendering
            test_recipient = Recipient(
                first_name="John",
                company="Test Corp",
                role="CEO",
                email="john@testcorp.com"
            )
            
            rendered = template_engine.render_email(1, test_recipient)
            
            return {
                'success': True,
                'details': {
                    'template_validation': validation_results,
                    'rendering_test': {
                        'subject_rendered': bool(rendered.get('subject')),
                        'content_rendered': bool(rendered.get('html_content'))
                    }
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_rate_limiting(self) -> Dict[str, Any]:
        """Test rate limiting functionality"""
        try:
            config = Config()
            from utils.rate_limiter import RateLimiter
            
            rate_limiter = RateLimiter(config)
            
            # Test rate limit checking
            can_send_initial = await rate_limiter.can_send_email()
            
            # Test recording email sent
            await rate_limiter.record_email_sent()
            
            # Test rate status
            rate_status = rate_limiter.get_current_rate()
            
            return {
                'success': True,
                'details': {
                    'can_send_initial': can_send_initial,
                    'rate_status': rate_status
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_scheduler(self) -> Dict[str, Any]:
        """Test scheduler functionality"""
        try:
            config = Config()
            app = EmailAutomationApp(config)
            await app.initialize()
            
            # Test scheduler initialization
            scheduler_running = app.scheduler.scheduler.running
            
            # Test adding recipient to sequence
            test_data = {
                'first_name': 'Scheduler',
                'company': 'Test Company',
                'role': 'Test Role',
                'email': 'scheduler.test@example.com'
            }
            
            success = await app.scheduler.add_recipient_to_sequence(test_data)
            
            # Test getting scheduler status
            status = await app.scheduler.get_scheduler_status()
            
            await app.cleanup()
            
            return {
                'success': scheduler_running and success,
                'details': {
                    'scheduler_running': scheduler_running,
                    'add_recipient_success': success,
                    'scheduler_status': status
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_reply_detection(self) -> Dict[str, Any]:
        """Test reply detection functionality"""
        try:
            config = Config()
            app = EmailAutomationApp(config)
            await app.initialize()
            
            # Test reply tracker initialization
            test_result = await app.reply_tracker.test_reply_detection()
            
            await app.cleanup()
            
            return {
                'success': test_result.get('graph_api_connected', False) and test_result.get('inbox_accessible', False),
                'details': test_result
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def test_end_to_end(self) -> Dict[str, Any]:
        """Test complete end-to-end workflow"""
        try:
            config = Config()
            app = EmailAutomationApp(config)
            await app.initialize()
            
            # Test complete workflow without actually sending emails
            test_recipient_data = {
                'first_name': 'EndToEnd',
                'company': 'Test Workflow Corp',
                'role': 'Test Manager',
                'email': 'e2e.test@example.com'
            }
            
            # Add recipient
            add_success = await app.scheduler.add_recipient_to_sequence(test_recipient_data)
            
            # Get sequence status
            from db.models import RecipientRepository
            recipient_repo = RecipientRepository(app.db_manager)
            recipient = await recipient_repo.get_by_email(test_recipient_data['email'])
            
            sequence_status = None
            if recipient:
                from scheduler.sequence_manager import SequenceManager
                from db.models import EmailSequenceRepository
                sequence_repo = EmailSequenceRepository(app.db_manager)
                sequence_manager = SequenceManager(config, recipient_repo, sequence_repo)
                sequence_status = await sequence_manager.get_sequence_status(recipient.id)
            
            await app.cleanup()
            
            return {
                'success': add_success and recipient is not None,
                'details': {
                    'add_recipient': add_success,
                    'recipient_created': recipient is not None,
                    'sequence_status': sequence_status
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


async def run_health_check() -> Dict[str, Any]:
    """Run system health check"""
    try:
        config = Config()
        app = EmailAutomationApp(config)
        await app.initialize()
        
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_health': 'healthy',
            'components': {}
        }
        
        # Check database
        try:
            from db.models import RecipientRepository
            recipient_repo = RecipientRepository(app.db_manager)
            await recipient_repo.get_all_by_status('active')
            health_status['components']['database'] = 'healthy'
        except Exception as e:
            health_status['components']['database'] = f'unhealthy: {e}'
            health_status['overall_health'] = 'degraded'
        
        # Check authentication
        try:
            token_valid = await app.authenticator.validate_token()
            health_status['components']['authentication'] = 'healthy' if token_valid else 'unhealthy'
            if not token_valid:
                health_status['overall_health'] = 'degraded'
        except Exception as e:
            health_status['components']['authentication'] = f'unhealthy: {e}'
            health_status['overall_health'] = 'degraded'
        
        # Check scheduler
        try:
            scheduler_status = await app.scheduler.get_scheduler_status()
            is_running = scheduler_status.get('scheduler_running', False)
            health_status['components']['scheduler'] = 'healthy' if is_running else 'unhealthy'
            if not is_running:
                health_status['overall_health'] = 'degraded'
        except Exception as e:
            health_status['components']['scheduler'] = f'unhealthy: {e}'
            health_status['overall_health'] = 'degraded'
        
        # Check reply tracking
        try:
            reply_status = app.reply_tracker.get_monitoring_status()
            is_active = reply_status.get('monitoring_active', False)
            health_status['components']['reply_tracking'] = 'healthy' if is_active else 'unhealthy'
            if not is_active:
                health_status['overall_health'] = 'degraded'
        except Exception as e:
            health_status['components']['reply_tracking'] = f'unhealthy: {e}'
            health_status['overall_health'] = 'degraded'
        
        await app.cleanup()
        
        return health_status
        
    except Exception as e:
        return {
            'timestamp': datetime.now().isoformat(),
            'overall_health': 'critical',
            'error': str(e)
        }


async def main():
    """Main function for integration tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Email Automation Integration Tests')
    parser.add_argument('--health-check', action='store_true', help='Run health check only')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    
    if args.health_check:
        health_status = await run_health_check()
        print(f"\nSystem Health: {health_status['overall_health'].upper()}")
        for component, status in health_status.get('components', {}).items():
            print(f"  {component}: {status}")
        
        if health_status['overall_health'] == 'critical':
            print(f"  Error: {health_status.get('error', 'Unknown error')}")
        
        return health_status['overall_health'] == 'healthy'
    
    else:
        tester = IntegrationTester()
        results = await tester.run_all_tests()
        
        # Exit with error code if tests failed
        if results['failed'] > 0:
            sys.exit(1)
        
        return True


if __name__ == "__main__":
    asyncio.run(main())