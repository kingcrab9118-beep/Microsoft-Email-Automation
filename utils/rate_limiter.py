"""
Rate limiting implementation for Microsoft 365 email sending
Ensures compliance with sending limits and prevents bulk blasting
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from collections import deque
import json
import os

from config import Config


class RateLimiter:
    """Rate limiter for email sending to comply with Microsoft 365 limits"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Rate limiting configuration
        self.max_per_minute = config.rate_limit_per_minute
        self.max_per_day = config.rate_limit_per_day
        
        # Tracking data structures
        self.minute_window = deque()  # Timestamps of emails sent in current minute
        self.daily_count = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        # Persistence file for rate limiting data
        self.persistence_file = "rate_limiter_state.json"
        
        # Load persisted state
        self._load_state()
        
        self.logger.info(f"Rate limiter initialized: {self.max_per_minute}/min, {self.max_per_day}/day")
    
    async def can_send_email(self) -> bool:
        """Check if an email can be sent without exceeding rate limits"""
        current_time = datetime.now()
        
        # Clean up old entries and check daily reset
        self._cleanup_old_entries(current_time)
        
        # Check minute limit
        if len(self.minute_window) >= self.max_per_minute:
            self.logger.warning(f"Minute rate limit reached: {len(self.minute_window)}/{self.max_per_minute}")
            return False
        
        # Check daily limit
        if self.daily_count >= self.max_per_day:
            self.logger.warning(f"Daily rate limit reached: {self.daily_count}/{self.max_per_day}")
            return False
        
        return True
    
    async def record_email_sent(self):
        """Record that an email was sent"""
        current_time = datetime.now()
        
        # Add to minute window
        self.minute_window.append(current_time)
        
        # Increment daily count
        self.daily_count += 1
        
        # Persist state
        self._save_state()
        
        self.logger.debug(f"Email recorded: {len(self.minute_window)} in current minute, {self.daily_count} today")
    
    def _cleanup_old_entries(self, current_time: datetime):
        """Remove old entries from tracking windows"""
        # Clean minute window (remove entries older than 1 minute)
        minute_ago = current_time - timedelta(minutes=1)
        while self.minute_window and self.minute_window[0] < minute_ago:
            self.minute_window.popleft()
        
        # Reset daily count if it's a new day
        if current_time >= self.daily_reset_time:
            self.daily_count = 0
            self.daily_reset_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            self.logger.info("Daily rate limit counter reset")
    
    def get_current_rate(self) -> Dict[str, Any]:
        """Get current rate limiting status"""
        current_time = datetime.now()
        self._cleanup_old_entries(current_time)
        
        # Calculate time until next available slot
        next_minute_slot = None
        next_day_slot = None
        
        if len(self.minute_window) >= self.max_per_minute:
            # Next slot available when oldest entry in minute window expires
            oldest_entry = self.minute_window[0]
            next_minute_slot = oldest_entry + timedelta(minutes=1)
        
        if self.daily_count >= self.max_per_day:
            next_day_slot = self.daily_reset_time
        
        return {
            'current_minute_count': len(self.minute_window),
            'max_per_minute': self.max_per_minute,
            'current_daily_count': self.daily_count,
            'max_per_day': self.max_per_day,
            'can_send_now': len(self.minute_window) < self.max_per_minute and self.daily_count < self.max_per_day,
            'next_minute_slot': next_minute_slot.isoformat() if next_minute_slot else None,
            'next_day_slot': next_day_slot.isoformat() if next_day_slot else None,
            'daily_reset_time': self.daily_reset_time.isoformat()
        }
    
    async def wait_for_rate_limit(self) -> float:
        """Wait until rate limit allows sending, return wait time in seconds"""
        wait_time = 0
        
        while not await self.can_send_email():
            current_time = datetime.now()
            
            # Calculate wait time
            if len(self.minute_window) >= self.max_per_minute:
                # Wait until oldest entry in minute window expires
                oldest_entry = self.minute_window[0]
                wait_until = oldest_entry + timedelta(minutes=1)
                wait_seconds = (wait_until - current_time).total_seconds()
                
                if wait_seconds > 0:
                    self.logger.info(f"Rate limit reached, waiting {wait_seconds:.1f} seconds")
                    await asyncio.sleep(min(wait_seconds, 60))  # Cap at 60 seconds
                    wait_time += wait_seconds
            
            elif self.daily_count >= self.max_per_day:
                # Wait until daily reset
                wait_until = self.daily_reset_time
                wait_seconds = (wait_until - current_time).total_seconds()
                
                if wait_seconds > 0:
                    self.logger.info(f"Daily limit reached, waiting until {wait_until}")
                    # For daily waits, we might want to return immediately and let the scheduler handle it
                    return wait_seconds
            
            # Refresh state
            self._cleanup_old_entries(datetime.now())
        
        return wait_time
    
    def _save_state(self):
        """Persist rate limiter state to file"""
        try:
            state = {
                'daily_count': self.daily_count,
                'daily_reset_time': self.daily_reset_time.isoformat(),
                'minute_window': [dt.isoformat() for dt in self.minute_window]
            }
            
            with open(self.persistence_file, 'w') as f:
                json.dump(state, f)
                
        except Exception as e:
            self.logger.error(f"Failed to save rate limiter state: {e}")
    
    def _load_state(self):
        """Load persisted rate limiter state from file"""
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    state = json.load(f)
                
                # Load daily count and reset time
                self.daily_count = state.get('daily_count', 0)
                reset_time_str = state.get('daily_reset_time')
                if reset_time_str:
                    self.daily_reset_time = datetime.fromisoformat(reset_time_str)
                
                # Load minute window
                minute_window_data = state.get('minute_window', [])
                self.minute_window = deque([
                    datetime.fromisoformat(dt_str) 
                    for dt_str in minute_window_data
                ])
                
                # Clean up old data
                self._cleanup_old_entries(datetime.now())
                
                self.logger.info("Rate limiter state loaded from persistence file")
            
        except Exception as e:
            self.logger.error(f"Failed to load rate limiter state: {e}")
            # Reset to clean state
            self.daily_count = 0
            self.minute_window = deque()
    
    def reset_limits(self):
        """Reset all rate limiting counters (for testing/admin purposes)"""
        self.minute_window.clear()
        self.daily_count = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self._save_state()
        self.logger.info("Rate limiting counters reset")


