"""
Batch Processing System for Hydrology Projects
=============================================
This module provides batch processing capabilities for multiple
hydrological modeling projects with task scheduling and parallel execution.
"""
import os
import json
import yaml
import time
import threading
import queue
import subprocess
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Callable
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import schedule
import psutil


class BatchJob:
    """
    Represents a batch job for processing multiple projects.
    """
    
    def __init__(self, name: str, description: str = ""):
        """
        Initialize a batch job.
        
        Args:
            name: Job name
            description: Job description
        """
        self.name = name
        self.description = description
        self.projects = []
        self.tasks = []
        self.schedule = None
        self.status = "pending"
        self.created_date = datetime.now()
        self.last_run = None
        self.next_run = None
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_execution_time = 0.0
        self.results = []
        
    def add_project(self, project_path: str, project_name: str = None):
        """Add a project to the batch job."""
        if project_name is None:
            project_name = os.path.basename(project_path)
            
        self.projects.append({
            'path': project_path,
            'name': project_name,
            'status': 'pending',
            'last_run': None,
            'execution_count': 0,
            'success_count': 0,
            'failure_count': 0
        })
        
    def add_task(self, task_name: str, command: str, working_dir: str = None, 
                 timeout: int = 300, retry_count: int = 0):
        """Add a task to the batch job."""
        self.tasks.append({
            'name': task_name,
            'command': command,
            'working_dir': working_dir,
            'timeout': timeout,
            'retry_count': retry_count,
            'current_retries': 0
        })
        
    def set_schedule(self, schedule_type: str, **kwargs):
        """
        Set the job schedule.
        
        Args:
            schedule_type: Type of schedule ('daily', 'weekly', 'monthly', 'cron')
            **kwargs: Schedule parameters
        """
        self.schedule = {
            'type': schedule_type,
            'parameters': kwargs
        }
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert batch job to dictionary."""
        return {
            'name': self.name,
            'description': self.description,
            'projects': self.projects,
            'tasks': self.tasks,
            'schedule': self.schedule,
            'status': self.status,
            'created_date': self.created_date.isoformat(),
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'execution_count': self.execution_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'total_execution_time': self.total_execution_time,
            'results': self.results
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BatchJob':
        """Create batch job from dictionary."""
        job = cls(data['name'], data.get('description', ''))
        job.projects = data.get('projects', [])
        job.tasks = data.get('tasks', [])
        job.schedule = data.get('schedule')
        job.status = data.get('status', 'pending')
        job.created_date = datetime.fromisoformat(data['created_date'])
        
        if data.get('last_run'):
            job.last_run = datetime.fromisoformat(data['last_run'])
        if data.get('next_run'):
            job.next_run = datetime.fromisoformat(data['next_run'])
            
        job.execution_count = data.get('execution_count', 0)
        job.success_count = data.get('success_count', 0)
        job.failure_count = data.get('failure_count', 0)
        job.total_execution_time = data.get('total_execution_time', 0.0)
        job.results = data.get('results', [])
        
        return job


class TaskExecutor:
    """
    Executes individual tasks for batch jobs.
    """
    
    def __init__(self, task: Dict[str, Any], project_path: str):
        """
        Initialize task executor.
        
        Args:
            task: Task configuration
            project_path: Path to the project
        """
        self.task = task
        self.project_path = project_path
        self.logger = logging.getLogger(__name__)
        
    def execute(self) -> Dict[str, Any]:
        """
        Execute the task.
        
        Returns:
            Task execution result
        """
        start_time = time.time()
        result = {
            'task_name': self.task['name'],
            'project_path': self.project_path,
            'command': self.task['command'],
            'start_time': datetime.now().isoformat(),
            'status': 'running',
            'output': '',
            'error': '',
            'exit_code': None,
            'execution_time': 0.0
        }
        
        try:
            # Determine working directory
            working_dir = self.task.get('working_dir')
            if working_dir:
                if os.path.isabs(working_dir):
                    work_dir = working_dir
                else:
                    work_dir = os.path.join(self.project_path, working_dir)
            else:
                work_dir = self.project_path
                
            # Execute command
            process = subprocess.Popen(
                self.task['command'],
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = process.communicate(timeout=self.task['timeout'])
                result['exit_code'] = process.returncode
                result['output'] = stdout
                result['error'] = stderr
                
                if process.returncode == 0:
                    result['status'] = 'completed'
                else:
                    result['status'] = 'failed'
                    
            except subprocess.TimeoutExpired:
                process.kill()
                result['status'] = 'timeout'
                result['error'] = 'Task execution timed out'
                
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            self.logger.error(f"Task execution error: {e}")
            
        finally:
            result['execution_time'] = time.time() - start_time
            
        return result


class BatchProcessor:
    """
    Main batch processor for executing batch jobs.
    """
    
    def __init__(self, max_workers: int = None, log_file: str = None):
        """
        Initialize the batch processor.
        
        Args:
            max_workers: Maximum number of parallel workers
            log_file: Log file path
        """
        self.max_workers = max_workers or min(mp.cpu_count(), 8)
        self.jobs: Dict[str, BatchJob] = {}
        self.running_jobs: Dict[str, bool] = {}
        self.job_queue = queue.Queue()
        self.results_queue = queue.Queue()
        
        # Setup logging
        self._setup_logging(log_file)
        
        # Start worker threads
        self.workers = []
        self.stop_workers = False
        self._start_workers()
        
    def _setup_logging(self, log_file: str = None):
        """Setup logging configuration."""
        log_level = logging.INFO
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        handlers = [logging.StreamHandler()]
        if log_file:
            handlers.append(logging.FileHandler(log_file))
            
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=handlers
        )
        
        self.logger = logging.getLogger(__name__)
        
    def _start_workers(self):
        """Start worker threads for processing jobs."""
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            worker.start()
            self.workers.append(worker)
            
        self.logger.info(f"Started {self.max_workers} worker threads")
        
    def _worker_loop(self, worker_id: int):
        """Worker thread main loop."""
        self.logger.debug(f"Worker {worker_id} started")
        
        while not self.stop_workers:
            try:
                # Get job from queue
                job_data = self.job_queue.get(timeout=1)
                if job_data is None:  # Stop signal
                    break
                    
                job_name, project_path = job_data
                self._process_job(job_name, project_path)
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Worker {worker_id} error: {e}")
                
        self.logger.debug(f"Worker {worker_id} stopped")
        
    def _process_job(self, job_name: str, project_path: str):
        """Process a single job for a project."""
        if job_name not in self.jobs:
            return
            
        job = self.jobs[job_name]
        project_info = next((p for p in job.projects if p['path'] == project_path), None)
        
        if not project_info:
            return
            
        # Update project status
        project_info['status'] = 'running'
        project_info['last_run'] = datetime.now()
        project_info['execution_count'] += 1
        
        # Execute tasks
        project_results = []
        project_success = True
        
        for task in job.tasks:
            executor = TaskExecutor(task, project_path)
            result = executor.execute()
            project_results.append(result)
            
            if result['status'] != 'completed':
                project_success = False
                
                # Retry if configured
                if task['retry_count'] > 0 and task['current_retries'] < task['retry_count']:
                    task['current_retries'] += 1
                    self.logger.info(f"Retrying task {task['name']} for project {project_path}")
                    
                    # Wait before retry
                    time.sleep(2)
                    retry_result = executor.execute()
                    project_results.append(retry_result)
                    
                    if retry_result['status'] == 'completed':
                        project_success = True
                        
        # Update project status
        if project_success:
            project_info['status'] = 'completed'
            project_info['success_count'] += 1
        else:
            project_info['status'] = 'failed'
            project_info['failure_count'] += 1
            
        # Add results to job
        job.results.extend(project_results)
        
        # Update job statistics
        job.execution_count += 1
        if project_success:
            job.success_count += 1
        else:
            job.failure_count += 1
            
        # Calculate total execution time
        total_time = sum(r['execution_time'] for r in project_results)
        job.total_execution_time += total_time
        
        # Send results to main thread
        self.results_queue.put({
            'job_name': job_name,
            'project_path': project_path,
            'results': project_results,
            'success': project_success
        })
        
    def add_job(self, job: BatchJob) -> bool:
        """
        Add a batch job to the processor.
        
        Args:
            job: Batch job to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.jobs[job.name] = job
            self.logger.info(f"Added batch job: {job.name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add job {job.name}: {e}")
            return False
            
    def remove_job(self, job_name: str) -> bool:
        """
        Remove a batch job.
        
        Args:
            job_name: Name of the job to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if job_name in self.jobs:
                del self.jobs[job_name]
                self.logger.info(f"Removed batch job: {job_name}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove job {job_name}: {e}")
            return False
            
    def run_job(self, job_name: str, projects: List[str] = None) -> bool:
        """
        Run a batch job.
        
        Args:
            job_name: Name of the job to run
            projects: Specific projects to run (None for all)
            
        Returns:
            True if successful, False otherwise
        """
        if job_name not in self.jobs:
            self.logger.error(f"Job '{job_name}' not found")
            return False
            
        if self.running_jobs.get(job_name, False):
            self.logger.warning(f"Job '{job_name}' is already running")
            return False
            
        try:
            job = self.jobs[job_name]
            job.status = 'running'
            job.last_run = datetime.now()
            self.running_jobs[job_name] = True
            
            # Determine projects to run
            if projects is None:
                projects_to_run = [p['path'] for p in job.projects]
            else:
                projects_to_run = [p for p in projects if p in [proj['path'] for proj in job.projects]]
                
            # Queue projects for processing
            for project_path in projects_to_run:
                self.job_queue.put((job_name, project_path))
                
            self.logger.info(f"Started batch job '{job_name}' with {len(projects_to_run)} projects")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to run job {job_name}: {e}")
            job.status = 'failed'
            self.running_jobs[job_name] = False
            return False
            
    def run_job_sync(self, job_name: str, projects: List[str] = None) -> Dict[str, Any]:
        """
        Run a batch job synchronously and return results.
        
        Args:
            job_name: Name of the job to run
            projects: Specific projects to run (None for all)
            
        Returns:
            Job execution results
        """
        if not self.run_job(job_name, projects):
            return {'error': f'Failed to start job {job_name}'}
            
        # Wait for completion
        job = self.jobs[job_name]
        while job.status == 'running':
            time.sleep(1)
            
        # Collect results
        results = []
        while not self.results_queue.empty():
            try:
                result = self.results_queue.get_nowait()
                results.append(result)
            except queue.Empty:
                break
                
        return {
            'job_name': job_name,
            'status': job.status,
            'results': results,
            'statistics': {
                'total_projects': len(job.projects),
                'execution_count': job.execution_count,
                'success_count': job.success_count,
                'failure_count': job.failure_count,
                'total_execution_time': job.total_execution_time
            }
        }
        
    def get_job_status(self, job_name: str) -> Dict[str, Any]:
        """
        Get the status of a batch job.
        
        Args:
            job_name: Name of the job
            
        Returns:
            Job status information
        """
        if job_name not in self.jobs:
            return {'error': f'Job {job_name} not found'}
            
        job = self.jobs[job_name]
        return {
            'name': job.name,
            'status': job.status,
            'is_running': self.running_jobs.get(job_name, False),
            'projects': job.projects,
            'statistics': {
                'execution_count': job.execution_count,
                'success_count': job.success_count,
                'failure_count': job.failure_count,
                'total_execution_time': job.total_execution_time
            },
            'last_run': job.last_run.isoformat() if job.last_run else None,
            'next_run': job.next_run.isoformat() if job.next_run else None
        }
        
    def list_jobs(self) -> List[Dict[str, Any]]:
        """
        List all batch jobs.
        
        Returns:
            List of job information
        """
        job_list = []
        for job in self.jobs.values():
            job_info = {
                'name': job.name,
                'description': job.description,
                'status': job.status,
                'is_running': self.running_jobs.get(job.name, False),
                'project_count': len(job.projects),
                'task_count': len(job.tasks),
                'created_date': job.created_date.isoformat(),
                'last_run': job.last_run.isoformat() if job.last_run else None,
                'execution_count': job.execution_count
            }
            job_list.append(job_info)
            
        return job_list
        
    def save_job(self, job_name: str, file_path: str) -> bool:
        """
        Save a batch job to file.
        
        Args:
            job_name: Name of the job to save
            file_path: Path to save the job
            
        Returns:
            True if successful, False otherwise
        """
        if job_name not in self.jobs:
            return False
            
        try:
            job = self.jobs[job_name]
            job_data = job.to_dict()
            
            with open(file_path, 'w') as f:
                json.dump(job_data, f, indent=2)
                
            self.logger.info(f"Saved job '{job_name}' to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save job {job_name}: {e}")
            return False
            
    def load_job(self, file_path: str) -> bool:
        """
        Load a batch job from file.
        
        Args:
            file_path: Path to the job file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(file_path, 'r') as f:
                job_data = json.load(f)
                
            job = BatchJob.from_dict(job_data)
            self.add_job(job)
            
            self.logger.info(f"Loaded job '{job.name}' from {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load job from {file_path}: {e}")
            return False
            
    def stop_job(self, job_name: str) -> bool:
        """
        Stop a running batch job.
        
        Args:
            job_name: Name of the job to stop
            
        Returns:
            True if successful, False otherwise
        """
        if job_name not in self.running_jobs or not self.running_jobs[job_name]:
            return False
            
        try:
            job = self.jobs[job_name]
            job.status = 'stopped'
            self.running_jobs[job_name] = False
            
            self.logger.info(f"Stopped batch job: {job_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop job {job_name}: {e}")
            return False
            
    def stop_all_jobs(self):
        """Stop all running batch jobs."""
        for job_name in list(self.running_jobs.keys()):
            self.stop_job(job_name)
            
    def shutdown(self):
        """Shutdown the batch processor."""
        self.logger.info("Shutting down batch processor...")
        
        # Stop all jobs
        self.stop_all_jobs()
        
        # Stop workers
        self.stop_workers = True
        
        # Send stop signals to workers
        for _ in range(len(self.workers)):
            self.job_queue.put(None)
            
        # Wait for workers to finish
        for worker in self.workers:
            worker.join()
            
        self.logger.info("Batch processor shutdown complete")


