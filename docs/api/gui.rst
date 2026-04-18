gui package
===========

.. automodule:: gui
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
----------

gui.main_window module
----------------------

.. automodule:: gui.main_window
   :members:
   :undoc-members:
   :show-inheritance:

gui.model_config_dialog module
------------------------------

.. automodule:: gui.model_config_dialog
   :members:
   :undoc-members:
   :show-inheritance:

gui.visualization_panel module
------------------------------

.. automodule:: gui.visualization_panel
   :members:
   :undoc-members:
   :show-inheritance:

gui.web package
---------------

.. automodule:: gui.web
   :members:
   :undoc-members:
   :show-inheritance:

Submodules
~~~~~~~~~~

gui.web.app module
^^^^^^^^^^^^^^^^^^

.. automodule:: gui.web.app
   :members:
   :undoc-members:
   :show-inheritance:

gui.web.routes module
^^^^^^^^^^^^^^^^^^^^^

.. automodule:: gui.web.routes
   :members:
   :undoc-members:
   :show-inheritance:

Module Contents
---------------

The gui package provides both desktop and web-based graphical user interfaces for the Hydrology Framework.
It includes comprehensive tools for model configuration, data visualization, simulation control, and results analysis.

Key Features
------------

* **Desktop Application**: Full-featured Qt-based desktop interface
* **Web Interface**: Modern web-based dashboard for remote access
* **Interactive Visualization**: Real-time plotting and 3D visualization
* **Model Configuration**: Intuitive dialogs for setting up simulations
* **Data Management**: Import/export tools and data browsers
* **Simulation Control**: Start, stop, pause, and monitor simulations
* **Results Analysis**: Post-processing tools and report generation
* **Multi-User Support**: User authentication and session management

Key Classes and Functions
-------------------------

MainWindow Class
~~~~~~~~~~~~~~~~

.. autoclass:: gui.main_window.MainWindow
   :members:
   :special-members: __init__

ModelConfigDialog Class
~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: gui.model_config_dialog.ModelConfigDialog
   :members:
   :special-members: __init__

VisualizationPanel Class
~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: gui.visualization_panel.VisualizationPanel
   :members:
   :special-members: __init__

WebApp Class
~~~~~~~~~~~~

.. autoclass:: gui.web.app.WebApp
   :members:
   :special-members: __init__

Usage Examples
--------------

Desktop Application
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from gui.main_window import MainWindow
   from PyQt5.QtWidgets import QApplication
   import sys
   
   # Create Qt application
   app = QApplication(sys.argv)
   
   # Create main window
   main_window = MainWindow()
   
   # Configure application settings
   main_window.set_application_settings({
       'theme': 'dark',
       'auto_save': True,
       'auto_save_interval': 300,  # 5 minutes
       'default_project_path': 'C:/HydrologyProjects',
       'max_recent_files': 10
   })
   
   # Set up project workspace
   main_window.create_new_project(
       name="River Basin Analysis",
       description="Comprehensive analysis of the XYZ river basin",
       location="C:/HydrologyProjects/RiverBasin"
   )
   
   # Load data files
   data_files = {
       'streamflow': 'data/streamflow_daily.csv',
       'rainfall': 'data/rainfall_hourly.csv',
       'elevation': 'data/dem_10m.tif',
       'land_use': 'data/landuse.shp'
   }
   
   for data_type, file_path in data_files.items():
       main_window.load_data_file(data_type, file_path)
   
   # Configure model
   model_config = {
       'model_type': '1d_hydraulic',
       'time_step': 60,  # seconds
       'simulation_duration': 86400,  # 24 hours
       'output_interval': 300,  # 5 minutes
       'boundary_conditions': {
           'upstream': 'flow_hydrograph',
           'downstream': 'normal_depth'
       }
   }
   
   main_window.configure_model(model_config)
   
   # Set up visualization
   main_window.setup_visualization({
       'real_time_plots': ['water_level', 'flow_rate'],
       'update_interval': 1000,  # 1 second
       'plot_style': 'scientific',
       'color_scheme': 'viridis'
   })
   
   # Show main window
   main_window.show()
   
   # Start application event loop
   sys.exit(app.exec_())

