"""
Performance and load testing for the email automation system
Tests system behavior under various load conditions
"""

import asyncio
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List
import concurrent.futures

from config import Config
from main import EmailAutomationApp
from db.models import Recipient


class PerformanceTester:
    """Performance testing suite"""
    
    def __init__(self, config: Config):
        self.config = config
        self.app = None
        self.results = []
    
    async def initialize(self):
        """Initialize test environment"""
        self.app = EmailAutomationApp(self.config)
        await self.app.initialize()
    
    async def cleanup(self):
        """Cleanup test environment"""
        if self.app:
            await self.app.cleanup()
    
    async def test_database_performance(self, num_operations: int = 1000) -> Dict[str, Any]:
        """Test database operation performance"""
        print(f"Testing database performance with {num_operations} operations...")
        
        from db.models import RecipientRepository, Recipient
        recipient_repo = RecipientRepository(self.app.db_manager)
        
        # Test data
        test_recipients = []
        for i in range(num_operations):
            test_recipients.append(Recipient(
                first_name=f"Test{i}",
                company=f"Company{i}",
                role=f"Role{i}",
                email=f"test{i}@example.com"
            ))
        
        results = {
            'num_operations': num_operations,
            'create_times': [],
            'read_times': [],
            'update_times': [],
            'total_time': 0
        }
        
        start_total = time.time()
        
        # Test CREATE operations
        print("Testing CREATE operations...")
        create_times = []
        recipient_ids = []
        
        for recipient in test_recipients:
            start_time = time.time()
            recipient_id = await recipient_repo.create(recipient)
            end_time = time.time()
            
            create_times.append((end_time - start_time) * 1000)  # Convert to ms
            recipient_ids.append(recipient_id)
        
        results['create_times'] = create_times
        
        # Test READ operations
        print("Testing READ operations...")
        read_times = []
        
        for recipient_id in recipient_ids[:100]:  # Test first 100
            start_time = time.time()
            await recipient_repo.get_by_id(recipient_id)
            end_time = time.time()
            
            read_times.append((end_time - start_time) * 1000)
        
        results['read_times'] = read_times
        
        # Test UPDATE operations
        print("Testing UPDATE operations...")
        update_times = []
        
        for recipient_id in recipient_ids[:100]:  # Test first 100
            start_time = time.time()
            await recipient_repo.update_status(recipient_id, 'active')
            end_time = time.time()
            
            update_times.append((end_time - start_time) * 1000)
        
        results['update_times'] = update_times
        
        end_total = time.time()
        results['total_time'] = (end_total - start_total) * 1000
        
        # Calculate statistics
        results['create_stats'] = self._calculate_stats(create_times)
        results['read_stats'] = self._calculate_stats(read_times)
        results['update_stats'] = self._calculate_stats(update_times)
        
        return results
    
    async def test_template_rendering_performance(self, num_renders: int = 1000) -> Dict[str, Any]:
        """Test email template rendering performance"""
        print(f"Testing template rendering with {num_renders} renders...")
        
        from email.template_engine import EmailTemplateEngine
        template_engine = EmailTemplateEngine()
        
        # Test recipient
        test_recipient = Recipient(
            first_name="Performance",
            company="Test Company",
            role="Test Role",
            email="performance@test.com"
        )
        
        results = {
            'num_renders': num_renders,
            'render_times': {1: [], 2: [], 3: []},
            'total_time': 0
        }
        
        start_total = time.time()
        
        for step in [1, 2, 3]:
            print(f"Testing template step {step}...")
            step_times = []
            
            for _ in range(num_renders // 3):  # Divide renders among steps
                start_time = time.time()
                template_engine.render_email(step, test_recipient)
                end_time = time.time()
                
                step_times.append((end_time - start_time) * 1000)
            
            results['render_times'][step] = step_times
        
        end_total = time.time()
        results['total_time'] = (end_total - start_total) * 1000
        
        # Calculate statistics for each step
        for step in [1, 2, 3]:
            results[f'step_{step}_stats'] = self._calculate_stats(results['render_times'][step])
        
        return results
    
    async def test_rate_limiter_performance(self, num_checks: int = 10000) -> Dict[str, Any]:
        """Test rate limiter performance"""
        print(f"Testing rate limiter with {num_checks} checks...")
        
        from utils.rate_limiter import RateLimiter
        rate_limiter = RateLimiter(self.config)
        
        results = {
            'num_checks': num_checks,
            'check_times': [],
            'record_times': [],
            'total_time': 0
        }
        
        start_total = time.time()
        
        # Test can_send_email performance
        check_times = []
        for _ in range(num_checks):
            start_time = time.time()
            await rate_limiter.can_send_email()
            end_time = time.time()
            
            check_times.append((end_time - start_time) * 1000)
        
        results['check_times'] = check_times
        
        # Test record_email_sent performance
        record_times = []
        for _ in range(min(num_checks, 100)):  # Limit to avoid hitting actual limits
            start_time = time.time()
            await rate_limiter.record_email_sent()
            end_time = time.time()
            
            record_times.append((end_time - start_time) * 1000)
        
        results['record_times'] = record_times
        
        end_total = time.time()
        results['total_time'] = (end_total - start_total) * 1000
        
        # Calculate statistics
        results['check_stats'] = self._calculate_stats(check_times)
        results['record_stats'] = self._calculate_stats(record_times)
        
        return results
    
    async def test_concurrent_operations(self, num_concurrent: int = 50) -> Dict[str, Any]:
        """Test concurrent operation performance"""
        print(f"Testing concurrent operations with {num_concurrent} concurrent tasks...")
        
        from db.models import RecipientRepository, Recipient
        recipient_repo = RecipientRepository(self.app.db_manager)
        
        async def create_recipient_task(index: int):
            """Task to create a recipient"""
            start_time = time.time()
            
            recipient = Recipient(
                first_name=f"Concurrent{index}",
                company=f"Company{index}",
                role=f"Role{index}",
                email=f"concurrent{index}@example.com"
            )
            
            recipient_id = await recipient_repo.create(recipient)
            
            end_time = time.time()
            return {
                'index': index,
                'recipient_id': recipient_id,
                'duration_ms': (end_time - start_time) * 1000
            }
        
        # Run concurrent tasks
        start_total = time.time()
        
        tasks = [create_recipient_task(i) for i in range(num_concurrent)]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_total = time.time()
        
        # Process results
        successful_tasks = [r for r in task_results if not isinstance(r, Exception)]
        failed_tasks = [r for r in task_results if isinstance(r, Exception)]
        
        durations = [task['duration_ms'] for task in successful_tasks]
        
        results = {
            'num_concurrent': num_concurrent,
            'successful_tasks': len(successful_tasks),
            'failed_tasks': len(failed_tasks),
            'total_time': (end_total - start_total) * 1000,
            'task_durations': durations,
            'duration_stats': self._calculate_stats(durations) if durations else {},
            'throughput_per_second': len(successful_tasks) / ((end_total - start_total) or 1)
        }
        
        return results
    
    async def test_memory_usage(self, num_recipients: int = 10000) -> Dict[str, Any]:
        """Test memory usage with large datasets"""
        print(f"Testing memory usage with {num_recipients} recipients...")
        
        try:
            import psutil
            process = psutil.Process()
        except ImportError:
            return {'error': 'psutil not available for memory testing'}
        
        # Get initial memory usage
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB
        
        from db.models import RecipientRepository, Recipient
        recipient_repo = RecipientRepository(self.app.db_manager)
        
        # Create large number of recipients
        recipients = []
        for i in range(num_recipients):
            recipients.append(Recipient(
                first_name=f"Memory{i}",
                company=f"Company{i}",
                role=f"Role{i}",
                email=f"memory{i}@example.com"
            ))
        
        memory_after_creation = process.memory_info().rss / (1024 * 1024)
        
        # Insert recipients into database
        start_time = time.time()
        
        for recipient in recipients:
            await recipient_repo.create(recipient)
        
        end_time = time.time()
        
        memory_after_insert = process.memory_info().rss / (1024 * 1024)
        
        # Query all recipients
        all_recipients = await recipient_repo.get_all_by_status('pending')
        
        memory_after_query = process.memory_info().rss / (1024 * 1024)
        
        results = {
            'num_recipients': num_recipients,
            'initial_memory_mb': initial_memory,
            'memory_after_creation_mb': memory_after_creation,
            'memory_after_insert_mb': memory_after_insert,
            'memory_after_query_mb': memory_after_query,
            'memory_increase_mb': memory_after_query - initial_memory,
            'insert_time_seconds': end_time - start_time,
            'recipients_queried': len(all_recipients)
        }
        
        return results
    
    def _calculate_stats(self, times: List[float]) -> Dict[str, float]:
        """Calculate statistics for a list of times"""
        if not times:
            return {}
        
        return {
            'min': min(times),
            'max': max(times),
            'mean': statistics.mean(times),
            'median': statistics.median(times),
            'std_dev': statistics.stdev(times) if len(times) > 1 else 0,
            'p95': self._percentile(times, 95),
            'p99': self._percentile(times, 99)
        }
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of data"""
        sorted_data = sorted(data)
        index = (percentile / 100) * (len(sorted_data) - 1)
        
        if index.is_integer():
            return sorted_data[int(index)]
        else:
            lower = sorted_data[int(index)]
            upper = sorted_data[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))
    
    def print_results(self, test_name: str, results: Dict[str, Any]):
        """Print formatted test results"""
        print(f"\n{'='*60}")
        print(f"PERFORMANCE TEST RESULTS: {test_name}")
        print(f"{'='*60}")
        
        if 'error' in results:
            print(f"Error: {results['error']}")
            return
        
        # Print basic metrics
        for key, value in results.items():
            if key.endswith('_stats'):
                stats_name = key.replace('_stats', '').replace('_', ' ').title()
                print(f"\n{stats_name} Statistics:")
                for stat_key, stat_value in value.items():
                    print(f"  {stat_key}: {stat_value:.2f} ms")
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if 'time' in key.lower():
                    if value > 1000:
                        print(f"{key}: {value:.2f} ms ({value/1000:.2f} s)")
                    else:
                        print(f"{key}: {value:.2f} ms")
                else:
                    print(f"{key}: {value}")
            elif isinstance(value, str):
                print(f"{key}: {value}")
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all performance tests"""
        print("Starting comprehensive performance testing...")
        
        all_results = {}
        
        tests = [
            ("Database Performance", self.test_database_performance, 500),
            ("Template Rendering", self.test_template_rendering_performance, 300),
            ("Rate Limiter", self.test_rate_limiter_performance, 1000),
            ("Concurrent Operations", self.test_concurrent_operations, 25),
            ("Memory Usage", self.test_memory_usage, 1000)
        ]
        
        for test_name, test_func, test_size in tests:
            try:
                print(f"\n{'-'*40}")
                print(f"Running: {test_name}")
                print(f"{'-'*40}")
                
                start_time = time.time()
                results = await test_func(test_size)
                end_time = time.time()
                
                results['test_duration_seconds'] = end_time - start_time
                all_results[test_name] = results
                
                self.print_results(test_name, results)
                
            except Exception as e:
                print(f"Test {test_name} failed: {e}")
                all_results[test_name] = {'error': str(e)}
        
        return all_results


async def run_performance_tests():
    """Main function to run performance tests"""
    config = Config()
    tester = PerformanceTester(config)
    
    try:
        await tester.initialize()
        results = await tester.run_all_tests()
        
        # Generate summary
        print(f"\n{'='*60}")
        print("PERFORMANCE TEST SUMMARY")
        print(f"{'='*60}")
        
        for test_name, test_results in results.items():
            if 'error' in test_results:
                print(f"{test_name}: FAILED - {test_results['error']}")
            else:
                duration = test_results.get('test_duration_seconds', 0)
                print(f"{test_name}: COMPLETED in {duration:.2f}s")
        
        return results
        
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Email Automation Performance Tests')
    parser.add_argument('--test', choices=['database', 'template', 'rate', 'concurrent', 'memory'], 
                       help='Run specific test only')
    parser.add_argument('--size', type=int, default=1000, help='Test size (number of operations)')
    
    args = parser.parse_args()
    
    if args.test:
        # Run specific test
        async def run_specific_test():
            config = Config()
            tester = PerformanceTester(config)
            
            try:
                await tester.initialize()
                
                if args.test == 'database':
                    results = await tester.test_database_performance(args.size)
                elif args.test == 'template':
                    results = await tester.test_template_rendering_performance(args.size)
                elif args.test == 'rate':
                    results = await tester.test_rate_limiter_performance(args.size)
                elif args.test == 'concurrent':
                    results = await tester.test_concurrent_operations(args.size)
                elif args.test == 'memory':
                    results = await tester.test_memory_usage(args.size)
                
                tester.print_results(args.test.title(), results)
                
            finally:
                await tester.cleanup()
        
        asyncio.run(run_specific_test())
    else:
        # Run all tests
        asyncio.run(run_performance_tests())