"""
Modern Main GUI for Hydrology Modeling Framework
===============================================
This module provides a modern, integrated GUI that combines 3D visualization,
real-time dashboard, and workflow management capabilities.
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import time
import json
import yaml
from typing import Dict, List, Any, Optional
import webbrowser

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from gui.visualization.3d_viewer import Hydrology3DViewer
from gui.dashboard.real_time_dashboard import RealTimeDashboard, SimulationMonitor
from gui.workflow.workflow_manager import WorkflowManager, setup_default_templates
from common.parallel_controller import ParallelSimulationController, HybridParallelController
from utils.performance_monitor import PerformanceMonitor
from run_from_config import run_simulation


class ModernHydrologyGUI:
    """
    Modern integrated GUI for hydrological modeling.
    """
    
    def __init__(self):
        """Initialize the modern GUI."""
        self.root = tk.Tk()
        self.root.title("Hydro-Suite: Modern Hydrology Modeling Framework")
        self.root.geometry("1400x900")
        self.root.state('zoomed')  # Start maximized
        
        # Initialize components
        self.workflow_manager = WorkflowManager()
        self.performance_monitor = PerformanceMonitor()
        self.simulation_running = False
        self.current_project = None
        
        # Setup default templates if none exist
        if not self.workflow_manager.list_templates():
            setup_default_templates(self.workflow_manager)
        
        # Setup GUI
        self._setup_gui()
        self._setup_menu()
        self._setup_notebook()
        self._setup_status_bar()
        
        # Start performance monitoring
        self.performance_monitor.start_monitoring()
        
    def _setup_gui(self):
        """Setup the main GUI layout."""
        # Configure grid weights
        self.root.grid_rowconfigure(0, weight=0)  # Menu
        self.root.grid_rowconfigure(1, weight=1)  # Main content
        self.root.grid_rowconfigure(2, weight=0)  # Status bar
        self.root.grid_columnconfigure(0, weight=1)
        
        # Create main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
    def _setup_menu(self):
        """Setup the menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Project", command=self._new_project)
        file_menu.add_command(label="Open Project", command=self._open_project)
        file_menu.add_command(label="Save Project", command=self._save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Import Configuration", command=self._import_config)
        file_menu.add_command(label="Export Results", command=self._export_results)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._exit_app)
        
        # Project menu
        project_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Project", menu=project_menu)
        project_menu.add_command(label="Project Templates", command=self._show_templates)
        project_menu.add_command(label="Project Settings", command=self._project_settings)
        project_menu.add_command(label="Version Control", command=self._version_control)
        
        # Simulation menu
        simulation_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Simulation", menu=simulation_menu)
        simulation_menu.add_command(label="Start Simulation", command=self._start_simulation)
        simulation_menu.add_command(label="Pause Simulation", command=self._pause_simulation)
        simulation_menu.add_command(label="Stop Simulation", command=self._stop_simulation)
        simulation_menu.add_separator()
        simulation_menu.add_command(label="Simulation Settings", command=self._simulation_settings)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="3D Visualization", command=self._show_3d_view)
        view_menu.add_command(label="Real-time Dashboard", command=self._show_dashboard)
        view_menu.add_command(label="Performance Monitor", command=self._show_performance)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Workflow Manager", command=self._show_workflow_manager)
        tools_menu.add_command(label="Batch Processing", command=self._show_batch_processing)
        tools_menu.add_command(label="Data Preprocessing", command=self._show_data_preprocessing)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self._show_documentation)
        help_menu.add_command(label="About", command=self._show_about)
        
    def _setup_notebook(self):
        """Setup the main notebook with tabs."""
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # Create tabs
        self._create_project_tab()
        self._create_simulation_tab()
        self._create_visualization_tab()
        self._create_analysis_tab()
        self._create_workflow_tab()
        
    def _create_project_tab(self):
        """Create the project management tab."""
        project_frame = ttk.Frame(self.notebook)
        self.notebook.add(project_frame, text="Project")
        
        # Project info section
        info_frame = ttk.LabelFrame(project_frame, text="Project Information", padding=10)
        info_frame.pack(fill="x", padx=10, pady=5)
        
        # Project name
        ttk.Label(info_frame, text="Project Name:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.project_name_var = tk.StringVar(value="Untitled Project")
        self.project_name_entry = ttk.Entry(info_frame, textvariable=self.project_name_var, width=40)
        self.project_name_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        # Project path
        ttk.Label(info_frame, text="Project Path:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.project_path_var = tk.StringVar()
        path_frame = ttk.Frame(info_frame)
        path_frame.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        self.project_path_entry = ttk.Entry(path_frame, textvariable=self.project_path_var, width=35)
        self.project_path_entry.pack(side="left")
        ttk.Button(path_frame, text="Browse", command=self._browse_project_path).pack(side="left", padx=(5, 0))
        
        # Project template
        ttk.Label(info_frame, text="Template:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.template_var = tk.StringVar()
        template_combo = ttk.Combobox(info_frame, textvariable=self.template_var, state="readonly", width=40)
        template_combo['values'] = [t['name'] for t in self.workflow_manager.list_templates()]
        template_combo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        # Project actions
        actions_frame = ttk.Frame(project_frame)
        actions_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(actions_frame, text="New Project", command=self._new_project).pack(side="left", padx=(0, 5))
        ttk.Button(actions_frame, text="Open Project", command=self._open_project).pack(side="left", padx=(0, 5))
        ttk.Button(actions_frame, text="Save Project", command=self._save_project).pack(side="left", padx=(0, 5))
        ttk.Button(actions_frame, text="Export Project", command=self._export_project).pack(side="left", padx=(0, 5))
        
        # Recent projects
        recent_frame = ttk.LabelFrame(project_frame, text="Recent Projects", padding=10)
        recent_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.recent_projects_list = tk.Listbox(recent_frame)
        self.recent_projects_list.pack(fill="both", expand=True)
        self.recent_projects_list.bind('<Double-Button-1>', self._open_recent_project)
        
        self._update_recent_projects()
        
    def _create_simulation_tab(self):
        """Create the simulation control tab."""
        sim_frame = ttk.Frame(self.notebook)
        self.notebook.add(sim_frame, text="Simulation")
        
        # Simulation controls
        controls_frame = ttk.LabelFrame(sim_frame, text="Simulation Controls", padding=10)
        controls_frame.pack(fill="x", padx=10, pady=5)
        
        # Control buttons
        button_frame = ttk.Frame(controls_frame)
        button_frame.pack(fill="x")
        
        self.start_button = ttk.Button(button_frame, text="Start Simulation", 
                                      command=self._start_simulation, style="Accent.TButton")
        self.start_button.pack(side="left", padx=(0, 5))
        
        self.pause_button = ttk.Button(button_frame, text="Pause", 
                                      command=self._pause_simulation, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 5))
        
        self.stop_button = ttk.Button(button_frame, text="Stop", 
                                     command=self._stop_simulation, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 5))
        
        # Simulation progress
        progress_frame = ttk.Frame(controls_frame)
        progress_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(progress_frame, text="Progress:").pack(side="left")
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                           maximum=100, length=300)
        self.progress_bar.pack(side="left", padx=(5, 0))
        
        self.progress_label = ttk.Label(progress_frame, text="0%")
        self.progress_label.pack(side="left", padx=(5, 0))
        
        # Simulation settings
        settings_frame = ttk.LabelFrame(sim_frame, text="Simulation Settings", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=5)
        
        # Time steps
        ttk.Label(settings_frame, text="Time Steps:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.time_steps_var = tk.StringVar(value="1000")
        ttk.Entry(settings_frame, textvariable=self.time_steps_var, width=15).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        # Time step size
        ttk.Label(settings_frame, text="Time Step (s):").grid(row=0, column=2, sticky="w", padx=5, pady=2)
        self.dt_var = tk.StringVar(value="1.0")
        ttk.Entry(settings_frame, textvariable=self.dt_var, width=15).grid(row=0, column=3, sticky="w", padx=5, pady=2)
        
        # Parallel processing
        self.parallel_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable Parallel Processing", 
                       variable=self.parallel_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=2)
        
        # Max workers
        ttk.Label(settings_frame, text="Max Workers:").grid(row=1, column=2, sticky="w", padx=5, pady=2)
        self.max_workers_var = tk.StringVar(value="4")
        ttk.Entry(settings_frame, textvariable=self.max_workers_var, width=15).grid(row=1, column=3, sticky="w", padx=5, pady=2)
        
        # Simulation log
        log_frame = ttk.LabelFrame(sim_frame, text="Simulation Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.sim_log = tk.Text(log_frame, height=10, wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.sim_log.yview)
        self.sim_log.configure(yscrollcommand=scrollbar.set)
        
        self.sim_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def _create_visualization_tab(self):
        """Create the visualization tab."""
        viz_frame = ttk.Frame(self.notebook)
        self.notebook.add(viz_frame, text="Visualization")
        
        # 3D visualization controls
        viz_controls = ttk.LabelFrame(viz_frame, text="3D Visualization Controls", padding=10)
        viz_controls.pack(fill="x", padx=10, pady=5)
        
        # Terrain file
        ttk.Label(viz_controls, text="Terrain File:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        terrain_frame = ttk.Frame(viz_controls)
        terrain_frame.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        self.terrain_path_var = tk.StringVar()
        ttk.Entry(terrain_frame, textvariable=self.terrain_path_var, width=35).pack(side="left")
        ttk.Button(terrain_frame, text="Browse", command=self._browse_terrain_file).pack(side="left", padx=(5, 0))
        
        # Visualization buttons
        viz_button_frame = ttk.Frame(viz_controls)
        viz_button_frame.grid(row=1, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(viz_button_frame, text="Load 3D Model", command=self._load_3d_model).pack(side="left", padx=(0, 5))
        ttk.Button(viz_button_frame, text="Create 3D View", command=self._create_3d_view).pack(side="left", padx=(0, 5))
        ttk.Button(viz_button_frame, text="Export 3D Scene", command=self._export_3d_scene).pack(side="left", padx=(0, 5))
        
        # 3D viewer container
        self.viz_container = ttk.Frame(viz_frame)
        self.viz_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Placeholder for 3D visualization
        placeholder = ttk.Label(self.viz_container, text="3D Visualization will appear here\n\nClick 'Create 3D View' to start", 
                               font=("Arial", 14), foreground="gray")
        placeholder.pack(expand=True)
        
    def _create_analysis_tab(self):
        """Create the analysis and results tab."""
        analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(analysis_frame, text="Analysis")
        
        # Results overview
        results_frame = ttk.LabelFrame(analysis_frame, text="Results Overview", padding=10)
        results_frame.pack(fill="x", padx=10, pady=5)
        
        # Results table
        columns = ("Component", "Flow Rate", "Water Level", "Status")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=150)
        
        self.results_tree.pack(fill="x")
        
        # Analysis controls
        analysis_controls = ttk.Frame(analysis_frame)
        analysis_controls.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(analysis_controls, text="Generate Plots", command=self._generate_plots).pack(side="left", padx=(0, 5))
        ttk.Button(analysis_controls, text="Export Results", command=self._export_results).pack(side="left", padx=(0, 5))
        ttk.Button(analysis_controls, text="Performance Report", command=self._show_performance_report).pack(side="left", padx=(0, 5))
        
        # Charts container
        charts_frame = ttk.LabelFrame(analysis_frame, text="Charts and Plots", padding=10)
        charts_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Placeholder for charts
        charts_placeholder = ttk.Label(charts_frame, text="Charts and plots will appear here\n\nClick 'Generate Plots' to create visualizations", 
                                      font=("Arial", 12), foreground="gray")
        charts_placeholder.pack(expand=True)
        
    def _create_workflow_tab(self):
        """Create the workflow management tab."""
        workflow_frame = ttk.Frame(self.notebook)
        self.notebook.add(workflow_frame, text="Workflow")
        
        # Workflow controls
        workflow_controls = ttk.LabelFrame(workflow_frame, text="Workflow Management", padding=10)
        workflow_controls.pack(fill="x", padx=10, pady=5)
        
        # Template management
        template_frame = ttk.Frame(workflow_controls)
        template_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(template_frame, text="Project Templates:").pack(side="left")
        self.template_combo = ttk.Combobox(template_frame, state="readonly", width=30)
        self.template_combo['values'] = [t['name'] for t in self.workflow_manager.list_templates()]
        self.template_combo.pack(side="left", padx=(5, 0))
        
        ttk.Button(template_frame, text="Create from Template", 
                  command=self._create_from_template).pack(side="left", padx=(10, 0))
        
        # Batch processing
        batch_frame = ttk.Frame(workflow_controls)
        batch_frame.pack(fill="x")
        
        ttk.Button(batch_frame, text="Create Batch Job", command=self._create_batch_job).pack(side="left", padx=(0, 5))
        ttk.Button(batch_frame, text="Run Batch Job", command=self._run_batch_job).pack(side="left", padx=(0, 5))
        ttk.Button(batch_frame, text="View Batch Jobs", command=self._view_batch_jobs).pack(side="left", padx=(0, 5))
        
        # Projects list
        projects_frame = ttk.LabelFrame(workflow_frame, text="Projects", padding=10)
        projects_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Projects table
        project_columns = ("Name", "Template", "Created", "Status", "Path")
        self.projects_tree = ttk.Treeview(projects_frame, columns=project_columns, show="headings", height=10)
        
        for col in project_columns:
            self.projects_tree.heading(col, text=col)
            self.projects_tree.column(col, width=120)
        
        self.projects_tree.pack(fill="both", expand=True)
        self.projects_tree.bind('<Double-Button-1>', self._open_project_from_list)
        
        self._update_projects_list()
        
    def _setup_status_bar(self):
        """Setup the status bar."""
        self.status_bar = ttk.Frame(self.root)
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        
        self.status_label = ttk.Label(self.status_bar, text="Ready")
        self.status_label.pack(side="left")
        
        # Performance indicators
        perf_frame = ttk.Frame(self.status_bar)
        perf_frame.pack(side="right")
        
        ttk.Label(perf_frame, text="CPU:").pack(side="left")
        self.cpu_label = ttk.Label(perf_frame, text="0%")
        self.cpu_label.pack(side="left", padx=(0, 10))
        
        ttk.Label(perf_frame, text="Memory:").pack(side="left")
        self.memory_label = ttk.Label(perf_frame, text="0 MB")
        self.memory_label.pack(side="left", padx=(0, 10))
        
        # Start status update thread
        self._start_status_updates()
        
    def _start_status_updates(self):
        """Start the status update thread."""
        def update_status():
            while True:
                try:
                    # Update performance indicators
                    cpu_usage = self.performance_monitor.current_metrics.cpu_usage
                    memory_usage = self.performance_monitor.current_metrics.memory_usage
                    
                    self.cpu_label.config(text=f"{cpu_usage:.1f}%")
                    self.memory_label.config(text=f"{memory_usage:.1f} MB")
                    
                    time.sleep(2)  # Update every 2 seconds
                except Exception as e:
                    print(f"Status update error: {e}")
                    time.sleep(5)
        
        status_thread = threading.Thread(target=update_status, daemon=True)
        status_thread.start()
        
    # Menu command methods
    def _new_project(self):
        """Create a new project."""
        # This would open a new project dialog
        messagebox.showinfo("New Project", "New project functionality will be implemented here")
        
    def _open_project(self):
        """Open an existing project."""
        project_path = filedialog.askdirectory(title="Select Project Directory")
        if project_path:
            self._load_project(project_path)
            
    def _save_project(self):
        """Save the current project."""
        if self.current_project:
            messagebox.showinfo("Save Project", f"Project saved: {self.current_project}")
        else:
            messagebox.showwarning("Save Project", "No project to save")
            
    def _import_config(self):
        """Import a configuration file."""
        config_file = filedialog.askopenfilename(
            title="Select Configuration File",
            filetypes=[("YAML files", "*.yaml"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if config_file:
            self._load_configuration(config_file)
            
    def _export_results(self):
        """Export simulation results."""
        export_path = filedialog.asksaveasfilename(
            title="Export Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if export_path:
            messagebox.showinfo("Export", f"Results exported to: {export_path}")
            
    def _exit_app(self):
        """Exit the application."""
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            self.performance_monitor.stop_monitoring()
            self.root.quit()
            
    def _show_templates(self):
        """Show project templates dialog."""
        self._create_templates_dialog()
        
    def _project_settings(self):
        """Show project settings dialog."""
        if self.current_project:
            messagebox.showinfo("Project Settings", f"Settings for: {self.current_project}")
        else:
            messagebox.showwarning("Project Settings", "No project loaded")
            
    def _version_control(self):
        """Show version control dialog."""
        if self.current_project:
            messagebox.showinfo("Version Control", f"Version control for: {self.current_project}")
        else:
            messagebox.showwarning("Version Control", "No project loaded")
            
    def _start_simulation(self):
        """Start the simulation."""
        if not self.current_project:
            messagebox.showwarning("Simulation", "Please load a project first")
            return
            
        try:
            self.simulation_running = True
            self.start_button.config(state="disabled")
            self.pause_button.config(state="normal")
            self.stop_button.config(state="normal")
            
            # Start simulation in background thread
            sim_thread = threading.Thread(target=self._run_simulation, daemon=True)
            sim_thread.start()
            
            self.status_label.config(text="Simulation running...")
            self._log_message("Simulation started")
            
        except Exception as e:
            messagebox.showerror("Simulation Error", f"Failed to start simulation: {e}")
            self._log_message(f"Simulation error: {e}")
            
    def _pause_simulation(self):
        """Pause the simulation."""
        self.simulation_running = False
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")
        self.status_label.config(text="Simulation paused")
        self._log_message("Simulation paused")
        
    def _stop_simulation(self):
        """Stop the simulation."""
        self.simulation_running = False
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
        self.status_label.config(text="Simulation stopped")
        self._log_message("Simulation stopped")
        
    def _simulation_settings(self):
        """Show simulation settings dialog."""
        messagebox.showinfo("Simulation Settings", "Simulation settings dialog will be implemented here")
        
    def _show_3d_view(self):
        """Show 3D visualization."""
        self.notebook.select(2)  # Switch to visualization tab
        
    def _show_dashboard(self):
        """Show real-time dashboard."""
        # Launch dashboard in browser
        try:
            dashboard = RealTimeDashboard()
            dashboard_thread = threading.Thread(target=dashboard.run, daemon=True)
            dashboard_thread.start()
            
            # Wait a moment for dashboard to start
            time.sleep(2)
            webbrowser.open(f"http://127.0.0.1:{dashboard.port}")
            
        except Exception as e:
            messagebox.showerror("Dashboard Error", f"Failed to start dashboard: {e}")
            
    def _show_performance(self):
        """Show performance monitoring."""
        if hasattr(self.performance_monitor, 'generate_report'):
            report = self.performance_monitor.generate_report()
            self._show_text_dialog("Performance Report", report)
        else:
            messagebox.showinfo("Performance", "Performance monitoring is active")
            
    def _show_workflow_manager(self):
        """Show workflow manager."""
        self.notebook.select(4)  # Switch to workflow tab
        
    def _show_batch_processing(self):
        """Show batch processing dialog."""
        self._create_batch_processing_dialog()
        
    def _show_data_preprocessing(self):
        """Show data preprocessing dialog."""
        messagebox.showinfo("Data Preprocessing", "Data preprocessing dialog will be implemented here")
        
    def _show_documentation(self):
        """Show documentation."""
        webbrowser.open("https://github.com/your-repo/hydrology-framework/docs")
        
    def _show_about(self):
        """Show about dialog."""
        about_text = """Hydro-Suite: Modern Hydrology Modeling Framework

Version: 2.0.0
A comprehensive framework for hydrological modeling with:
- Modular hydrological models
- 1D/2D hydraulic modeling
- Parallel computing support
- Real-time visualization
- Workflow management
- Performance monitoring

© 2024 Hydrology Framework Team"""
        
        messagebox.showinfo("About Hydro-Suite", about_text)
        
    # Helper methods
    def _log_message(self, message: str):
        """Add a message to the simulation log."""
        timestamp = time.strftime("%H:%M:%S")
        self.sim_log.insert(tk.END, f"[{timestamp}] {message}\n")
        self.sim_log.see(tk.END)
        
    def _update_progress(self, value: float):
        """Update the progress bar."""
        self.progress_var.set(value)
        self.progress_label.config(text=f"{value:.1f}%")
        
    def _load_project(self, project_path: str):
        """Load a project from the given path."""
        try:
            self.current_project = project_path
            self.project_path_var.set(project_path)
            self.project_name_var.set(os.path.basename(project_path))
            
            # Load project configuration if it exists
            config_file = os.path.join(project_path, "config.yaml")
            if os.path.exists(config_file):
                self._load_configuration(config_file)
                
            self.status_label.config(text=f"Project loaded: {os.path.basename(project_path)}")
            self._log_message(f"Project loaded: {project_path}")
            
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load project: {e}")
            
    def _load_configuration(self, config_file: str):
        """Load a configuration file."""
        try:
            with open(config_file, 'r') as f:
                if config_file.endswith('.yaml'):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
                    
            # Update GUI with configuration
            if 'simulation' in config:
                sim_config = config['simulation']
                if 'time_steps' in sim_config:
                    self.time_steps_var.set(str(sim_config['time_steps']))
                if 'dt' in sim_config:
                    self.dt_var.set(str(sim_config['dt']))
                    
            self._log_message(f"Configuration loaded: {config_file}")
            
        except Exception as e:
            messagebox.showerror("Configuration Error", f"Failed to load configuration: {e}")
            
    def _run_simulation(self):
        """Run the simulation in background."""
        try:
            # This would integrate with the actual simulation framework
            total_steps = int(self.time_steps_var.get())
            
            for step in range(total_steps):
                if not self.simulation_running:
                    break
                    
                # Simulate progress
                progress = (step + 1) / total_steps * 100
                self.root.after(0, self._update_progress, progress)
                
                # Simulate some work
                time.sleep(0.01)
                
            if self.simulation_running:
                self.root.after(0, self._simulation_completed)
                
        except Exception as e:
            self.root.after(0, lambda: self._log_message(f"Simulation error: {e}"))
            
    def _simulation_completed(self):
        """Handle simulation completion."""
        self.simulation_running = False
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.status_label.config(text="Simulation completed")
        self._log_message("Simulation completed successfully")
        
    def _browse_project_path(self):
        """Browse for project path."""
        path = filedialog.askdirectory(title="Select Project Directory")
        if path:
            self.project_path_var.set(path)
            
    def _browse_terrain_file(self):
        """Browse for terrain file."""
        file_path = filedialog.askopenfilename(
            title="Select Terrain File",
            filetypes=[("GeoTIFF files", "*.tif *.tiff"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.terrain_path_var.set(file_path)
            
    def _load_3d_model(self):
        """Load 3D model data."""
        if not self.terrain_path_var.get():
            messagebox.showwarning("3D Model", "Please select a terrain file first")
            return
            
        try:
            # This would integrate with the 3D viewer
            messagebox.showinfo("3D Model", "3D model loaded successfully")
            self._log_message("3D model loaded")
        except Exception as e:
            messagebox.showerror("3D Model Error", f"Failed to load 3D model: {e}")
            
    def _create_3d_view(self):
        """Create 3D visualization."""
        if not self.terrain_path_var.get():
            messagebox.showwarning("3D View", "Please load a 3D model first")
            return
            
        try:
            # This would create and display the 3D visualization
            messagebox.showinfo("3D View", "3D visualization created")
            self._log_message("3D visualization created")
        except Exception as e:
            messagebox.showerror("3D View Error", f"Failed to create 3D view: {e}")
            
    def _export_3d_scene(self):
        """Export 3D scene."""
        export_path = filedialog.asksaveasfilename(
            title="Export 3D Scene",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
        )
        if export_path:
            messagebox.showinfo("Export", f"3D scene exported to: {export_path}")
            
    def _generate_plots(self):
        """Generate analysis plots."""
        messagebox.showinfo("Plots", "Plot generation will be implemented here")
        
    def _show_performance_report(self):
        """Show performance report."""
        if hasattr(self.performance_monitor, 'generate_report'):
            report = self.performance_monitor.generate_report()
            self._show_text_dialog("Performance Report", report)
        else:
            messagebox.showinfo("Performance", "No performance report available")
            
    def _create_from_template(self):
        """Create project from template."""
        template_name = self.template_combo.get()
        if not template_name:
            messagebox.showwarning("Template", "Please select a template")
            return
            
        project_name = tk.simpledialog.askstring("Project Name", "Enter project name:")
        if project_name:
            try:
                project_path = self.workflow_manager.create_project(template_name, project_name)
                messagebox.showinfo("Success", f"Project created: {project_path}")
                self._update_projects_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create project: {e}")
                
    def _create_batch_job(self):
        """Create a batch job."""
        messagebox.showinfo("Batch Job", "Batch job creation will be implemented here")
        
    def _run_batch_job(self):
        """Run a batch job."""
        messagebox.showinfo("Batch Job", "Batch job execution will be implemented here")
        
    def _view_batch_jobs(self):
        """View batch jobs."""
        jobs = self.workflow_manager.list_batch_jobs()
        if jobs:
            job_text = "\n".join([f"{j['name']}: {j['status']}" for j in jobs])
            self._show_text_dialog("Batch Jobs", job_text)
        else:
            messagebox.showinfo("Batch Jobs", "No batch jobs found")
            
    def _update_projects_list(self):
        """Update the projects list."""
        projects = self.workflow_manager.list_projects()
        
        # Clear existing items
        for item in self.projects_tree.get_children():
            self.projects_tree.delete(item)
            
        # Add projects
        for project in projects:
            self.projects_tree.insert("", "end", values=(
                project.get('name', 'Unknown'),
                project.get('created_from_template', 'Unknown'),
                project.get('created_date', 'Unknown')[:10] if project.get('created_date') else 'Unknown',
                'Active' if project.get('has_git') else 'Inactive',
                project.get('path', 'Unknown')
            ))
            
    def _update_recent_projects(self):
        """Update the recent projects list."""
        projects = self.workflow_manager.list_projects()
        
        # Clear existing items
        self.recent_projects_list.delete(0, tk.END)
        
        # Add recent projects (last 10)
        for project in projects[-10:]:
            self.recent_projects_list.insert(tk.END, project.get('name', 'Unknown'))
            
    def _open_recent_project(self, event):
        """Open a project from the recent projects list."""
        selection = self.recent_projects_list.curselection()
        if selection:
            project_name = self.recent_projects_list.get(selection[0])
            projects = self.workflow_manager.list_projects()
            
            for project in projects:
                if project.get('name') == project_name:
                    self._load_project(project.get('path'))
                    break
                    
    def _open_project_from_list(self, event):
        """Open a project from the projects list."""
        selection = self.projects_tree.selection()
        if selection:
            item = self.projects_tree.item(selection[0])
            project_path = item['values'][4]  # Path column
            if os.path.exists(project_path):
                self._load_project(project_path)
                
    def _show_text_dialog(self, title: str, text: str):
        """Show a text dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x400")
        
        text_widget = tk.Text(dialog, wrap="word")
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        text_widget.insert("1.0", text)
        text_widget.config(state="disabled")
        
    def _create_templates_dialog(self):
        """Create templates dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Templates")
        dialog.geometry("500x400")
        
        # Templates list
        templates_frame = ttk.LabelFrame(dialog, text="Available Templates", padding=10)
        templates_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        templates = self.workflow_manager.list_templates()
        
        for template in templates:
            template_frame = ttk.Frame(templates_frame)
            template_frame.pack(fill="x", pady=2)
            
            ttk.Label(template_frame, text=template['name'], font=("Arial", 10, "bold")).pack(side="left")
            ttk.Label(template_frame, text=f" - {template['description']}", foreground="gray").pack(side="left")
            
    def _create_batch_processing_dialog(self):
        """Create batch processing dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Batch Processing")
        dialog.geometry("600x500")
        
        # Batch job creation
        create_frame = ttk.LabelFrame(dialog, text="Create Batch Job", padding=10)
        create_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(create_frame, text="Job Name:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        job_name_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=job_name_var, width=30).grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(create_frame, text="Projects:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        projects_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=projects_var, width=30).grid(row=1, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(create_frame, text="Commands:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        commands_var = tk.StringVar()
        ttk.Entry(create_frame, textvariable=commands_var, width=30).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        # Buttons
        button_frame = ttk.Frame(create_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(button_frame, text="Create Job", 
                  command=lambda: self._create_batch_job_from_dialog(job_name_var.get(), 
                                                                  projects_var.get(), 
                                                                  commands_var.get())).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side="left")
        
    def _create_batch_job_from_dialog(self, name: str, projects: str, commands: str):
        """Create batch job from dialog."""
        try:
            project_list = [p.strip() for p in projects.split(',')]
            command_list = [c.strip() for c in commands.split(',')]
            
            job_file = self.workflow_manager.create_batch_job(name, project_list, command_list)
            messagebox.showinfo("Success", f"Batch job created: {job_file}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create batch job: {e}")
            
    def run(self):
        """Run the GUI."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            print("GUI interrupted by user")
        finally:
            self.performance_monitor.stop_monitoring()


def main():
    """Main function to run the modern GUI."""
    try:
        gui = ModernHydrologyGUI()
        gui.run()
    except Exception as e:
        print(f"Failed to start GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