Model Configuration Dialog
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from gui.model_config_dialog import ModelConfigDialog
   from PyQt5.QtWidgets import QApplication, QMainWindow
   import sys
   
   class MainApp(QMainWindow):
       def __init__(self):
           super().__init__()
           self.init_ui()
       
       def init_ui(self):
           self.setWindowTitle('Hydrology Framework')
           self.setGeometry(100, 100, 1200, 800)
           
           # Create menu bar
           menubar = self.menuBar()
           
           # Model menu
           model_menu = menubar.addMenu('Model')
           
           # Configure action
           configure_action = model_menu.addAction('Configure Model')
           configure_action.triggered.connect(self.open_model_config)
       
       def open_model_config(self):
           # Create model configuration dialog
           config_dialog = ModelConfigDialog(parent=self)
           
           # Set available model types
           config_dialog.set_model_types([
               '1D Hydraulic (Preissmann)',
               '2D Shallow Water',
               'Deep Learning (LSTM)',
               'Deep Learning (GNN)',
               'Hybrid (1D-2D Coupled)'
           ])
           
           # Set default configuration
           default_config = {
               'model_type': '1D Hydraulic (Preissmann)',
               'geometry': {
                   'channel_file': '',
                   'cross_sections': '',
                   'roughness_file': ''
               },
               'boundary_conditions': {
                   'upstream_type': 'flow',
                   'upstream_file': '',
                   'downstream_type': 'normal_depth',
                   'downstream_slope': 0.001
               },
               'numerical_parameters': {
                   'time_step': 60,
                   'theta': 0.6,
                   'max_iterations': 20,
                   'convergence_tolerance': 1e-6
               },
               'output_settings': {
                   'output_interval': 300,
                   'save_format': 'csv',
                   'variables': ['water_level', 'flow_rate', 'velocity']
               }
           }
           
           config_dialog.load_configuration(default_config)
           
           # Show dialog and get result
           if config_dialog.exec_() == config_dialog.Accepted:
               # Get configuration from dialog
               model_config = config_dialog.get_configuration()
               
               # Validate configuration
               validation_result = config_dialog.validate_configuration(model_config)
               
               if validation_result['valid']:
                   print("Model configuration is valid")
                   print(f"Configuration: {model_config}")
                   
                   # Apply configuration
                   self.apply_model_configuration(model_config)
               else:
                   print(f"Configuration errors: {validation_result['errors']}")
       
       def apply_model_configuration(self, config):
           """Apply the model configuration."""
           print(f"Applying configuration: {config['model_type']}")
           
           # Create appropriate model based on configuration
           if config['model_type'] == '1D Hydraulic (Preissmann)':
               self.create_1d_hydraulic_model(config)
           elif config['model_type'] == '2D Shallow Water':
               self.create_2d_model(config)
           elif 'Deep Learning' in config['model_type']:
               self.create_dl_model(config)
           
           print("Model configuration applied successfully")
       
       def create_1d_hydraulic_model(self, config):
           """Create 1D hydraulic model."""
           from preissmann_model.model import HydraulicModel
           
           # Load geometry
           geometry_file = config['geometry']['channel_file']
           
           # Create model
           self.hydraulic_model = HydraulicModel(
               name="configured_model",
               geometry_file=geometry_file,
               dt=config['numerical_parameters']['time_step']
           )
           
           print("1D Hydraulic model created")
       
       def create_2d_model(self, config):
           """Create 2D model."""
           from model_2d.model import Model2D
           
           # Create 2D model
           self.model_2d = Model2D(
               name="configured_2d_model",
               mesh_file=config['geometry']['mesh_file']
           )
           
           print("2D model created")
       
       def create_dl_model(self, config):
           """Create deep learning model."""
           if 'LSTM' in config['model_type']:
               from dl_model.lstm_model import LSTMModel
               
               self.dl_model = LSTMModel(
                   input_size=config['dl_parameters']['input_size'],
                   hidden_size=config['dl_parameters']['hidden_size'],
                   num_layers=config['dl_parameters']['num_layers'],
                   output_size=config['dl_parameters']['output_size']
               )
           elif 'GNN' in config['model_type']:
               from dl_model.gnn_model import GNNModel
               
               self.dl_model = GNNModel(
                   model_path=config['dl_parameters']['model_path'],
                   catchment_def_path=config['dl_parameters']['catchment_def_path']
               )
           
           print("Deep learning model created")
   
   # Run application
   if __name__ == '__main__':
       app = QApplication(sys.argv)
       main_app = MainApp()
       main_app.show()
       sys.exit(app.exec_())

