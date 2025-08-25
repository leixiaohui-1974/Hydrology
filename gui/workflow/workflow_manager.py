"""
Workflow Management System for Hydrology Models
==============================================
This module provides workflow management capabilities including project templates,
version control, and batch processing.
"""
import os
import json
import shutil
import git
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import yaml
import pandas as pd
from pathlib import Path
import logging
import threading
import queue
import time


class ProjectTemplate:
    """
    A project template for hydrological modeling workflows.
    """
    
    def __init__(self, name: str, description: str = ""):
        """
        Initialize a project template.
        
        Args:
            name: Template name
            description: Template description
        """
        self.name = name
        self.description = description
        self.files = {}
        self.configuration = {}
        self.dependencies = []
        self.created_date = datetime.now()
        
    def add_file(self, file_path: str, content: str, is_template: bool = True):
        """
        Add a file to the template.
        
        Args:
            file_path: Path where the file should be created
            content: File content (can include template variables)
            is_template: Whether the content contains template variables
        """
        self.files[file_path] = {
            'content': content,
            'is_template': is_template
        }
        
    def add_configuration(self, key: str, value: Any):
        """Add a configuration parameter to the template."""
        self.configuration[key] = value
        
    def add_dependency(self, package_name: str, version: str = None):
        """Add a package dependency to the template."""
        self.dependencies.append({
            'package': package_name,
            'version': version
        })
        
    def save_template(self, template_dir: str):
        """Save the template to a directory."""
        template_path = os.path.join(template_dir, self.name)
        os.makedirs(template_path, exist_ok=True)
        
        # Save template metadata
        metadata = {
            'name': self.name,
            'description': self.description,
            'created_date': self.created_date.isoformat(),
            'configuration': self.configuration,
            'dependencies': self.dependencies
        }
        
        with open(os.path.join(template_path, 'template.json'), 'w') as f:
            json.dump(metadata, f, indent=2)
            
        # Save template files
        for file_path, file_info in self.files.items():
            full_path = os.path.join(template_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, 'w') as f:
                f.write(file_info['content'])
                
    @classmethod
    def load_template(cls, template_path: str) -> 'ProjectTemplate':
        """Load a template from a directory."""
        metadata_file = os.path.join(template_path, 'template.json')
        
        if not os.path.exists(metadata_file):
            raise FileNotFoundError(f"Template metadata not found: {metadata_file}")
            
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
            
        template = cls(metadata['name'], metadata.get('description', ''))
        template.configuration = metadata.get('configuration', {})
        template.dependencies = metadata.get('dependencies', [])
        template.created_date = datetime.fromisoformat(metadata['created_date'])
        
        # Load template files
        for root, dirs, files in os.walk(template_path):
            for file in files:
                if file == 'template.json':
                    continue
                    
                rel_path = os.path.relpath(os.path.join(root, file), template_path)
                with open(os.path.join(root, file), 'r') as f:
                    content = f.read()
                    
                template.add_file(rel_path, content, is_template=True)
                
        return template
        
    def instantiate(self, project_path: str, variables: Dict[str, str]) -> str:
        """
        Instantiate the template to create a new project.
        
        Args:
            project_path: Path where the project should be created
            variables: Dictionary of template variables to substitute
            
        Returns:
            Path to the created project
        """
        project_path = os.path.abspath(project_path)
        os.makedirs(project_path, exist_ok=True)
        
        # Create project files
        for file_path, file_info in self.files.items():
            full_path = os.path.join(project_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            content = file_info['content']
            if file_info['is_template']:
                # Substitute template variables
                for var_name, var_value in variables.items():
                    content = content.replace(f"{{{{{var_name}}}}}", str(var_value))
                    
            with open(full_path, 'w') as f:
                f.write(content)
                
        # Create requirements.txt if dependencies exist
        if self.dependencies:
            requirements_path = os.path.join(project_path, 'requirements.txt')
            with open(requirements_path, 'w') as f:
                for dep in self.dependencies:
                    if dep['version']:
                        f.write(f"{dep['package']}=={dep['version']}\n")
                    else:
                        f.write(f"{dep['package']}\n")
                        
        # Create project configuration
        config_path = os.path.join(project_path, 'project_config.yaml')
        project_config = {
            'name': variables.get('project_name', 'New Project'),
            'created_from_template': self.name,
            'created_date': datetime.now().isoformat(),
            'configuration': self.configuration.copy()
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(project_config, f, default_flow_style=False)
            
        return project_path


class WorkflowManager:
    """
    Manages hydrological modeling workflows and projects.
    """
    
    def __init__(self, workspace_path: str = None):
        """
        Initialize the workflow manager.
        
        Args:
            workspace_path: Path to the workspace directory
        """
        self.workspace_path = workspace_path or os.path.expanduser("~/hydrology_workspace")
        self.templates_path = os.path.join(self.workspace_path, "templates")
        self.projects_path = os.path.join(self.workspace_path, "projects")
        self.batch_jobs_path = os.path.join(self.workspace_path, "batch_jobs")
        
        # Create workspace directories
        for path in [self.workspace_path, self.templates_path, 
                    self.projects_path, self.batch_jobs_path]:
            os.makedirs(path, exist_ok=True)
            
        # Initialize logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(self.workspace_path, 'workflow.log')),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load available templates
        self.templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, ProjectTemplate]:
        """Load available project templates."""
        templates = {}
        
        if os.path.exists(self.templates_path):
            for template_dir in os.listdir(self.templates_path):
                template_path = os.path.join(self.templates_path, template_dir)
                if os.path.isdir(template_path):
                    try:
                        template = ProjectTemplate.load_template(template_path)
                        templates[template.name] = template
                    except Exception as e:
                        self.logger.warning(f"Failed to load template {template_dir}: {e}")
                        
        return templates
        
    def create_template(self, name: str, description: str = "") -> ProjectTemplate:
        """Create a new project template."""
        template = ProjectTemplate(name, description)
        self.templates[name] = template
        return template
        
    def save_template(self, template: ProjectTemplate):
        """Save a template to the templates directory."""
        template.save_template(self.templates_path)
        self.logger.info(f"Template '{template.name}' saved successfully")
        
    def list_templates(self) -> List[Dict[str, Any]]:
        """List available templates with metadata."""
        template_list = []
        for name, template in self.templates.items():
            template_list.append({
                'name': name,
                'description': template.description,
                'created_date': template.created_date,
                'file_count': len(template.files),
                'dependency_count': len(template.dependencies)
            })
        return template_list
        
    def create_project(self, template_name: str, project_name: str, 
                      project_path: str = None, variables: Dict[str, str] = None) -> str:
        """
        Create a new project from a template.
        
        Args:
            template_name: Name of the template to use
            project_name: Name of the new project
            project_path: Path where the project should be created
            variables: Template variables for substitution
            
        Returns:
            Path to the created project
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
            
        template = self.templates[template_name]
        
        if project_path is None:
            project_path = os.path.join(self.projects_path, project_name)
            
        variables = variables or {}
        variables['project_name'] = project_name
        variables['project_date'] = datetime.now().strftime('%Y-%m-%d')
        
        try:
            project_path = template.instantiate(project_path, variables)
            self.logger.info(f"Project '{project_name}' created successfully from template '{template_name}'")
            return project_path
        except Exception as e:
            self.logger.error(f"Failed to create project '{project_name}': {e}")
            raise
            
    def list_projects(self) -> List[Dict[str, Any]]:
        """List available projects with metadata."""
        projects = []
        
        if os.path.exists(self.projects_path):
            for project_dir in os.listdir(self.projects_path):
                project_path = os.path.join(self.projects_path, project_dir)
                if os.path.isdir(project_path):
                    config_file = os.path.join(project_path, 'project_config.yaml')
                    
                    project_info = {
                        'name': project_dir,
                        'path': project_path,
                        'created_date': None,
                        'template': None,
                        'has_git': os.path.exists(os.path.join(project_path, '.git'))
                    }
                    
                    if os.path.exists(config_file):
                        try:
                            with open(config_file, 'r') as f:
                                config = yaml.safe_load(f)
                                project_info.update(config)
                        except Exception as e:
                            self.logger.warning(f"Failed to load config for project {project_dir}: {e}")
                            
                    projects.append(project_info)
                    
        return projects
        
    def initialize_git_repository(self, project_path: str, 
                                initial_commit: bool = True) -> bool:
        """
        Initialize a Git repository for a project.
        
        Args:
            project_path: Path to the project
            initial_commit: Whether to make an initial commit
            
        Returns:
            True if successful, False otherwise
        """
        try:
            repo = git.Repo.init(project_path)
            
            if initial_commit:
                # Add all files
                repo.index.add('*')
                repo.index.commit("Initial commit")
                
            self.logger.info(f"Git repository initialized for project: {project_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Git repository: {e}")
            return False
            
    def create_batch_job(self, name: str, projects: List[str], 
                         commands: List[str], schedule: str = None) -> str:
        """
        Create a batch job for multiple projects.
        
        Args:
            name: Name of the batch job
            projects: List of project paths to process
            commands: List of commands to run for each project
            schedule: Cron-like schedule string (optional)
            
        Returns:
            Path to the batch job configuration
        """
        job_config = {
            'name': name,
            'created_date': datetime.now().isoformat(),
            'projects': projects,
            'commands': commands,
            'schedule': schedule,
            'status': 'pending',
            'last_run': None,
            'next_run': None
        }
        
        job_file = os.path.join(self.batch_jobs_path, f"{name}.json")
        with open(job_file, 'w') as f:
            json.dump(job_config, f, indent=2)
            
        self.logger.info(f"Batch job '{name}' created successfully")
        return job_file
        
    def run_batch_job(self, job_name: str) -> bool:
        """
        Run a batch job.
        
        Args:
            job_name: Name of the batch job to run
            
        Returns:
            True if successful, False otherwise
        """
        job_file = os.path.join(self.batch_jobs_path, f"{job_name}.json")
        
        if not os.path.exists(job_file):
            self.logger.error(f"Batch job '{job_name}' not found")
            return False
            
        try:
            with open(job_file, 'r') as f:
                job_config = json.load(f)
                
            # Update job status
            job_config['status'] = 'running'
            job_config['last_run'] = datetime.now().isoformat()
            
            with open(job_file, 'w') as f:
                json.dump(job_config, f, indent=2)
                
            # Run commands for each project
            for project_path in job_config['projects']:
                if not os.path.exists(project_path):
                    self.logger.warning(f"Project path not found: {project_path}")
                    continue
                    
                self.logger.info(f"Processing project: {project_path}")
                
                # Change to project directory and run commands
                original_dir = os.getcwd()
                try:
                    os.chdir(project_path)
                    
                    for command in job_config['commands']:
                        self.logger.info(f"Running command: {command}")
                        result = os.system(command)
                        
                        if result != 0:
                            self.logger.error(f"Command failed with exit code {result}: {command}")
                            
                finally:
                    os.chdir(original_dir)
                    
            # Update job status
            job_config['status'] = 'completed'
            with open(job_file, 'w') as f:
                json.dump(job_config, f, indent=2)
                
            self.logger.info(f"Batch job '{job_name}' completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to run batch job '{job_name}': {e}")
            
            # Update job status
            job_config['status'] = 'failed'
            with open(job_file, 'w') as f:
                json.dump(job_config, f, indent=2)
                
            return False
            
    def list_batch_jobs(self) -> List[Dict[str, Any]]:
        """List available batch jobs with status."""
        jobs = []
        
        if os.path.exists(self.batch_jobs_path):
            for job_file in os.listdir(self.batch_jobs_path):
                if job_file.endswith('.json'):
                    try:
                        with open(os.path.join(self.batch_jobs_path, job_file), 'r') as f:
                            job_config = json.load(f)
                            job_config['filename'] = job_file
                            jobs.append(job_config)
                    except Exception as e:
                        self.logger.warning(f"Failed to load batch job {job_file}: {e}")
                        
        return jobs
        
    def export_project(self, project_path: str, export_path: str = None) -> str:
        """
        Export a project to a compressed archive.
        
        Args:
            project_path: Path to the project to export
            export_path: Path where the export should be saved
            
        Returns:
            Path to the exported archive
        """
        if export_path is None:
            project_name = os.path.basename(project_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(self.workspace_path, f"{project_name}_{timestamp}.zip")
            
        try:
            shutil.make_archive(
                export_path.replace('.zip', ''),
                'zip',
                project_path
            )
            
            self.logger.info(f"Project exported successfully: {export_path}")
            return export_path
            
        except Exception as e:
            self.logger.error(f"Failed to export project: {e}")
            raise
            
    def import_project(self, archive_path: str, project_name: str = None) -> str:
        """
        Import a project from a compressed archive.
        
        Args:
            archive_path: Path to the archive file
            project_name: Name for the imported project
            
        Returns:
            Path to the imported project
        """
        if project_name is None:
            project_name = os.path.splitext(os.path.basename(archive_path))[0]
            
        import_path = os.path.join(self.projects_path, project_name)
        
        try:
            shutil.unpack_archive(archive_path, import_path, 'zip')
            self.logger.info(f"Project imported successfully: {import_path}")
            return import_path
            
        except Exception as e:
            self.logger.error(f"Failed to import project: {e}")
            raise


# Predefined templates
def create_basic_hydrology_template() -> ProjectTemplate:
    """Create a basic hydrology modeling template."""
    template = ProjectTemplate(
        "Basic Hydrology Model",
        "A basic template for hydrological modeling projects"
    )
    
    # Add configuration
    template.add_configuration("time_steps", 1000)
    template.add_configuration("dt", 1.0)
    template.add_configuration("output_format", "csv")
    
    # Add dependencies
    template.add_dependency("numpy")
    template.add_dependency("pandas")
    template.add_dependency("matplotlib")
    template.add_dependency("pyyaml")
    
    # Add main configuration file
    config_content = """# Hydrology Model Configuration
# Generated from template: {template_name}
# Project: {project_name}
# Date: {project_date}

simulation:
  name: "{project_name}"
  time_steps: {time_steps}
  dt: {dt}
  output_format: "{output_format}"

components:
  - name: "Catchment1"
    type: "HydrologicalModel"
    parameters:
      area: 100.0
      curve_number: 70
      impervious_fraction: 0.1

global_inputs:
  - target_component: "Catchment1"
    inputs:
      rainfall:
        type: "file"
        path: "data/rainfall.csv"
      pet:
        type: "file"
        path: "data/pet.csv"

output:
  results_file: "results/simulation_results.csv"
  plots:
    - type: "hydrograph"
      components: ["Catchment1"]
      output_file: "results/hydrograph.png"
"""
    
    template.add_file("config.yaml", config_content)
    
    # Add main script
    script_content = """#!/usr/bin/env python3
\"\"\"
Hydrology Model Simulation
Generated from template: {template_name}
Project: {project_name}
Date: {project_date}
\"\"\"

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from run_from_config import run_simulation

def main():
    \"\"\"Run the hydrology simulation.\"\"\"
    config_file = "config.yaml"
    
    if not os.path.exists(config_file):
        print(f"Configuration file not found: {config_file}")
        return
        
    print(f"Starting simulation for project: {project_name}")
    results = run_simulation(config_file)
    print("Simulation completed successfully!")
    
if __name__ == "__main__":
    main()
"""
    
    template.add_file("run_simulation.py", script_content)
    
    # Add README
    readme_content = """# {project_name}

This project was generated from the Basic Hydrology Model template.

## Project Information
- **Template**: {template_name}
- **Created**: {project_date}
- **Description**: Basic hydrological modeling project

## Usage

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Prepare input data in the `data/` directory

3. Run simulation:
   ```bash
   python run_simulation.py
   ```

## Project Structure

- `config.yaml` - Main configuration file
- `run_simulation.py` - Main simulation script
- `data/` - Input data directory
- `results/` - Output results directory

## Customization

Edit `config.yaml` to modify model parameters and components.
"""
    
    template.add_file("README.md", readme_content)
    
    # Add directory structure
    template.add_file("data/.gitkeep", "")
    template.add_file("results/.gitkeep", "")
    
    return template


def create_advanced_hydrology_template() -> ProjectTemplate:
    """Create an advanced hydrology modeling template with multiple components."""
    template = ProjectTemplate(
        "Advanced Hydrology Model",
        "Advanced template with multiple catchments and complex routing"
    )
    
    # Add configuration
    template.add_configuration("time_steps", 2000)
    template.add_configuration("dt", 0.5)
    template.add_configuration("parallel_enabled", True)
    template.add_configuration("max_workers", 4)
    
    # Add dependencies
    template.add_dependency("numpy")
    template.add_dependency("pandas")
    template.add_dependency("matplotlib")
    template.add_dependency("pyyaml")
    template.add_dependency("psutil")
    
    # Add advanced configuration
    config_content = """# Advanced Hydrology Model Configuration
# Generated from template: {template_name}
# Project: {project_name}
# Date: {project_date}

simulation:
  name: "{project_name}"
  time_steps: {time_steps}
  dt: {dt}
  parallel:
    enabled: {parallel_enabled}
    max_workers: {max_workers}

components:
  - name: "Catchment1"
    type: "HydrologicalModel"
    parameters:
      area: 150.0
      curve_number: 75
      impervious_fraction: 0.15
      routing:
        type: "Muskingum"
        k: 2.0
        x: 0.2

  - name: "Catchment2"
    type: "HydrologicalModel"
    parameters:
      area: 200.0
      curve_number: 80
      impervious_fraction: 0.2
      routing:
        type: "Muskingum"
        k: 1.5
        x: 0.3

  - name: "Junction1"
    type: "Junction"
    parameters:
      split_ratios: [0.6, 0.4]

connections:
  - from: "Catchment1"
    to: "Junction1"
  - from: "Catchment2"
    to: "Junction1"

global_inputs:
  - target_component: "Catchment1"
    inputs:
      rainfall:
        type: "file"
        path: "data/rainfall_catchment1.csv"
      pet:
        type: "file"
        path: "data/pet_catchment1.csv"

  - target_component: "Catchment2"
    inputs:
      rainfall:
        type: "file"
        path: "data/rainfall_catchment2.csv"
      pet:
        type: "file"
        path: "data/pet_catchment2.csv"

performance_monitoring:
  enabled: true
  metrics:
    - execution_time
    - memory_usage
    - cpu_usage
    - parallelization_speedup

output:
  results_file: "results/simulation_results.csv"
  plots:
    - type: "hydrograph"
      components: ["Catchment1", "Catchment2", "Junction1"]
      output_file: "results/hydrographs.png"
    - type: "performance"
      output_file: "results/performance_analysis.png"
"""
    
    template.add_file("config.yaml", config_content)
    
    # Add main script
    script_content = """#!/usr/bin/env python3
\"\"\"
Advanced Hydrology Model Simulation
Generated from template: {template_name}
Project: {project_name}
Date: {project_date}
\"\"\"

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from run_from_config import run_simulation
from utils.performance_monitor import PerformanceMonitor
from common.parallel_controller import ParallelSimulationController

def main():
    \"\"\"Run the advanced hydrology simulation.\"\"\"
    config_file = "config.yaml"
    
    if not os.path.exists(config_file):
        print(f"Configuration file not found: {config_file}")
        return
        
    print(f"Starting advanced simulation for project: {project_name}")
    
    # Initialize performance monitoring
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    try:
        # Run simulation
        results = run_simulation(config_file)
        
        # Generate performance report
        metrics = monitor.finalize_metrics()
        report = monitor.generate_report("results/performance_report.txt")
        
        print("Advanced simulation completed successfully!")
        print(f"Performance report saved to: results/performance_report.txt")
        
    finally:
        monitor.stop_monitoring()
    
if __name__ == "__main__":
    main()
"""
    
    template.add_file("run_simulation.py", script_content)
    
    # Add README
    readme_content = """# {project_name}

This project was generated from the Advanced Hydrology Model template.

## Project Information
- **Template**: {template_name}
- **Created**: {project_date}
- **Description**: Advanced hydrological modeling project with multiple catchments

## Features

- Multiple catchment modeling
- Complex routing networks
- Parallel computation support
- Performance monitoring
- Advanced visualization

## Usage

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Prepare input data in the `data/` directory:
   - `rainfall_catchment1.csv`
   - `pet_catchment1.csv`
   - `rainfall_catchment2.csv`
   - `pet_catchment2.csv`

3. Run simulation:
   ```bash
   python run_simulation.py
   ```

## Project Structure

- `config.yaml` - Advanced configuration file
- `run_simulation.py` - Main simulation script
- `data/` - Input data directory
- `results/` - Output results directory

## Performance Monitoring

The simulation includes built-in performance monitoring that tracks:
- Execution time
- Memory usage
- CPU usage
- Parallelization speedup

Results are saved to `results/performance_report.txt`.
"""
    
    template.add_file("README.md", readme_content)
    
    # Add directory structure
    template.add_file("data/.gitkeep", "")
    template.add_file("results/.gitkeep", "")
    
    return template


# Utility functions
def setup_default_templates(workflow_manager: WorkflowManager):
    """Setup default templates in the workflow manager."""
    # Create basic template
    basic_template = create_basic_hydrology_template()
    workflow_manager.save_template(basic_template)
    
    # Create advanced template
    advanced_template = create_advanced_hydrology_template()
    workflow_manager.save_template(advanced_template)
    
    print("Default templates created successfully!")


if __name__ == "__main__":
    # Example usage
    workflow_manager = WorkflowManager()
    
    # Setup default templates
    setup_default_templates(workflow_manager)
    
    # List available templates
    templates = workflow_manager.list_templates()
    print("Available templates:")
    for template in templates:
        print(f"  - {template['name']}: {template['description']}")
    
    # Create a new project
    project_path = workflow_manager.create_project(
        "Basic Hydrology Model",
        "My First Project",
        variables={
            'time_steps': '500',
            'output_format': 'json'
        }
    )
    
    print(f"Project created at: {project_path}")
    
    # Initialize Git repository
    workflow_manager.initialize_git_repository(project_path)
    
    # List projects
    projects = workflow_manager.list_projects()
    print("Available projects:")
    for project in projects:
        print(f"  - {project['name']}: {project['path']}")
