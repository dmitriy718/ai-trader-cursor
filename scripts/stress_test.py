"""72-hour stress test script with auto-restart capabilities."""

import asyncio
import subprocess
import time
import requests
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stress_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StressTest")


class StressTester:
    """72-hour stress tester with container monitoring."""
    
    def __init__(self, duration_hours: int = 72):
        """
        Initialize stress tester.
        
        Args:
            duration_hours: Test duration in hours
        """
        self.duration_hours = duration_hours
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(hours=duration_hours)
        self.container_name = "ai-trading-bot"
        self.api_url = "http://localhost:8000"
        self.restart_count = 0
        self.freeze_count = 0
        self.max_restarts_per_hour = 5
        
    def check_container_health(self) -> bool:
        """Check if container is running and healthy."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={self.container_name}", "--format", "{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                return False
            
            status = result.stdout.strip()
            if not status:
                return False
            
            # Check if container is running
            if "Up" not in status:
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking container health: {e}")
            return False
    
    def check_api_health(self) -> bool:
        """Check if API is responding."""
        try:
            response = requests.get(f"{self.api_url}/api/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"API health check failed: {e}")
            return False
    
    def restart_container(self) -> bool:
        """Restart the container."""
        try:
            logger.warning(f"Restarting container (attempt {self.restart_count + 1})...")
            
            # Stop container
            subprocess.run(
                ["docker", "compose", "stop", "trading-bot"],
                timeout=30,
                check=False
            )
            
            # Wait a bit
            time.sleep(5)
            
            # Start container
            result = subprocess.run(
                ["docker", "compose", "up", "-d", "trading-bot"],
                timeout=30,
                check=False
            )
            
            if result.returncode == 0:
                self.restart_count += 1
                logger.info(f"Container restarted successfully (total restarts: {self.restart_count})")
                
                # Wait for container to be ready
                for _ in range(30):  # Wait up to 30 seconds
                    if self.check_api_health():
                        logger.info("Container is healthy after restart")
                        return True
                    time.sleep(1)
                
                logger.warning("Container restarted but API not responding yet")
                return True
            else:
                logger.error("Failed to restart container")
                return False
        
        except Exception as e:
            logger.error(f"Error restarting container: {e}")
            return False
    
    def detect_freeze(self) -> bool:
        """Detect if the bot has frozen (no API response)."""
        return not self.check_api_health()
    
    def get_stats(self) -> dict:
        """Get bot statistics."""
        try:
            response = requests.get(f"{self.api_url}/api/stats", timeout=5)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.debug(f"Error getting stats: {e}")
            return {}
    
    async def run(self):
        """Run stress test."""
        logger.info(f"Starting {self.duration_hours}-hour stress test")
        logger.info(f"Start time: {self.start_time}")
        logger.info(f"End time: {self.end_time}")
        
        last_health_check = time.time()
        health_check_interval = 30  # Check every 30 seconds
        freeze_timeout = 120  # Consider frozen if no response for 2 minutes
        
        consecutive_failures = 0
        
        while datetime.now() < self.end_time:
            try:
                elapsed = datetime.now() - self.start_time
                remaining = self.end_time - datetime.now()
                
                logger.info(
                    f"Stress test progress: {elapsed} elapsed, "
                    f"{remaining} remaining, "
                    f"Restarts: {self.restart_count}, "
                    f"Freezes detected: {self.freeze_count}"
                )
                
                # Check container health
                if not self.check_container_health():
                    logger.warning("Container is not running, attempting restart...")
                    if not self.restart_container():
                        logger.error("Failed to restart container, waiting before retry...")
                        await asyncio.sleep(60)
                    continue
                
                # Check API health
                if not self.check_api_health():
                    consecutive_failures += 1
                    logger.warning(f"API health check failed (consecutive: {consecutive_failures})")
                    
                    if consecutive_failures * health_check_interval >= freeze_timeout:
                        logger.error("Bot appears to be frozen, restarting...")
                        self.freeze_count += 1
                        self.restart_container()
                        consecutive_failures = 0
                        await asyncio.sleep(30)  # Wait after restart
                    else:
                        await asyncio.sleep(health_check_interval)
                    continue
                
                # Reset failure counter on success
                consecutive_failures = 0
                
                # Get and log stats
                stats = self.get_stats()
                if stats:
                    logger.info(
                        f"Bot stats: Open trades: {stats.get('open_trades', 0)}, "
                        f"Daily PnL: ${stats.get('daily_pnl', 0):.2f}"
                    )
                
                # Check restart rate limit
                hours_elapsed = elapsed.total_seconds() / 3600
                if hours_elapsed > 0:
                    restarts_per_hour = self.restart_count / hours_elapsed
                    if restarts_per_hour > self.max_restarts_per_hour:
                        logger.error(
                            f"Too many restarts: {restarts_per_hour:.2f}/hour "
                            f"(limit: {self.max_restarts_per_hour}/hour)"
                        )
                
                # Wait before next check
                await asyncio.sleep(health_check_interval)
            
            except KeyboardInterrupt:
                logger.info("Stress test interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in stress test loop: {e}")
                await asyncio.sleep(health_check_interval)
        
        # Final report
        total_duration = datetime.now() - self.start_time
        logger.info("=" * 60)
        logger.info("STRESS TEST COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total duration: {total_duration}")
        logger.info(f"Total restarts: {self.restart_count}")
        logger.info(f"Freezes detected: {self.freeze_count}")
        logger.info(f"Average restarts per hour: {self.restart_count / max(total_duration.total_seconds() / 3600, 0.1):.2f}")
        logger.info("=" * 60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="72-hour stress test")
    parser.add_argument(
        "--duration",
        type=int,
        default=72,
        help="Test duration in hours (default: 72)"
    )
    args = parser.parse_args()
    
    tester = StressTester(duration_hours=args.duration)
    
    try:
        asyncio.run(tester.run())
    except KeyboardInterrupt:
        logger.info("Stress test interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