Visualization Panel
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from gui.visualization_panel import VisualizationPanel
   from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
   import numpy as np
   import pandas as pd
   import sys
   
   class VisualizationApp(QMainWindow):
       def __init__(self):
           super().__init__()
           self.init_ui()
           self.setup_data()
       
       def init_ui(self):
           self.setWindowTitle('Hydrology Visualization')
           self.setGeometry(100, 100, 1400, 900)
           
           # Create central widget
           central_widget = QWidget()
           self.setCentralWidget(central_widget)
           
           # Create layout
           layout = QVBoxLayout(central_widget)
           
           # Create visualization panel
           self.viz_panel = VisualizationPanel(parent=self)
           layout.addWidget(self.viz_panel)
           
           # Configure visualization panel
           self.viz_panel.set_plot_style({
               'theme': 'dark',
               'grid': True,
               'legend': True,
               'toolbar': True
           })
       
       def setup_data(self):
           """Generate sample data for visualization."""
           # Time series data
           dates = pd.date_range('2023-01-01', periods=365, freq='D')
           
           # Synthetic streamflow data
           base_flow = 10 + 5 * np.sin(2 * np.pi * np.arange(365) / 365)
           noise = np.random.normal(0, 1, 365)
           
           # Add some flood events
           flood_events = [50, 120, 200, 280]
           for event_day in flood_events:
               if event_day < 365:
                   flood_magnitude = np.random.uniform(20, 50)
                   flood_duration = np.random.randint(3, 8)
                   
                   for i in range(flood_duration):
                       if event_day + i < 365:
                           base_flow[event_day + i] += flood_magnitude * np.exp(-i/2)
           
           streamflow = base_flow + noise
           streamflow[streamflow < 0] = 0.1  # Ensure positive flows
           
           # Create DataFrame
           self.time_series_data = pd.DataFrame({
               'date': dates,
               'streamflow': streamflow,
               'rainfall': np.random.exponential(2, 365),
               'temperature': 15 + 10 * np.sin(2 * np.pi * np.arange(365) / 365) + np.random.normal(0, 2, 365)
           })
           
           # Spatial data (cross-section)
           self.cross_section_data = {
               'distance': np.linspace(0, 100, 50),
               'elevation': 10 - 0.5 * (np.linspace(0, 100, 50) - 50)**2 / 500 + np.random.normal(0, 0.1, 50),
               'water_level': np.full(50, 8.5)
           }
           
           # 2D spatial data (flood map)
           x = np.linspace(0, 1000, 100)
           y = np.linspace(0, 500, 50)
           X, Y = np.meshgrid(x, y)
           
           # Create synthetic flood depths
           river_center = 250  # River at y=250
           distance_from_river = np.abs(Y - river_center)
           
           flood_depths = np.maximum(0, 3 - distance_from_river/50 + 
                                   0.5*np.sin(X/100) + 0.2*np.random.randn(50, 100))
           
           self.flood_map_data = {
               'x': x,
               'y': y,
               'depths': flood_depths
           }
           
           # Load data into visualization panel
           self.load_visualizations()
       
       def load_visualizations(self):
           """Load data into visualization panel."""
           
           # Time series plot
           self.viz_panel.add_time_series_plot(
               data=self.time_series_data,
               x_column='date',
               y_columns=['streamflow', 'rainfall'],
               plot_title='Streamflow and Rainfall Time Series',
               y_labels=['Flow (m³/s)', 'Rainfall (mm)'],
               colors=['blue', 'green']
           )
           
           # Cross-section plot
           self.viz_panel.add_cross_section_plot(
               distance=self.cross_section_data['distance'],
               elevation=self.cross_section_data['elevation'],
               water_level=self.cross_section_data['water_level'],
               plot_title='River Cross-Section',
               fill_water=True
           )
           
           # 2D flood map
           self.viz_panel.add_contour_plot(
               x=self.flood_map_data['x'],
               y=self.flood_map_data['y'],
               z=self.flood_map_data['depths'],
               plot_title='Flood Depth Map',
               colorbar_label='Depth (m)',
               colormap='Blues'
           )
           
           # Statistical plots
           self.viz_panel.add_histogram(
               data=self.time_series_data['streamflow'],
               bins=30,
               plot_title='Streamflow Distribution',
               x_label='Flow (m³/s)',
               y_label='Frequency'
           )
           
           # Flow duration curve
           sorted_flows = np.sort(self.time_series_data['streamflow'])[::-1]
           exceedance_prob = np.arange(1, len(sorted_flows) + 1) / len(sorted_flows) * 100
           
           self.viz_panel.add_log_plot(
               x=exceedance_prob,
               y=sorted_flows,
               plot_title='Flow Duration Curve',
               x_label='Exceedance Probability (%)',
               y_label='Flow (m³/s)'
           )
           
           # Correlation matrix
           correlation_data = self.time_series_data[['streamflow', 'rainfall', 'temperature']].corr()
           
           self.viz_panel.add_heatmap(
               data=correlation_data.values,
               x_labels=correlation_data.columns,
               y_labels=correlation_data.index,
               plot_title='Variable Correlation Matrix',
               colormap='RdBu_r',
               center_colormap=True
           )
           
           # 3D surface plot
           self.viz_panel.add_3d_surface(
               x=self.flood_map_data['x'],
               y=self.flood_map_data['y'],
               z=self.flood_map_data['depths'],
               plot_title='3D Flood Surface',
               colormap='viridis'
           )
           
           # Animation setup
           self.setup_animation()
       
       def setup_animation(self):
           """Setup animated plots."""
           # Create time-varying data for animation
           time_steps = 100
           animation_data = []
           
           for t in range(time_steps):
               # Simulate flood wave propagation
               wave_position = t * 10  # Wave moves 10 units per time step
               
               depths = np.zeros_like(self.flood_map_data['depths'])
               
               # Create moving flood wave
               for i, x_val in enumerate(self.flood_map_data['x']):
                   if abs(x_val - wave_position) < 50:  # Wave width
                       wave_height = 2 * np.exp(-((x_val - wave_position)/20)**2)
                       depths[:, i] = wave_height
               
               animation_data.append(depths)
           
           # Add animated plot
           self.viz_panel.add_animated_contour(
               x=self.flood_map_data['x'],
               y=self.flood_map_data['y'],
               z_frames=animation_data,
               plot_title='Flood Wave Propagation',
               colorbar_label='Depth (m)',
               frame_interval=100  # 100ms between frames
           )
   
   # Run application
   if __name__ == '__main__':
       app = QApplication(sys.argv)
       viz_app = VisualizationApp()
       viz_app.show()
       sys.exit(app.exec_())

