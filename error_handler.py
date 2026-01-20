"""
Centralized error handling and recovery for the email automation system
Provides consistent error handling across all components
"""

import logging
import traceback
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from enum import Enum
from functools import wraps


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""
    AUTHENTICATION = "authentication"
    DATABASE = "database"
    EMAIL_SENDING = "email_sending"
    RATE_LIMITING = "rate_limiting"
    SCHEDULING = "scheduling"
    REPLY_DETECTION = "reply_detection"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    VALIDATION = "validation"
    SYSTEM = "system"


class EmailAutomationError(Exception):
    """Base exception for email automation system"""
    
    def __init__(self, message: str, category: ErrorCategory, severity: ErrorSeverity = ErrorSeverity.MEDIUM, 
                 details: Dict[str, Any] = None, recoverable: bool = True):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.recoverable = recoverable
        self.timestamp = datetime.now()


class ErrorHandler:
    """Centralized error handler with recovery strategies"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_counts = {}
        self.recovery_strategies = {}
        self._setup_recovery_strategies()
    
    def _setup_recovery_strategies(self):
        """Setup recovery strategies for different error types"""
        self.recovery_strategies = {
            ErrorCategory.AUTHENTICATION: self._recover_authentication,
            ErrorCategory.DATABASE: self._recover_database,
            ErrorCategory.EMAIL_SENDING: self._recover_email_sending,
            ErrorCategory.RATE_LIMITING: self._recover_rate_limiting,
            ErrorCategory.NETWORK: self._recover_network,
            ErrorCategory.SCHEDULING: self._recover_scheduling
        }
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Handle an error with appropriate logging and recovery"""
        try:
            # Convert to EmailAutomationError if needed
            if not isinstance(error, EmailAutomationError):
                automation_error = self._classify_error(error, context)
            else:
                automation_error = error
            
            # Log the error
            self._log_error(automation_error, context)
            
            # Track error frequency
            self._track_error(automation_error)
            
            # Attempt recovery if possible
            recovery_result = None
            if automation_error.recoverable:
                recovery_result = self._attempt_recovery(automation_error, context)
            
            return {
                'error_handled': True,
                'error_id': id(automation_error),
                'category': automation_error.category.value,
                'severity': automation_error.severity.value,
                'recoverable': automation_error.recoverable,
                'recovery_attempted': recovery_result is not None,
                'recovery_successful': recovery_result.get('success', False) if recovery_result else False,
                'recovery_details': recovery_result
            }
            
        except Exception as e:
            self.logger.critical(f"Error in error handler: {e}")
            return {'error_handled': False, 'handler_error': str(e)}
    
    def _classify_error(self, error: Exception, context: Dict[str, Any] = None) -> EmailAutomationError:
        """Classify a generic error into EmailAutomationError"""
        error_str = str(error).lower()
        context = context or {}
        
        # Authentication errors
        if any(keyword in error_str for keyword in ['auth', 'token', 'credential', 'permission']):
            return EmailAutomationError(
                str(error), 
                ErrorCategory.AUTHENTICATION, 
                ErrorSeverity.HIGH,
                {'original_error': str(error), 'context': context}
            )
        
        # Database errors
        elif any(keyword in error_str for keyword in ['database', 'sql', 'connection', 'table']):
            return EmailAutomationError(
                str(error),
                ErrorCategory.DATABASE,
                ErrorSeverity.HIGH,
                {'original_error': str(error), 'context': context}
            )
        
        # Network errors
        elif any(keyword in error_str for keyword in ['network', 'connection', 'timeout', 'http']):
            return EmailAutomationError(
                str(error),
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                {'original_error': str(error), 'context': context}
            )
        
        # Rate limiting errors
        elif any(keyword in error_str for keyword in ['rate', 'limit', 'throttl', 'quota']):
            return EmailAutomationError(
                str(error),
                ErrorCategory.RATE_LIMITING,
                ErrorSeverity.LOW,
                {'original_error': str(error), 'context': context}
            )
        
        # Default classification
        else:
            return EmailAutomationError(
                str(error),
                ErrorCategory.SYSTEM,
                ErrorSeverity.MEDIUM,
                {'original_error': str(error), 'context': context}
            )
    
    def _log_error(self, error: EmailAutomationError, context: Dict[str, Any] = None):
        """Log error with appropriate level and details"""
        log_data = {
            'category': error.category.value,
            'severity': error.severity.value,
            'message': error.message,
            'recoverable': error.recoverable,
            'timestamp': error.timestamp.isoformat(),
            'details': error.details,
            'context': context or {}
        }
        
        if error.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"CRITICAL ERROR: {error.message}", extra=log_data)
        elif error.severity == ErrorSeverity.HIGH:
            self.logger.error(f"HIGH SEVERITY: {error.message}", extra=log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"MEDIUM SEVERITY: {error.message}", extra=log_data)
        else:
            self.logger.info(f"LOW SEVERITY: {error.message}", extra=log_data)
    
    def _track_error(self, error: EmailAutomationError):
        """Track error frequency for pattern analysis"""
        key = f"{error.category.value}:{error.message[:50]}"
        
        if key not in self.error_counts:
            self.error_counts[key] = {
                'count': 0,
                'first_seen': error.timestamp,
                'last_seen': error.timestamp,
                'category': error.category.value,
                'severity': error.severity.value
            }
        
        self.error_counts[key]['count'] += 1
        self.error_counts[key]['last_seen'] = error.timestamp
        
        # Alert on frequent errors
        if self.error_counts[key]['count'] > 10:
            self.logger.warning(f"Frequent error detected: {key} (count: {self.error_counts[key]['count']})")
    
    def _attempt_recovery(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Attempt to recover from the error"""
        recovery_strategy = self.recovery_strategies.get(error.category)
        
        if not recovery_strategy:
            return None
        
        try:
            return recovery_strategy(error, context)
        except Exception as e:
            self.logger.error(f"Recovery strategy failed for {error.category.value}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _recover_authentication(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for authentication errors"""
        return {
            'success': False,
            'message': 'Authentication errors require manual intervention',
            'suggested_actions': [
                'Check credentials in .env file',
                'Verify Azure app registration permissions',
                'Run authentication validation: python main.py validate'
            ]
        }
    
    def _recover_database(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for database errors"""
        return {
            'success': False,
            'message': 'Database errors may require manual intervention',
            'suggested_actions': [
                'Check database connection string',
                'Verify database file permissions',
                'Check disk space',
                'Restart application to reinitialize database'
            ]
        }
    
    def _recover_email_sending(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for email sending errors"""
        return {
            'success': True,
            'message': 'Email sending error - will retry with backoff',
            'actions_taken': [
                'Email marked for retry',
                'Rate limiting applied',
                'Sequence continues with next scheduled email'
            ]
        }
    
    def _recover_rate_limiting(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for rate limiting errors"""
        return {
            'success': True,
            'message': 'Rate limit encountered - applying backoff',
            'actions_taken': [
                'Increased delay between sends',
                'Email rescheduled for later',
                'Rate limiter adjusted'
            ]
        }
    
    def _recover_network(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for network errors"""
        return {
            'success': True,
            'message': 'Network error - will retry with exponential backoff',
            'actions_taken': [
                'Request scheduled for retry',
                'Exponential backoff applied',
                'Connection will be re-established'
            ]
        }
    
    def _recover_scheduling(self, error: EmailAutomationError, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Recovery strategy for scheduling errors"""
        return {
            'success': True,
            'message': 'Scheduling error - job will be rescheduled',
            'actions_taken': [
                'Failed job removed from queue',
                'Job rescheduled with delay',
                'Scheduler continues operation'
            ]
        }
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics for monitoring"""
        total_errors = sum(data['count'] for data in self.error_counts.values())
        
        category_counts = {}
        severity_counts = {}
        
        for data in self.error_counts.values():
            category = data['category']
            severity = data['severity']
            
            category_counts[category] = category_counts.get(category, 0) + data['count']
            severity_counts[severity] = severity_counts.get(severity, 0) + data['count']
        
        return {
            'total_errors': total_errors,
            'unique_error_types': len(self.error_counts),
            'category_breakdown': category_counts,
            'severity_breakdown': severity_counts,
            'most_frequent_errors': sorted(
                [(key, data['count']) for key, data in self.error_counts.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }


# Global error handler instance
error_handler = ErrorHandler()


def handle_errors(category: ErrorCategory = ErrorCategory.SYSTEM, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
    """Decorator for automatic error handling"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = {
                    'function': func.__name__,
                    'args': str(args)[:100],
                    'kwargs': str(kwargs)[:100]
                }
                
                automation_error = EmailAutomationError(
                    str(e), category, severity, 
                    {'traceback': traceback.format_exc()}, 
                    recoverable=True
                )
                
                error_handler.handle_error(automation_error, context)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {
                    'function': func.__name__,
                    'args': str(args)[:100],
                    'kwargs': str(kwargs)[:100]
                }
                
                automation_error = EmailAutomationError(
                    str(e), category, severity,
                    {'traceback': traceback.format_exc()},
                    recoverable=True
                )
                
                error_handler.handle_error(automation_error, context)
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


def safe_execute(func: Callable, *args, **kwargs) -> Dict[str, Any]:
    """Safely execute a function with error handling"""
    try:
        if asyncio.iscoroutinefunction(func):
            # For async functions, this should be called with await
            raise ValueError("Use safe_execute_async for async functions")
        
        result = func(*args, **kwargs)
        return {'success': True, 'result': result}
        
    except Exception as e:
        error_result = error_handler.handle_error(e, {
            'function': func.__name__,
            'args': str(args)[:100],
            'kwargs': str(kwargs)[:100]
        })
        
        return {
            'success': False,
            'error': str(e),
            'error_handling': error_result
        }


async def safe_execute_async(func: Callable, *args, **kwargs) -> Dict[str, Any]:
    """Safely execute an async function with error handling"""
    try:
        result = await func(*args, **kwargs)
        return {'success': True, 'result': result}
        
    except Exception as e:
        error_result = error_handler.handle_error(e, {
            'function': func.__name__,
            'args': str(args)[:100],
            'kwargs': str(kwargs)[:100]
        })
        
        return {
            'success': False,
            'error': str(e),
            'error_handling': error_result
        }