class AdaptiveRateLimiter(RateLimiter):
    """Advanced rate limiter with adaptive behavior based on API responses"""
    
    def __init__(self, config: Config):
        super().__init__(config)
        
        # Adaptive behavior settings
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.current_delay = 1.0  # Base delay between sends in seconds
        self.min_delay = 0.5
        self.max_delay = 30.0
        
        # Exponential backoff settings
        self.backoff_multiplier = 2.0
        self.backoff_max_retries = 3
    
    async def record_send_result(self, success: bool, error_code: str = None):
        """Record the result of an email send attempt"""
        await self.record_email_sent()
        
        if success:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            
            # Gradually reduce delay on consecutive successes
            if self.consecutive_successes >= 5:
                self.current_delay = max(self.min_delay, self.current_delay * 0.9)
                self.consecutive_successes = 0
        
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            
            # Increase delay on failures
            if error_code and "throttl" in error_code.lower():
                # Aggressive backoff for throttling
                self.current_delay = min(self.max_delay, self.current_delay * self.backoff_multiplier)
                self.logger.warning(f"Throttling detected, increased delay to {self.current_delay}s")
            
            elif self.consecutive_failures >= 3:
                # Moderate backoff for other failures
                self.current_delay = min(self.max_delay, self.current_delay * 1.5)
                self.logger.warning(f"Multiple failures detected, increased delay to {self.current_delay}s")
    
    async def wait_before_send(self):
        """Wait appropriate time before sending next email"""
        if self.current_delay > self.min_delay:
            self.logger.debug(f"Adaptive delay: waiting {self.current_delay}s before next send")
            await asyncio.sleep(self.current_delay)
    
    async def exponential_backoff_retry(self, send_function, max_retries: int = None):
        """Execute send function with exponential backoff retry logic"""
        if max_retries is None:
            max_retries = self.backoff_max_retries
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                # Wait for rate limit
                await self.wait_for_rate_limit()
                
                # Execute send function
                result = await send_function()
                
                # Record success
                await self.record_send_result(True)
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Record failure
                error_code = str(e)
                await self.record_send_result(False, error_code)
                
                if attempt < max_retries:
                    # Calculate backoff delay
                    backoff_delay = min(
                        self.max_delay,
                        (self.backoff_multiplier ** attempt) * self.current_delay
                    )
                    
                    self.logger.warning(f"Send attempt {attempt + 1} failed: {e}. Retrying in {backoff_delay}s")
                    await asyncio.sleep(backoff_delay)
                else:
                    self.logger.error(f"All {max_retries + 1} send attempts failed")
        
        # All retries exhausted
        raise last_exception
    
    def get_adaptive_status(self) -> Dict[str, Any]:
        """Get adaptive rate limiter status"""
        base_status = self.get_current_rate()
        
        adaptive_status = {
            'current_delay': self.current_delay,
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'min_delay': self.min_delay,
            'max_delay': self.max_delay
        }
        
        return {**base_status, **adaptive_status}