Web Interface
~~~~~~~~~~~~~

.. code-block:: python

   from gui.web.app import WebApp
   from flask import Flask, render_template, request, jsonify
   import json
   import pandas as pd
   import numpy as np
   
   # Create web application
   web_app = WebApp(
       name='Hydrology Framework Web Interface',
       debug=True,
       host='0.0.0.0',
       port=5000
   )
   
   # Configure authentication
   web_app.setup_authentication({
       'method': 'database',
       'database_url': 'sqlite:///users.db',
       'session_timeout': 3600,  # 1 hour
       'password_requirements': {
           'min_length': 8,
           'require_uppercase': True,
           'require_numbers': True,
           'require_special': True
       }
   })
   
   # Setup database for projects and results
   web_app.setup_database({
       'url': 'sqlite:///hydrology_projects.db',
       'tables': ['projects', 'simulations', 'results', 'users']
   })
   
   # Configure file upload
   web_app.setup_file_upload({
       'upload_folder': 'uploads/',
       'max_file_size': 100 * 1024 * 1024,  # 100 MB
       'allowed_extensions': ['.csv', '.txt', '.shp', '.tif', '.nc']
   })
   
   # Add custom routes
   @web_app.route('/api/projects', methods=['GET', 'POST'])
   def handle_projects():
       """Handle project management."""
       if request.method == 'GET':
           # Get all projects for current user
           projects = web_app.get_user_projects()
           return jsonify(projects)
       
       elif request.method == 'POST':
           # Create new project
           project_data = request.get_json()
           
           # Validate project data
           required_fields = ['name', 'description', 'model_type']
           if not all(field in project_data for field in required_fields):
               return jsonify({'error': 'Missing required fields'}), 400
           
           # Create project
           project_id = web_app.create_project(project_data)
           
           return jsonify({
               'message': 'Project created successfully',
               'project_id': project_id
           })
   
   @web_app.route('/api/simulations/<int:project_id>', methods=['GET', 'POST'])
   def handle_simulations(project_id):
       """Handle simulation management."""
       if request.method == 'GET':
           # Get simulations for project
           simulations = web_app.get_project_simulations(project_id)
           return jsonify(simulations)
       
       elif request.method == 'POST':
           # Start new simulation
           sim_config = request.get_json()
           
           # Validate simulation configuration
           validation_result = web_app.validate_simulation_config(sim_config)
           if not validation_result['valid']:
               return jsonify({
                   'error': 'Invalid configuration',
                   'details': validation_result['errors']
               }), 400
           
           # Start simulation
           simulation_id = web_app.start_simulation(project_id, sim_config)
           
           return jsonify({
               'message': 'Simulation started',
               'simulation_id': simulation_id
           })
   
   @web_app.route('/api/simulation_status/<int:simulation_id>')
   def get_simulation_status(simulation_id):
       """Get simulation status and progress."""
       status = web_app.get_simulation_status(simulation_id)
       return jsonify(status)
   
   @web_app.route('/api/results/<int:simulation_id>')
   def get_simulation_results(simulation_id):
       """Get simulation results."""
       results = web_app.get_simulation_results(simulation_id)
       
       if results is None:
           return jsonify({'error': 'Results not found'}), 404
       
       return jsonify(results)
   
   @web_app.route('/api/visualization/<int:simulation_id>')
   def get_visualization_data(simulation_id):
       """Get data for visualization."""
       viz_type = request.args.get('type', 'time_series')
       
       if viz_type == 'time_series':
           data = web_app.get_time_series_data(simulation_id)
       elif viz_type == 'spatial':
           data = web_app.get_spatial_data(simulation_id)
       elif viz_type == 'cross_section':
           data = web_app.get_cross_section_data(simulation_id)
       else:
           return jsonify({'error': 'Invalid visualization type'}), 400
       
       return jsonify(data)
   
   @web_app.route('/upload_data', methods=['POST'])
   def upload_data():
       """Handle data file uploads."""
       if 'file' not in request.files:
           return jsonify({'error': 'No file provided'}), 400
       
       file = request.files['file']
       data_type = request.form.get('data_type')
       
       if file.filename == '':
           return jsonify({'error': 'No file selected'}), 400
       
       # Validate file
       if not web_app.validate_uploaded_file(file):
           return jsonify({'error': 'Invalid file type or size'}), 400
       
       # Save file
       file_path = web_app.save_uploaded_file(file, data_type)
       
       # Process file based on type
       if data_type == 'streamflow':
           processed_data = web_app.process_streamflow_data(file_path)
       elif data_type == 'rainfall':
           processed_data = web_app.process_rainfall_data(file_path)
       elif data_type == 'elevation':
           processed_data = web_app.process_elevation_data(file_path)
       else:
           processed_data = web_app.process_generic_data(file_path)
       
       return jsonify({
           'message': 'File uploaded and processed successfully',
           'file_path': file_path,
           'data_summary': processed_data['summary']
       })
   
   # Add WebSocket support for real-time updates
   @web_app.websocket('/ws/simulation_updates')
   def handle_simulation_updates(ws):
       """Handle real-time simulation updates via WebSocket."""
       while True:
           # Get simulation updates
           updates = web_app.get_pending_updates()
           
           for update in updates:
               ws.send(json.dumps(update))
           
           # Wait before next update
           web_app.sleep(1)
   
   # Custom dashboard route
   @web_app.route('/dashboard')
   def dashboard():
       """Main dashboard page."""
       # Get user's recent projects
       recent_projects = web_app.get_recent_projects(limit=5)
       
       # Get system status
       system_status = web_app.get_system_status()
       
       # Get running simulations
       running_simulations = web_app.get_running_simulations()
       
       return render_template('dashboard.html', 
                            recent_projects=recent_projects,
                            system_status=system_status,
                            running_simulations=running_simulations)
   
   # Model configuration page
   @web_app.route('/configure_model/<int:project_id>')
   def configure_model(project_id):
       """Model configuration page."""
       project = web_app.get_project(project_id)
       
       if not project:
           return "Project not found", 404
       
       # Get available model types
       model_types = web_app.get_available_model_types()
       
       # Get default configurations
       default_configs = web_app.get_default_configurations()
       
       return render_template('configure_model.html',
                            project=project,
                            model_types=model_types,
                            default_configs=default_configs)
   
   # Results visualization page
   @web_app.route('/results/<int:simulation_id>')
   def view_results(simulation_id):
       """Results visualization page."""
       simulation = web_app.get_simulation(simulation_id)
       
       if not simulation:
           return "Simulation not found", 404
       
       # Check if results are available
       if simulation['status'] != 'completed':
           return render_template('simulation_running.html', simulation=simulation)
       
       # Get results summary
       results_summary = web_app.get_results_summary(simulation_id)
       
       # Get available visualization types
       viz_types = web_app.get_available_visualizations(simulation_id)
       
       return render_template('results.html',
                            simulation=simulation,
                            results_summary=results_summary,
                            viz_types=viz_types)
   
   # API documentation
   @web_app.route('/api/docs')
   def api_documentation():
       """API documentation page."""
       api_endpoints = web_app.get_api_documentation()
       return render_template('api_docs.html', endpoints=api_endpoints)
   
   # Start the web application
   if __name__ == '__main__':
       # Initialize database
       web_app.init_database()
       
       # Create default admin user
       web_app.create_default_admin()
       
       # Start application
       web_app.run()

