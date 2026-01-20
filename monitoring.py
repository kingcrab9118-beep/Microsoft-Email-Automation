"""
Production monitoring and health checks for email automation system
Provides comprehensive monitoring, metrics, and alerting capabilities
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from config import Config
from main import EmailAutomationApp


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Individual health check result"""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any] = None
    timestamp: datetime = None
    response_time_ms: float = 0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: datetime
    emails_sent_last_hour: int = 0
    emails_sent_last_day: int = 0
    active_recipients: int = 0
    pending_emails: int = 0
    reply_rate_percent: float = 0.0
    error_rate_percent: float = 0.0
    avg_response_time_ms: float = 0.0
    database_connections: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0


class HealthMonitor:
    """Comprehensive health monitoring system"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.app: Optional[EmailAutomationApp] = None
        self.last_metrics: Optional[SystemMetrics] = None
        self.health_history: List[HealthCheck] = []
        self.max_history_size = 1000
    
    async def initialize(self):
        """Initialize monitoring system"""
        try:
            self.app = EmailAutomationApp(self.config)
            await self.app.initialize()
            self.logger.info("Health monitor initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize health monitor: {e}")
            raise
    
    async def run_comprehensive_health_check(self) -> Dict[str, Any]:
        """Run all health checks and return comprehensive status"""
        start_time = time.time()
        
        health_checks = [
            ("Database", self._check_database_health),
            ("Authentication", self._check_authentication_health),
            ("Email System", self._check_email_system_health),
            ("Scheduler", self._check_scheduler_health),
            ("Reply Tracking", self._check_reply_tracking_health),
            ("Rate Limiting", self._check_rate_limiting_health),
            ("System Resources", self._check_system_resources)
        ]
        
        results = []
        overall_status = HealthStatus.HEALTHY
        
        for check_name, check_func in health_checks:
            try:
                check_start = time.time()
                check_result = await check_func()
                check_time = (time.time() - check_start) * 1000
                
                health_check = HealthCheck(
                    name=check_name,
                    status=check_result['status'],
                    message=check_result['message'],
                    details=check_result.get('details', {}),
                    response_time_ms=check_time
                )
                
                results.append(health_check)
                self._update_health_history(health_check)
                
                # Update overall status
                if check_result['status'] == HealthStatus.CRITICAL:
                    overall_status = HealthStatus.CRITICAL
                elif check_result['status'] == HealthStatus.UNHEALTHY and overall_status != HealthStatus.CRITICAL:
                    overall_status = HealthStatus.UNHEALTHY
                elif check_result['status'] == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                
            except Exception as e:
                error_check = HealthCheck(
                    name=check_name,
                    status=HealthStatus.CRITICAL,
                    message=f"Health check failed: {str(e)}",
                    details={'error': str(e)}
                )
                results.append(error_check)
                overall_status = HealthStatus.CRITICAL
        
        total_time = (time.time() - start_time) * 1000
        
        return {
            'overall_status': overall_status.value,
            'timestamp': datetime.now().isoformat(),
            'total_check_time_ms': total_time,
            'checks': [asdict(check) for check in results],
            'summary': self._generate_health_summary(results)
        }
    
    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance"""
        try:
            start_time = time.time()
            
            # Test basic connectivity
            from db.models import RecipientRepository
            recipient_repo = RecipientRepository(self.app.db_manager)
            
            # Test query performance
            active_recipients = await recipient_repo.get_all_by_status('active')
            query_time = (time.time() - start_time) * 1000
            
            # Check database size (for SQLite)
            db_size = 0
            if self.config.database_url.startswith('sqlite'):
                import os
                db_file = self.config.database_url.replace('sqlite:///', '')
                if os.path.exists(db_file):
                    db_size = os.path.getsize(db_file) / (1024 * 1024)  # MB
            
            status = HealthStatus.HEALTHY
            message = "Database is healthy"
            
            if query_time > 1000:  # > 1 second
                status = HealthStatus.DEGRADED
                message = "Database queries are slow"
            elif query_time > 5000:  # > 5 seconds
                status = HealthStatus.UNHEALTHY
                message = "Database performance is poor"
            
            return {
                'status': status,
                'message': message,
                'details': {
                    'query_time_ms': query_time,
                    'active_recipients': len(active_recipients),
                    'database_size_mb': db_size,
                    'connection_string': self.config.database_url.split('@')[0] + '@***'  # Hide credentials
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Database check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_authentication_health(self) -> Dict[str, Any]:
        """Check authentication system health"""
        try:
            # Test token validation
            token_valid = await self.app.authenticator.validate_token()
            
            # Test permissions
            permissions = await self.app.authenticator.test_permissions()
            
            required_permissions = ['mail_send', 'mail_read']
            missing_permissions = [p for p in required_permissions if not permissions.get(p, False)]
            
            if not token_valid:
                return {
                    'status': HealthStatus.CRITICAL,
                    'message': "Authentication token is invalid",
                    'details': {'token_valid': False, 'permissions': permissions}
                }
            
            if missing_permissions:
                return {
                    'status': HealthStatus.UNHEALTHY,
                    'message': f"Missing permissions: {missing_permissions}",
                    'details': {'token_valid': True, 'missing_permissions': missing_permissions}
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "Authentication is healthy",
                'details': {'token_valid': True, 'permissions': permissions}
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Authentication check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_email_system_health(self) -> Dict[str, Any]:
        """Check email system health"""
        try:
            # Validate email templates
            from email.template_engine import EmailTemplateEngine
            template_engine = EmailTemplateEngine()
            
            template_validation = template_engine.validate_all_templates()
            invalid_templates = [step for step, valid in template_validation.items() if not valid]
            
            # Check sender email validation
            sender_valid = await self.app.email_sender.validate_sender_email()
            
            if invalid_templates:
                return {
                    'status': HealthStatus.UNHEALTHY,
                    'message': f"Invalid email templates: {invalid_templates}",
                    'details': {
                        'template_validation': template_validation,
                        'sender_valid': sender_valid
                    }
                }
            
            if not sender_valid:
                return {
                    'status': HealthStatus.DEGRADED,
                    'message': "Sender email validation failed",
                    'details': {
                        'template_validation': template_validation,
                        'sender_valid': sender_valid
                    }
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "Email system is healthy",
                'details': {
                    'template_validation': template_validation,
                    'sender_valid': sender_valid
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Email system check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_scheduler_health(self) -> Dict[str, Any]:
        """Check scheduler health"""
        try:
            scheduler_status = await self.app.scheduler.get_scheduler_status()
            
            is_running = scheduler_status.get('scheduler_running', False)
            pending_emails = scheduler_status.get('pending_emails', 0)
            jobs_count = scheduler_status.get('jobs_count', 0)
            
            if not is_running:
                return {
                    'status': HealthStatus.CRITICAL,
                    'message': "Scheduler is not running",
                    'details': scheduler_status
                }
            
            # Check for excessive pending emails (might indicate issues)
            if pending_emails > 100:
                return {
                    'status': HealthStatus.DEGRADED,
                    'message': f"High number of pending emails: {pending_emails}",
                    'details': scheduler_status
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "Scheduler is healthy",
                'details': scheduler_status
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Scheduler check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_reply_tracking_health(self) -> Dict[str, Any]:
        """Check reply tracking system health"""
        try:
            # Test reply detection functionality
            test_result = await self.app.reply_tracker.test_reply_detection()
            
            monitoring_status = self.app.reply_tracker.get_monitoring_status()
            
            if test_result.get('error'):
                return {
                    'status': HealthStatus.UNHEALTHY,
                    'message': f"Reply tracking error: {test_result['error']}",
                    'details': {**test_result, **monitoring_status}
                }
            
            if not test_result.get('graph_api_connected', False):
                return {
                    'status': HealthStatus.CRITICAL,
                    'message': "Cannot connect to Graph API for reply tracking",
                    'details': {**test_result, **monitoring_status}
                }
            
            if not test_result.get('inbox_accessible', False):
                return {
                    'status': HealthStatus.UNHEALTHY,
                    'message': "Inbox is not accessible for reply tracking",
                    'details': {**test_result, **monitoring_status}
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "Reply tracking is healthy",
                'details': {**test_result, **monitoring_status}
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Reply tracking check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_rate_limiting_health(self) -> Dict[str, Any]:
        """Check rate limiting system health"""
        try:
            rate_status = self.app.scheduler.rate_limiter.get_adaptive_status()
            
            current_minute_count = rate_status.get('current_minute_count', 0)
            max_per_minute = rate_status.get('max_per_minute', 30)
            current_daily_count = rate_status.get('current_daily_count', 0)
            max_per_day = rate_status.get('max_per_day', 10000)
            
            # Check if we're hitting limits frequently
            minute_usage = (current_minute_count / max_per_minute) * 100
            daily_usage = (current_daily_count / max_per_day) * 100
            
            if daily_usage > 90:
                return {
                    'status': HealthStatus.DEGRADED,
                    'message': f"Daily rate limit usage high: {daily_usage:.1f}%",
                    'details': rate_status
                }
            
            if minute_usage > 80:
                return {
                    'status': HealthStatus.DEGRADED,
                    'message': f"Minute rate limit usage high: {minute_usage:.1f}%",
                    'details': rate_status
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "Rate limiting is healthy",
                'details': rate_status
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Rate limiting check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            import psutil
            
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info().rss / (1024 * 1024)  # MB
            process_cpu = process.cpu_percent()
            
            details = {
                'system_cpu_percent': cpu_percent,
                'system_memory_percent': memory.percent,
                'system_disk_percent': disk.percent,
                'process_memory_mb': process_memory,
                'process_cpu_percent': process_cpu
            }
            
            # Determine status based on resource usage
            if cpu_percent > 90 or memory.percent > 90 or disk.percent > 95:
                return {
                    'status': HealthStatus.CRITICAL,
                    'message': "Critical resource usage detected",
                    'details': details
                }
            
            if cpu_percent > 70 or memory.percent > 80 or disk.percent > 85:
                return {
                    'status': HealthStatus.DEGRADED,
                    'message': "High resource usage detected",
                    'details': details
                }
            
            return {
                'status': HealthStatus.HEALTHY,
                'message': "System resources are healthy",
                'details': details
            }
            
        except ImportError:
            return {
                'status': HealthStatus.HEALTHY,
                'message': "System resource monitoring not available (psutil not installed)",
                'details': {'psutil_available': False}
            }
        except Exception as e:
            return {
                'status': HealthStatus.DEGRADED,
                'message': f"System resource check failed: {str(e)}",
                'details': {'error': str(e)}
            }
    
    def _update_health_history(self, health_check: HealthCheck):
        """Update health check history"""
        self.health_history.append(health_check)
        
        # Trim history if too large
        if len(self.health_history) > self.max_history_size:
            self.health_history = self.health_history[-self.max_history_size:]
    
    def _generate_health_summary(self, checks: List[HealthCheck]) -> Dict[str, Any]:
        """Generate summary of health checks"""
        status_counts = {}
        total_response_time = 0
        
        for check in checks:
            status = check.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            total_response_time += check.response_time_ms
        
        avg_response_time = total_response_time / len(checks) if checks else 0
        
        return {
            'total_checks': len(checks),
            'status_breakdown': status_counts,
            'average_response_time_ms': avg_response_time,
            'checks_passed': status_counts.get('healthy', 0),
            'checks_failed': status_counts.get('critical', 0) + status_counts.get('unhealthy', 0)
        }
    
    async def collect_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            from db.models import RecipientRepository, EmailSequenceRepository
            
            recipient_repo = RecipientRepository(self.app.db_manager)
            sequence_repo = EmailSequenceRepository(self.app.db_manager)
            
            # Get recipient counts
            active_recipients = await recipient_repo.get_all_by_status('active')
            replied_recipients = await recipient_repo.get_all_by_status('replied')
            
            # Get pending emails
            due_emails = await sequence_repo.get_due_emails()
            
            # Calculate reply rate
            total_contacted = len(active_recipients) + len(replied_recipients)
            reply_rate = (len(replied_recipients) / total_contacted * 100) if total_contacted > 0 else 0
            
            # Get rate limiting info
            rate_status = self.app.scheduler.rate_limiter.get_adaptive_status()
            
            # Get system resources (if available)
            memory_usage = 0
            cpu_usage = 0
            try:
                import psutil
                process = psutil.Process()
                memory_usage = process.memory_info().rss / (1024 * 1024)  # MB
                cpu_usage = process.cpu_percent()
            except ImportError:
                pass
            
            metrics = SystemMetrics(
                timestamp=datetime.now(),
                active_recipients=len(active_recipients),
                pending_emails=len(due_emails),
                reply_rate_percent=reply_rate,
                emails_sent_last_day=rate_status.get('current_daily_count', 0),
                memory_usage_mb=memory_usage,
                cpu_usage_percent=cpu_usage
            )
            
            self.last_metrics = metrics
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
            return SystemMetrics(timestamp=datetime.now())
    
    def get_health_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Get health trends over specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_checks = [
            check for check in self.health_history 
            if check.timestamp >= cutoff_time
        ]
        
        if not recent_checks:
            return {'message': 'No health check data available for the specified period'}
        
        # Group by check name
        trends = {}
        for check in recent_checks:
            if check.name not in trends:
                trends[check.name] = []
            trends[check.name].append({
                'timestamp': check.timestamp.isoformat(),
                'status': check.status.value,
                'response_time_ms': check.response_time_ms
            })
        
        # Calculate trend statistics
        trend_stats = {}
        for check_name, check_data in trends.items():
            statuses = [item['status'] for item in check_data]
            response_times = [item['response_time_ms'] for item in check_data]
            
            trend_stats[check_name] = {
                'total_checks': len(check_data),
                'healthy_count': statuses.count('healthy'),
                'degraded_count': statuses.count('degraded'),
                'unhealthy_count': statuses.count('unhealthy'),
                'critical_count': statuses.count('critical'),
                'avg_response_time_ms': sum(response_times) / len(response_times),
                'max_response_time_ms': max(response_times),
                'min_response_time_ms': min(response_times)
            }
        
        return {
            'period_hours': hours,
            'total_checks': len(recent_checks),
            'trends': trend_stats,
            'raw_data': trends
        }
    
    async def cleanup(self):
        """Cleanup monitoring resources"""
        if self.app:
            await self.app.cleanup()


async def run_monitoring_server(config: Config, port: int = 8080):
    """Run a simple HTTP monitoring server"""
    try:
        from aiohttp import web, web_response
        
        monitor = HealthMonitor(config)
        await monitor.initialize()
        
        async def health_endpoint(request):
            """Health check endpoint"""
            health_status = await monitor.run_comprehensive_health_check()
            
            # Set HTTP status based on health
            http_status = 200
            if health_status['overall_status'] in ['unhealthy', 'critical']:
                http_status = 503
            elif health_status['overall_status'] == 'degraded':
                http_status = 200  # Still operational
            
            return web_response.json_response(health_status, status=http_status)
        
        async def metrics_endpoint(request):
            """Metrics endpoint"""
            metrics = await monitor.collect_metrics()
            return web_response.json_response(asdict(metrics))
        
        async def trends_endpoint(request):
            """Health trends endpoint"""
            hours = int(request.query.get('hours', 24))
            trends = monitor.get_health_trends(hours)
            return web_response.json_response(trends)
        
        # Create web application
        app = web.Application()
        app.router.add_get('/health', health_endpoint)
        app.router.add_get('/metrics', metrics_endpoint)
        app.router.add_get('/trends', trends_endpoint)
        
        # Start server
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, 'localhost', port)
        await site.start()
        
        print(f"Monitoring server started on http://localhost:{port}")
        print(f"Health check: http://localhost:{port}/health")
        print(f"Metrics: http://localhost:{port}/metrics")
        print(f"Trends: http://localhost:{port}/trends")
        
        # Keep server running
        try:
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour
        except KeyboardInterrupt:
            print("Shutting down monitoring server...")
        finally:
            await monitor.cleanup()
            await runner.cleanup()
            
    except ImportError:
        print("aiohttp not installed. Install with: pip install aiohttp")
        print("Running basic health check instead...")
        
        monitor = HealthMonitor(config)
        await monitor.initialize()
        
        try:
            while True:
                health_status = await monitor.run_comprehensive_health_check()
                print(f"\n[{datetime.now()}] Overall Status: {health_status['overall_status'].upper()}")
                
                for check in health_status['checks']:
                    status_icon = "✓" if check['status'] == 'healthy' else "✗"
                    print(f"  {status_icon} {check['name']}: {check['message']}")
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
        except KeyboardInterrupt:
            print("Shutting down health monitor...")
        finally:
            await monitor.cleanup()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Email Automation Monitoring')
    parser.add_argument('--port', type=int, default=8080, help='Monitoring server port')
    parser.add_argument('--check-only', action='store_true', help='Run single health check and exit')
    
    args = parser.parse_args()
    
    config = Config()
    
    if args.check_only:
        async def single_check():
            monitor = HealthMonitor(config)
            await monitor.initialize()
            health_status = await monitor.run_comprehensive_health_check()
            print(json.dumps(health_status, indent=2, default=str))
            await monitor.cleanup()
        
        asyncio.run(single_check())
    else:
        asyncio.run(run_monitoring_server(config, args.port))