class ScheduledBatchProcessor(BatchProcessor):
    """
    Batch processor with scheduling capabilities.
    """
    
    def __init__(self, max_workers: int = None, log_file: str = None):
        """Initialize scheduled batch processor."""
        super().__init__(max_workers, log_file)
        self.scheduler = schedule.Scheduler()
        self.scheduler_thread = None
        self.stop_scheduler = False
        
    def start_scheduler(self):
        """Start the scheduler thread."""
        if self.scheduler_thread is None or not self.scheduler_thread.is_alive():
            self.stop_scheduler = False
            self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.scheduler_thread.start()
            self.logger.info("Scheduler started")
            
    def stop_scheduler(self):
        """Stop the scheduler thread."""
        self.stop_scheduler = True
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join()
            self.logger.info("Scheduler stopped")
            
    def _scheduler_loop(self):
        """Main scheduler loop."""
        while not self.stop_scheduler:
            try:
                self.scheduler.run_pending()
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Scheduler error: {e}")
                time.sleep(5)
                
    def schedule_job(self, job_name: str, schedule_type: str, **kwargs):
        """
        Schedule a batch job.
        
        Args:
            job_name: Name of the job to schedule
            schedule_type: Type of schedule
            **kwargs: Schedule parameters
        """
        if job_name not in self.jobs:
            self.logger.error(f"Job '{job_name}' not found")
            return
            
        job = self.jobs[job_name]
        
        # Set up schedule based on type
        if schedule_type == 'daily':
            time_str = kwargs.get('time', '09:00')
            self.scheduler.every().day.at(time_str).do(self.run_job, job_name)
            
        elif schedule_type == 'weekly':
            day = kwargs.get('day', 'monday')
            time_str = kwargs.get('time', '09:00')
            getattr(self.scheduler.every(), day).at(time_str).do(self.run_job, job_name)
            
        elif schedule_type == 'monthly':
            day = kwargs.get('day', 1)
            time_str = kwargs.get('time', '09:00')
            self.scheduler.every().month.at(time_str).do(self.run_job, job_name)
            
        elif schedule_type == 'interval':
            minutes = kwargs.get('minutes', 60)
            self.scheduler.every(minutes).minutes.do(self.run_job, job_name)
            
        else:
            self.logger.error(f"Unsupported schedule type: {schedule_type}")
            return
            
        # Update job schedule
        job.schedule = {
            'type': schedule_type,
            'parameters': kwargs
        }
        
        # Calculate next run
        if schedule_type == 'daily':
            job.next_run = datetime.now().replace(
                hour=int(time_str.split(':')[0]),
                minute=int(time_str.split(':')[1]),
                second=0, microsecond=0
            )
            if job.next_run <= datetime.now():
                job.next_run += timedelta(days=1)
                
        self.logger.info(f"Scheduled job '{job_name}' with {schedule_type} schedule")
        
    def get_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Get information about scheduled jobs."""
        scheduled_jobs = []
        
        for job_name, job in self.jobs.items():
            if job.schedule:
                scheduled_jobs.append({
                    'name': job_name,
                    'schedule': job.schedule,
                    'next_run': job.next_run.isoformat() if job.next_run else None,
                    'status': job.status
                })
                
        return scheduled_jobs


def create_sample_batch_job() -> BatchJob:
    """Create a sample batch job for demonstration."""
    job = BatchJob("Sample Hydrology Analysis", "Process multiple hydrology projects")
    
    # Add sample projects
    job.add_project("~/projects/catchment_1", "Catchment 1")
    job.add_project("~/projects/catchment_2", "Catchment 2")
    job.add_project("~/projects/catchment_3", "Catchment 3")
    
    # Add tasks
    job.add_task("Data Validation", "python validate_data.py", timeout=120)
    job.add_task("Model Simulation", "python run_simulation.py", timeout=600)
    job.add_task("Results Analysis", "python analyze_results.py", timeout=300)
    job.add_task("Generate Reports", "python generate_reports.py", timeout=180)
    
    # Set schedule
    job.set_schedule("daily", time="08:00")
    
    return job


def main():
    """Main function to demonstrate batch processing."""
    try:
        # Create batch processor
        processor = ScheduledBatchProcessor(max_workers=4)
        
        # Create sample job
        sample_job = create_sample_batch_job()
        processor.add_job(sample_job)
        
        # Schedule the job
        processor.schedule_job("Sample Hydrology Analysis", "daily", time="08:00")
        
        # Start scheduler
        processor.start_scheduler()
        
        # List jobs
        jobs = processor.list_jobs()
        print("Available batch jobs:")
        for job in jobs:
            print(f"  - {job['name']}: {job['description']}")
            print(f"    Status: {job['status']}, Projects: {job['project_count']}")
            
        # Run job manually (for testing)
        print("\nRunning sample job...")
        results = processor.run_job_sync("Sample Hydrology Analysis")
        
        print(f"Job completed with status: {results['status']}")
        print(f"Processed {results['statistics']['total_projects']} projects")
        
        # Keep running for a while to see scheduled execution
        print("\nKeeping processor running for 60 seconds...")
        time.sleep(60)
        
        # Shutdown
        processor.shutdown()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