Advanced GUI Features
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from gui.advanced_features import (
       RealTimeMonitor, ModelComparison, BatchProcessor, 
       ParameterSensitivity, UncertaintyAnalysis
   )
   import numpy as np
   import pandas as pd
   
   # Real-time monitoring
   class RealTimeMonitoringApp:
       def __init__(self):
           self.monitor = RealTimeMonitor()
           self.setup_monitoring()
       
       def setup_monitoring(self):
           """Setup real-time monitoring."""
           # Configure data sources
           self.monitor.add_data_source(
               name='gauge_station_001',
               type='tcp_socket',
               host='192.168.1.100',
               port=8080,
               update_interval=60  # 1 minute
           )
           
           self.monitor.add_data_source(
               name='weather_station',
               type='http_api',
               url='http://api.weather.com/data',
               api_key='your_api_key',
               update_interval=300  # 5 minutes
           )
           
           # Setup alerts
           self.monitor.add_alert(
               name='flood_warning',
               condition='water_level > 5.0',
               severity='high',
               notification_methods=['email', 'sms']
           )
           
           self.monitor.add_alert(
               name='equipment_failure',
               condition='data_age > 600',  # No data for 10 minutes
               severity='critical',
               notification_methods=['email', 'phone']
           )
           
           # Start monitoring
           self.monitor.start()
       
       def get_current_status(self):
           """Get current monitoring status."""
           return self.monitor.get_status()
   
   # Model comparison tool
   class ModelComparisonTool:
       def __init__(self):
           self.comparison = ModelComparison()
       
       def compare_models(self, models, test_data):
           """Compare multiple models."""
           # Add models to comparison
           for model_name, model in models.items():
               self.comparison.add_model(model_name, model)
           
           # Run comparison
           results = self.comparison.run_comparison(
               test_data=test_data,
               metrics=['rmse', 'mae', 'r2', 'nse'],
               cross_validation=True,
               cv_folds=5
           )
           
           # Generate comparison report
           report = self.comparison.generate_report(results)
           
           return report
   
   # Batch processing
   class BatchProcessingTool:
       def __init__(self):
           self.processor = BatchProcessor()
       
       def setup_batch_job(self, job_config):
           """Setup batch processing job."""
           # Define processing pipeline
           pipeline = [
               {'step': 'load_data', 'params': {'file_pattern': '*.csv'}},
               {'step': 'quality_control', 'params': {'remove_outliers': True}},
               {'step': 'baseflow_separation', 'params': {'alpha': 0.925}},
               {'step': 'run_model', 'params': {'model_type': '1d_hydraulic'}},
               {'step': 'save_results', 'params': {'format': 'netcdf'}}
           ]
           
           # Configure job
           job = self.processor.create_job(
               name=job_config['name'],
               pipeline=pipeline,
               input_directory=job_config['input_dir'],
               output_directory=job_config['output_dir'],
               parallel_workers=job_config.get('workers', 4)
           )
           
           return job
       
       def run_batch_job(self, job):
           """Run batch processing job."""
           # Start job
           job_id = self.processor.submit_job(job)
           
           # Monitor progress
           while not self.processor.is_job_complete(job_id):
               progress = self.processor.get_job_progress(job_id)
               print(f"Job progress: {progress['completed']}/{progress['total']} files")
               time.sleep(10)
           
           # Get results
           results = self.processor.get_job_results(job_id)
           
           return results
   
   # Parameter sensitivity analysis
   class SensitivityAnalysisTool:
       def __init__(self):
           self.sensitivity = ParameterSensitivity()
       
       def run_sensitivity_analysis(self, model, parameters, ranges):
           """Run parameter sensitivity analysis."""
           # Define parameter ranges
           param_ranges = {
               'roughness': (0.02, 0.05),
               'time_step': (30, 120),
               'theta': (0.5, 0.8)
           }
           
           # Run sensitivity analysis
           results = self.sensitivity.analyze(
               model=model,
               parameters=param_ranges,
               method='sobol',
               n_samples=1000,
               output_variables=['peak_flow', 'time_to_peak']
           )
           
           # Generate sensitivity indices
           sensitivity_indices = self.sensitivity.calculate_indices(results)
           
           # Create visualization
           self.sensitivity.plot_sensitivity(sensitivity_indices)
           
           return sensitivity_indices
   
   # Uncertainty analysis
   class UncertaintyAnalysisTool:
       def __init__(self):
           self.uncertainty = UncertaintyAnalysis()
       
       def run_uncertainty_analysis(self, model, uncertainties):
           """Run uncertainty analysis."""
           # Define uncertainty sources
           uncertainty_sources = {
               'input_data': {
                   'type': 'normal',
                   'mean': 0,
                   'std': 0.1  # 10% uncertainty
               },
               'model_parameters': {
                   'type': 'uniform',
                   'bounds': (-0.2, 0.2)  # ±20% uncertainty
               },
               'boundary_conditions': {
                   'type': 'triangular',
                   'mode': 0,
                   'left': -0.15,
                   'right': 0.15
               }
           }
           
           # Run Monte Carlo simulation
           results = self.uncertainty.monte_carlo(
               model=model,
               uncertainties=uncertainty_sources,
               n_simulations=10000,
               output_variables=['water_level', 'flow_rate']
           )
           
           # Calculate uncertainty metrics
           uncertainty_metrics = self.uncertainty.calculate_metrics(results)
           
           # Generate uncertainty bands
           confidence_intervals = self.uncertainty.calculate_confidence_intervals(
               results, confidence_levels=[0.68, 0.95, 0.99]
           )
           
           return {
               'results': results,
               'metrics': uncertainty_metrics,
               'confidence_intervals': confidence_intervals
           }

