#!/usr/bin/env python3
"""
Worker Startup Script

This script starts multiple external task workers in parallel.
Each worker runs in its own thread with proper error handling.
"""

import logging
import sys
import threading
import signal
import time
from typing import List

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('worker-supervisor')

# Import workers
from worker_insurance import InsuranceWorker
from worker_risk import RiskWorker


class WorkerSupervisor:
    """
    Supervises multiple worker threads.
    Handles graceful shutdown and worker restart on failure.
    """
    
    def __init__(self):
        self.workers = []
        self.threads: List[threading.Thread] = []
        self.running = True
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.stop()
    
    def add_worker(self, worker_class, name: str):
        """Add a worker to be supervised."""
        worker = worker_class()
        self.workers.append((name, worker))
        logger.info(f"Added worker: {name}")
    
    def _run_worker(self, name: str, worker):
        """Run a worker in a thread with error handling."""
        logger.info(f"Starting worker thread: {name}")
        
        while self.running:
            try:
                worker.run()
            except Exception as e:
                logger.exception(f"Worker {name} crashed: {e}")
                if self.running:
                    logger.info(f"Restarting worker {name} in 5 seconds...")
                    time.sleep(5)
                    # Reset worker state
                    worker.running = True
    
    def start(self):
        """Start all workers in separate threads."""
        logger.info(f"Starting {len(self.workers)} worker(s)...")
        
        for name, worker in self.workers:
            thread = threading.Thread(
                target=self._run_worker,
                args=(name, worker),
                name=f"worker-{name}",
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
            logger.info(f"Worker thread started: {name}")
        
        # Keep main thread alive
        try:
            while self.running:
                # Check thread health
                for thread in self.threads:
                    if not thread.is_alive() and self.running:
                        logger.warning(f"Thread {thread.name} died unexpectedly")
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()
    
    def stop(self):
        """Stop all workers gracefully."""
        logger.info("Stopping all workers...")
        self.running = False
        
        # Signal all workers to stop
        for name, worker in self.workers:
            worker.stop()
            logger.info(f"Stop signal sent to: {name}")
        
        # Wait for threads to finish (with timeout)
        for thread in self.threads:
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning(f"Thread {thread.name} did not stop gracefully")
        
        logger.info("All workers stopped")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Camunda External Task Worker Supervisor")
    logger.info("=" * 60)
    
    supervisor = WorkerSupervisor()
    
    # Add workers
    supervisor.add_worker(InsuranceWorker, "insurance")
    supervisor.add_worker(RiskWorker, "risk")
    
    # Start supervisor (blocks until shutdown)
    supervisor.start()
    
    logger.info("Supervisor shutdown complete")


if __name__ == '__main__':
    main()