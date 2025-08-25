"""
Project Template Management System
=================================
This module provides a comprehensive template management system for
creating and managing hydrological modeling project templates.
"""
import os
import json
import shutil
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import zipfile
import tempfile
from pathlib import Path
import logging


class TemplateManager:
    """
    Manages project templates for hydrological modeling.
    """
    
    def __init__(self, templates_dir: str = None):
        """
        Initialize the template manager.
        
        Args:
            templates_dir: Directory to store templates
        """
        self.templates_dir = templates_dir or os.path.expanduser("~/hydrology_templates")
        os.makedirs(self.templates_dir, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Load available templates
        self.templates = self._load_templates()
        
    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load available templates from the templates directory."""
        templates = {}
        
        if os.path.exists(self.templates_dir):
            for template_dir in os.listdir(self.templates_dir):
                template_path = os.path.join(self.templates_dir, template_dir)
                if os.path.isdir(template_path):
                    metadata_file = os.path.join(template_path, "template.json")
                    if os.path.exists(metadata_file):
                        try:
                            with open(metadata_file, 'r') as f:
                                metadata = json.load(f)
                                templates[template_dir] = metadata
                        except Exception as e:
                            self.logger.warning(f"Failed to load template {template_dir}: {e}")
                            
        return templates
        
    def create_template(self, name: str, description: str = "", 
                       category: str = "general") -> str:
        """
        Create a new template.
        
        Args:
            name: Template name
            description: Template description
            category: Template category
            
        Returns:
            Path to the created template
        """
        template_path = os.path.join(self.templates_dir, name)
        os.makedirs(template_path, exist_ok=True)
        
        # Create template metadata
        metadata = {
            'name': name,
            'description': description,
            'category': category,
            'created_date': datetime.now().isoformat(),
            'version': '1.0.0',
            'author': 'User',
            'tags': [],
            'files': [],
            'dependencies': [],
            'configuration': {},
            'examples': []
        }
        
        # Save metadata
        with open(os.path.join(template_path, "template.json"), 'w') as f:
            json.dump(metadata, f, indent=2)
            
        # Create template structure
        os.makedirs(os.path.join(template_path, "files"), exist_ok=True)
        os.makedirs(os.path.join(template_path, "examples"), exist_ok=True)
        
        self.templates[name] = metadata
        self.logger.info(f"Template '{name}' created successfully")
        
        return template_path
        
    def add_file_to_template(self, template_name: str, file_path: str, 
                           content: str, is_template: bool = True) -> bool:
        """
        Add a file to a template.
        
        Args:
            template_name: Name of the template
            file_path: Path where the file should be created
            content: File content
            is_template: Whether the content contains template variables
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        template_path = os.path.join(self.templates_dir, template_name)
        files_dir = os.path.join(template_path, "files")
        
        # Create file
        full_path = os.path.join(files_dir, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(content)
            
        # Update metadata
        file_info = {
            'path': file_path,
            'is_template': is_template,
            'size': len(content),
            'added_date': datetime.now().isoformat()
        }
        
        self.templates[template_name]['files'].append(file_info)
        
        # Save updated metadata
        self._save_template_metadata(template_name)
        
        self.logger.info(f"File '{file_path}' added to template '{template_name}'")
        return True
        
    def add_dependency_to_template(self, template_name: str, package_name: str, 
                                 version: str = None, source: str = "pypi") -> bool:
        """
        Add a dependency to a template.
        
        Args:
            template_name: Name of the template
            package_name: Name of the package
            version: Package version
            source: Package source (pypi, conda, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        dependency = {
            'package': package_name,
            'version': version,
            'source': source,
            'added_date': datetime.now().isoformat()
        }
        
        self.templates[template_name]['dependencies'].append(dependency)
        self._save_template_metadata(template_name)
        
        self.logger.info(f"Dependency '{package_name}' added to template '{template_name}'")
        return True
        
    def add_configuration_to_template(self, template_name: str, key: str, 
                                    value: Any, description: str = "") -> bool:
        """
        Add a configuration parameter to a template.
        
        Args:
            template_name: Name of the template
            key: Configuration key
            value: Configuration value
            description: Configuration description
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        config = {
            'key': key,
            'value': value,
            'description': description,
            'type': type(value).__name__,
            'added_date': datetime.now().isoformat()
        }
        
        self.templates[template_name]['configuration'][key] = config
        self._save_template_metadata(template_name)
        
        self.logger.info(f"Configuration '{key}' added to template '{template_name}'")
        return True
        
    def add_example_to_template(self, template_name: str, example_name: str, 
                              description: str = "") -> bool:
        """
        Add an example to a template.
        
        Args:
            template_name: Name of the template
            example_name: Name of the example
            description: Example description
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        example = {
            'name': example_name,
            'description': description,
            'added_date': datetime.now().isoformat()
        }
        
        self.templates[template_name]['examples'].append(example)
        self._save_template_metadata(template_name)
        
        self.logger.info(f"Example '{example_name}' added to template '{template_name}'")
        return True
        
    def _save_template_metadata(self, template_name: str):
        """Save template metadata to file."""
        template_path = os.path.join(self.templates_dir, template_name)
        metadata_file = os.path.join(template_path, "template.json")
        
        with open(metadata_file, 'w') as f:
            json.dump(self.templates[template_name], f, indent=2)
            
    def instantiate_template(self, template_name: str, project_path: str, 
                           variables: Dict[str, str] = None) -> str:
        """
        Instantiate a template to create a new project.
        
        Args:
            template_name: Name of the template to use
            project_path: Path where the project should be created
            variables: Template variables for substitution
            
        Returns:
            Path to the created project
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
            
        template_path = os.path.join(self.templates_dir, template_name)
        files_dir = os.path.join(template_path, "files")
        
        # Create project directory
        os.makedirs(project_path, exist_ok=True)
        
        variables = variables or {}
        
        # Copy template files
        if os.path.exists(files_dir):
            for root, dirs, files in os.walk(files_dir):
                # Create corresponding directories
                rel_path = os.path.relpath(root, files_dir)
                if rel_path != '.':
                    os.makedirs(os.path.join(project_path, rel_path), exist_ok=True)
                    
                # Copy files
                for file in files:
                    src_file = os.path.join(root, file)
                    rel_file = os.path.relpath(src_file, files_dir)
                    dst_file = os.path.join(project_path, rel_file)
                    
                    # Read file content
                    with open(src_file, 'r') as f:
                        content = f.read()
                        
                    # Substitute template variables
                    for var_name, var_value in variables.items():
                        content = content.replace(f"{{{{{var_name}}}}}", str(var_value))
                        
                    # Write file
                    with open(dst_file, 'w') as f:
                        f.write(content)
                        
        # Create requirements.txt if dependencies exist
        if self.templates[template_name]['dependencies']:
            requirements_path = os.path.join(project_path, "requirements.txt")
            with open(requirements_path, 'w') as f:
                for dep in self.templates[template_name]['dependencies']:
                    if dep['version']:
                        f.write(f"{dep['package']}=={dep['version']}\n")
                    else:
                        f.write(f"{dep['package']}\n")
                        
        # Create project configuration
        config_path = os.path.join(project_path, "project_config.yaml")
        project_config = {
            'name': variables.get('project_name', 'New Project'),
            'created_from_template': template_name,
            'created_date': datetime.now().isoformat(),
            'template_version': self.templates[template_name]['version'],
            'configuration': {}
        }
        
        # Add template configuration
        for key, config in self.templates[template_name]['configuration'].items():
            project_config['configuration'][key] = config['value']
            
        with open(config_path, 'w') as f:
            yaml.dump(project_config, f, default_flow_style=False)
            
        # Create README
        readme_path = os.path.join(project_path, "README.md")
        readme_content = self._generate_readme(template_name, variables)
        with open(readme_path, 'w') as f:
            f.write(readme_content)
            
        self.logger.info(f"Project created from template '{template_name}' at {project_path}")
        return project_path
        
    def _generate_readme(self, template_name: str, variables: Dict[str, str]) -> str:
        """Generate README content for the project."""
        template_info = self.templates[template_name]
        
        readme = f"""# {variables.get('project_name', 'New Project')}

This project was generated from the **{template_name}** template.

## Project Information

- **Template**: {template_name}
- **Description**: {template_info['description']}
- **Category**: {template_info['category']}
- **Version**: {template_info['version']}
- **Created**: {variables.get('project_date', datetime.now().strftime('%Y-%m-%d'))}

## Template Details

{template_info['description']}

## Dependencies

"""
        
        if template_info['dependencies']:
            readme += "The following packages are required:\n\n"
            for dep in template_info['dependencies']:
                version_str = f" ({dep['version']})" if dep['version'] else ""
                readme += f"- {dep['package']}{version_str}\n"
        else:
            readme += "No external dependencies required.\n"
            
        readme += f"""

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure the project by editing `project_config.yaml`

3. Run the simulation or analysis as specified in the template

## Project Structure

"""
        
        if template_info['files']:
            for file_info in template_info['files']:
                readme += f"- `{file_info['path']}` - {file_info['path']}\n"
                
        readme += f"""
- `project_config.yaml` - Project configuration
- `README.md` - This file

## Examples

"""
        
        if template_info['examples']:
            for example in template_info['examples']:
                readme += f"- **{example['name']}**: {example['description']}\n"
        else:
            readme += "No examples provided with this template.\n"
            
        readme += f"""

## Customization

Edit the configuration files and source code to customize the project for your needs.

## Support

For questions about this template, refer to the template documentation or contact the template author.

---

*Generated by Hydro-Suite Template Manager*
"""
        
        return readme
        
    def export_template(self, template_name: str, export_path: str = None) -> str:
        """
        Export a template to a compressed archive.
        
        Args:
            template_name: Name of the template to export
            export_path: Path where the export should be saved
            
        Returns:
            Path to the exported archive
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
            
        if export_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(self.templates_dir, f"{template_name}_{timestamp}.zip")
            
        template_path = os.path.join(self.templates_dir, template_name)
        
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(template_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, template_path)
                    zipf.write(file_path, arcname)
                    
        self.logger.info(f"Template '{template_name}' exported to {export_path}")
        return export_path
        
    def import_template(self, archive_path: str, template_name: str = None) -> str:
        """
        Import a template from a compressed archive.
        
        Args:
            archive_path: Path to the archive file
            template_name: Name for the imported template
            
        Returns:
            Path to the imported template
        """
        if template_name is None:
            template_name = os.path.splitext(os.path.basename(archive_path))[0]
            
        template_path = os.path.join(self.templates_dir, template_name)
        
        # Extract template
        with zipfile.ZipFile(archive_path, 'r') as zipf:
            zipf.extractall(template_path)
            
        # Load and validate template
        metadata_file = os.path.join(template_path, "template.json")
        if not os.path.exists(metadata_file):
            raise ValueError("Invalid template: missing template.json")
            
        # Reload templates
        self.templates = self._load_templates()
        
        self.logger.info(f"Template '{template_name}' imported successfully")
        return template_path
        
    def list_templates(self, category: str = None) -> List[Dict[str, Any]]:
        """
        List available templates.
        
        Args:
            category: Filter by category
            
        Returns:
            List of template information
        """
        template_list = []
        
        for name, metadata in self.templates.items():
            if category is None or metadata.get('category') == category:
                template_info = {
                    'name': name,
                    'description': metadata.get('description', ''),
                    'category': metadata.get('category', 'general'),
                    'version': metadata.get('version', '1.0.0'),
                    'created_date': metadata.get('created_date', ''),
                    'file_count': len(metadata.get('files', [])),
                    'dependency_count': len(metadata.get('dependencies', [])),
                    'example_count': len(metadata.get('examples', []))
                }
                template_list.append(template_info)
                
        return template_list
        
    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a template.
        
        Args:
            template_name: Name of the template
            
        Returns:
            Template information
        """
        if template_name not in self.templates:
            raise ValueError(f"Template '{template_name}' not found")
            
        return self.templates[template_name].copy()
        
    def delete_template(self, template_name: str) -> bool:
        """
        Delete a template.
        
        Args:
            template_name: Name of the template to delete
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        template_path = os.path.join(self.templates_dir, template_name)
        
        try:
            shutil.rmtree(template_path)
            del self.templates[template_name]
            self.logger.info(f"Template '{template_name}' deleted successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete template '{template_name}': {e}")
            return False
            
    def update_template(self, template_name: str, updates: Dict[str, Any]) -> bool:
        """
        Update template metadata.
        
        Args:
            template_name: Name of the template to update
            updates: Dictionary of updates
            
        Returns:
            True if successful, False otherwise
        """
        if template_name not in self.templates:
            self.logger.error(f"Template '{template_name}' not found")
            return False
            
        # Update metadata
        for key, value in updates.items():
            if key in ['name', 'description', 'category', 'version', 'author', 'tags']:
                self.templates[template_name][key] = value
                
        # Save updated metadata
        self._save_template_metadata(template_name)
        
        self.logger.info(f"Template '{template_name}' updated successfully")
        return True


# Predefined template creators
def create_basic_hydrology_template(template_manager: TemplateManager) -> str:
    """Create a basic hydrology modeling template."""
    template_name = "Basic Hydrology Model"
    
    # Create template
    template_path = template_manager.create_template(
        template_name,
        "A basic template for hydrological modeling projects",
        "hydrology"
    )
    
    # Add configuration
    template_manager.add_configuration_to_template(template_name, "time_steps", 1000, "Number of simulation time steps")
    template_manager.add_configuration_to_template(template_name, "dt", 1.0, "Time step size in seconds")
    template_manager.add_configuration_to_template(template_name, "output_format", "csv", "Output file format")
    
    # Add dependencies
    template_manager.add_dependency_to_template(template_name, "numpy")
    template_manager.add_dependency_to_template(template_name, "pandas")
    template_manager.add_dependency_to_template(template_name, "matplotlib")
    template_manager.add_dependency_to_template(template_name, "pyyaml")
    
    # Add main configuration file
    config_content = """# Basic Hydrology Model Configuration
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
    
    template_manager.add_file_to_template(template_name, "config.yaml", config_content)
    
    # Add main script
    script_content = """#!/usr/bin/env python3
\"\"\"
Basic Hydrology Model Simulation
Generated from template: {template_name}
Project: {project_name}
Date: {project_date}
\"\"\"

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from run_from_config import run_simulation

def main():
    \"\"\"Run the basic hydrology simulation.\"\"\"
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
    
    template_manager.add_file_to_template(template_name, "run_simulation.py", script_content)
    
    # Add example
    template_manager.add_example_to_template(template_name, "Simple Catchment", 
                                          "Basic single catchment simulation")
    
    return template_name


def create_advanced_hydrology_template(template_manager: TemplateManager) -> str:
    """Create an advanced hydrology modeling template."""
    template_name = "Advanced Hydrology Model"
    
    # Create template
    template_path = template_manager.create_template(
        template_name,
        "Advanced template with multiple catchments and complex routing",
        "hydrology"
    )
    
    # Add configuration
    template_manager.add_configuration_to_template(template_name, "time_steps", 2000, "Number of simulation time steps")
    template_manager.add_configuration_to_template(template_name, "dt", 0.5, "Time step size in seconds")
    template_manager.add_configuration_to_template(template_name, "parallel_enabled", True, "Enable parallel processing")
    template_manager.add_configuration_to_template(template_name, "max_workers", 4, "Maximum number of parallel workers")
    
    # Add dependencies
    template_manager.add_dependency_to_template(template_name, "numpy")
    template_manager.add_dependency_to_template(template_name, "pandas")
    template_manager.add_dependency_to_template(template_name, "matplotlib")
    template_manager.add_dependency_to_template(template_name, "pyyaml")
    template_manager.add_dependency_to_template(template_name, "psutil")
    
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
    
    template_manager.add_file_to_template(template_name, "config.yaml", config_content)
    
    # Add examples
    template_manager.add_example_to_template(template_name, "Multi-Catchment", 
                                          "Simulation with multiple catchments and routing")
    template_manager.add_example_to_template(template_name, "Parallel Processing", 
                                          "Performance monitoring and parallel execution")
    
    return template_name


def create_2d_hydraulic_template(template_manager: TemplateManager) -> str:
    """Create a 2D hydraulic modeling template."""
    template_name = "2D Hydraulic Model"
    
    # Create template
    template_path = template_manager.create_template(
        template_name,
        "2D hydraulic modeling with unstructured mesh",
        "hydraulic"
    )
    
    # Add configuration
    template_manager.add_configuration_to_template(template_name, "mesh_resolution", 100, "Mesh resolution in meters")
    template_manager.add_configuration_to_template(template_name, "simulation_time", 3600, "Total simulation time in seconds")
    template_manager.add_configuration_to_template(template_name, "output_interval", 60, "Output interval in seconds")
    
    # Add dependencies
    template_manager.add_dependency_to_template(template_name, "numpy")
    template_manager.add_dependency_to_template(template_name, "matplotlib")
    template_manager.add_dependency_to_template(template_name, "scipy")
    template_manager.add_dependency_to_template(template_name, "rasterio")
    
    # Add configuration
    config_content = """# 2D Hydraulic Model Configuration
# Generated from template: {template_name}
# Project: {project_name}
# Date: {project_date}

simulation:
  name: "{project_name}"
  mesh_resolution: {mesh_resolution}
  simulation_time: {simulation_time}
  output_interval: {output_interval}

mesh:
  type: "unstructured"
  resolution: {mesh_resolution}
  boundary_conditions:
    - type: "wall"
      boundary: "north"
    - type: "flow"
      boundary: "south"
      flow_rate: 100.0

physics:
  gravity: 9.81
  manning_coefficient: 0.03
  viscosity: 1e-6

output:
  results_file: "results/2d_results.csv"
  mesh_file: "results/mesh.vtk"
  plots:
    - type: "water_depth"
      output_file: "results/water_depth.png"
    - type: "velocity_field"
      output_file: "results/velocity_field.png"
"""
    
    template_manager.add_file_to_template(template_name, "config.yaml", config_content)
    
    # Add examples
    template_manager.add_example_to_template(template_name, "Flood Simulation", 
                                          "2D flood inundation modeling")
    template_manager.add_example_to_template(template_name, "Channel Flow", 
                                          "Open channel flow simulation")
    
    return template_name


def setup_default_templates(template_manager: TemplateManager):
    """Setup default templates in the template manager."""
    print("Creating default templates...")
    
    # Create basic template
    basic_name = create_basic_hydrology_template(template_manager)
    print(f"✓ Created template: {basic_name}")
    
    # Create advanced template
    advanced_name = create_advanced_hydrology_template(template_manager)
    print(f"✓ Created template: {advanced_name}")
    
    # Create 2D hydraulic template
    hydraulic_name = create_2d_hydraulic_template(template_manager)
    print(f"✓ Created template: {hydraulic_name}")
    
    print("Default templates created successfully!")


def main():
    """Main function to demonstrate template management."""
    try:
        # Create template manager
        template_manager = TemplateManager()
        
        # Setup default templates
        setup_default_templates(template_manager)
        
        # List available templates
        templates = template_manager.list_templates()
        print("\nAvailable templates:")
        for template in templates:
            print(f"  - {template['name']}: {template['description']}")
            print(f"    Category: {template['category']}, Files: {template['file_count']}")
            
        # Create a project from template
        project_path = template_manager.instantiate_template(
            "Basic Hydrology Model",
            "~/test_project",
            {
                'project_name': 'Test Project',
                'project_date': '2024-01-01',
                'time_steps': '500',
                'output_format': 'json'
            }
        )
        
        print(f"\nProject created at: {project_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