Configuration and Customization
-------------------------------

GUI Themes and Styling
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Theme configuration
   theme_config = {
       'dark_theme': {
           'background_color': '#2b2b2b',
           'text_color': '#ffffff',
           'accent_color': '#0078d4',
           'plot_background': '#1e1e1e',
           'grid_color': '#404040'
       },
       'light_theme': {
           'background_color': '#ffffff',
           'text_color': '#000000',
           'accent_color': '#0078d4',
           'plot_background': '#f8f9fa',
           'grid_color': '#e0e0e0'
       },
       'scientific_theme': {
           'background_color': '#ffffff',
           'text_color': '#000000',
           'accent_color': '#d62728',
           'plot_background': '#ffffff',
           'grid_color': '#cccccc',
           'font_family': 'Times New Roman'
       }
   }

Layout Configuration
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Layout configuration
   layout_config = {
       'main_window': {
           'width': 1400,
           'height': 900,
           'resizable': True,
           'maximized': False
       },
       'panels': {
           'model_tree': {'width': 250, 'dockable': True},
           'properties': {'width': 300, 'dockable': True},
           'visualization': {'expandable': True},
           'console': {'height': 150, 'collapsible': True}
       },
       'toolbars': {
           'main': ['new', 'open', 'save', 'run', 'stop'],
           'visualization': ['zoom', 'pan', 'export', 'settings']
       }
   }

User Preferences
~~~~~~~~~~~~~~~~

.. code-block:: python

   # User preferences
   user_preferences = {
       'general': {
           'auto_save': True,
           'auto_save_interval': 300,  # seconds
           'recent_files_count': 10,
           'default_project_location': 'C:/HydrologyProjects'
       },
       'visualization': {
           'default_plot_type': 'line',
           'animation_speed': 'medium',
           'color_scheme': 'viridis',
           'show_grid': True,
           'show_legend': True
       },
       'simulation': {
           'default_time_step': 60,
           'max_simulation_time': 86400,
           'auto_start_visualization': True,
           'save_intermediate_results': False
       }
   }

Performance Optimization
------------------------

Rendering Optimization
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Rendering optimization settings
   rendering_config = {
       'use_opengl': True,
       'antialiasing': True,
       'max_plot_points': 10000,
       'level_of_detail': True,
       'background_rendering': True,
       'cache_plots': True,
       'update_frequency': 30  # FPS
   }

Memory Management
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Memory management
   memory_config = {
       'max_memory_usage': '4GB',
       'data_streaming': True,
       'lazy_loading': True,
       'garbage_collection': 'aggressive',
       'cache_size': '1GB'
   }

Error Handling and Debugging
----------------------------

Error Handling
~~~~~~~~~~~~~~

.. code-block:: python

   from gui.error_handling import ErrorHandler, UserNotification
   
   # Setup error handling
   error_handler = ErrorHandler()
   
   # Configure error logging
   error_handler.setup_logging({
       'log_file': 'gui_errors.log',
       'log_level': 'ERROR',
       'max_file_size': '10MB',
       'backup_count': 5
   })
   
   # Setup user notifications
   notification_system = UserNotification()
   
   # Handle different types of errors
   try:
       # GUI operation that might fail
       result = some_gui_operation()
   except FileNotFoundError as e:
       error_handler.handle_file_error(e)
       notification_system.show_error(
           title="File Not Found",
           message="The specified file could not be found.",
           details=str(e)
       )
   except MemoryError as e:
       error_handler.handle_memory_error(e)
       notification_system.show_warning(
           title="Memory Warning",
           message="The operation requires more memory than available.",
           suggestion="Try reducing the data size or closing other applications."
       )
   except Exception as e:
       error_handler.handle_generic_error(e)
       notification_system.show_error(
           title="Unexpected Error",
           message="An unexpected error occurred.",
           details=str(e)
       )

Debugging Tools
~~~~~~~~~~~~~~~

.. code-block:: python

   from gui.debugging import GUIDebugger
   
   # Create debugger
   debugger = GUIDebugger()
   
   # Enable debug mode
   debugger.enable_debug_mode({
       'show_widget_borders': True,
       'log_events': True,
       'performance_monitoring': True,
       'memory_tracking': True
   })
   
   # Monitor GUI performance
   performance_stats = debugger.get_performance_stats()
   print(f"Render time: {performance_stats['avg_render_time']:.2f}ms")
   print(f"Memory usage: {performance_stats['memory_usage']:.1f}MB")
   print(f"Event queue size: {performance_stats['event_queue_size']}")

Deployment and Distribution
---------------------------

Desktop Application Packaging
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # PyInstaller configuration for desktop app
   pyinstaller_config = {
       'name': 'HydrologyFramework',
       'entry_point': 'gui/main_window.py',
       'icon': 'resources/icon.ico',
       'windowed': True,
       'one_file': False,
       'additional_data': [
           ('resources/', 'resources/'),
           ('templates/', 'templates/'),
           ('static/', 'static/')
       ],
       'hidden_imports': [
           'PyQt5.QtWebEngineWidgets',
           'matplotlib.backends.backend_qt5agg'
       ]
   }

Web Application Deployment
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Docker configuration for web app
   docker_config = {
       'base_image': 'python:3.9-slim',
       'working_directory': '/app',
       'exposed_ports': [5000],
       'environment_variables': {
           'FLASK_ENV': 'production',
           'DATABASE_URL': 'postgresql://user:pass@db:5432/hydrology'
       },
       'volumes': [
           '/app/uploads',
           '/app/results'
       ]
   }
   
   # Kubernetes deployment
   k8s_config = {
       'replicas': 3,
       'resources': {
           'requests': {'cpu': '500m', 'memory': '1Gi'},
           'limits': {'cpu': '2', 'memory': '4Gi'}
       },
       'services': {
           'web': {'port': 80, 'target_port': 5000},
           'database': {'port': 5432}
       }
   }

Installer Creation
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # NSIS installer configuration
   installer_config = {
       'name': 'Hydrology Framework',
       'version': '1.0.0',
       'publisher': 'Hydrology Research Group',
       'install_directory': '$PROGRAMFILES\\HydrologyFramework',
       'shortcuts': {
           'desktop': True,
           'start_menu': True
       },
       'file_associations': ['.hyd', '.hydro'],
       'uninstaller': True,
       'license_file': 'LICENSE.txt'
   }