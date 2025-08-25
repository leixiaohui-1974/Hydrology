"""
Responsive Web Application for Hydrology Modeling
================================================
This module provides a responsive web interface that works on both
mobile and desktop devices.
"""
import dash
from dash import dcc, html, Input, Output, callback_context, State
import plotly.graph_objs as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import threading
import time
import json
import os
from datetime import datetime, timedelta
import queue

# Add parent directory to path for imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from gui.visualization.3d_viewer import Hydrology3DViewer
from gui.dashboard.real_time_dashboard import RealTimeDashboard
from gui.workflow.workflow_manager import WorkflowManager


class ResponsiveHydrologyApp:
    """
    Responsive web application for hydrological modeling.
    """
    
    def __init__(self, port: int = 8050, debug: bool = True):
        """
        Initialize the responsive web app.
        
        Args:
            port: Port number for the web app
            debug: Enable debug mode
        """
        self.app = dash.Dash(__name__, external_stylesheets=[
            'https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css',
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css'
        ])
        self.port = port
        self.debug = debug
        
        # Initialize components
        self.workflow_manager = WorkflowManager()
        self.terrain_viewer = None
        self.simulation_data = {
            'time_steps': [],
            'flow_rates': {},
            'water_levels': {},
            'performance_metrics': {
                'cpu_usage': [],
                'memory_usage': [],
                'execution_time': []
            }
        }
        
        # Setup layout and callbacks
        self._setup_layout()
        self._setup_callbacks()
        
    def _setup_layout(self):
        """Setup the responsive layout."""
        self.app.layout = html.Div([
            # Navigation bar
            self._create_navbar(),
            
            # Main content container
            html.Div([
                # Mobile-friendly sidebar toggle
                html.Button([
                    html.I(className="fas fa-bars")
                ], id="sidebar-toggle", className="btn btn-primary d-md-none", 
                   style={'position': 'fixed', 'top': '70px', 'left': '10px', 'zIndex': 1000}),
                
                # Sidebar
                html.Div([
                    self._create_sidebar()
                ], id="sidebar", className="col-md-3 col-lg-2 d-none d-md-block"),
                
                # Main content area
                html.Div([
                    # Dashboard overview
                    self._create_dashboard_overview(),
                    
                    # Simulation controls
                    self._create_simulation_controls(),
                    
                    # Results and visualization
                    self._create_results_section(),
                    
                    # Performance monitoring
                    self._create_performance_section()
                ], className="col-md-9 col-lg-10 ml-sm-auto px-4")
            ], className="row", style={'marginTop': '70px'})
        ])
        
    def _create_navbar(self):
        """Create the navigation bar."""
        return html.Nav([
            html.Div([
                html.A([
                    html.I(className="fas fa-water mr-2"),
                    "Hydro-Suite"
                ], className="navbar-brand", href="#"),
                
                # Mobile menu button
                html.Button([
                    html.Span(className="navbar-toggler-icon")
                ], className="navbar-toggler", type="button", 
                   **{"data-toggle": "collapse", "data-target": "#navbarNav"}),
                
                # Navigation items
                html.Div([
                    html.Ul([
                        html.Li([
                            html.A("Dashboard", className="nav-link", href="#dashboard")
                        ], className="nav-item"),
                        html.Li([
                            html.A("Simulation", className="nav-link", href="#simulation")
                        ], className="nav-item"),
                        html.Li([
                            html.A("3D View", className="nav-link", href="#3dview")
                        ], className="nav-item"),
                        html.Li([
                            html.A("Analysis", className="nav-link", href="#analysis")
                        ], className="nav-item"),
                        html.Li([
                            html.A("Workflow", className="nav-link", href="#workflow")
                        ], className="nav-item")
                    ], className="navbar-nav ml-auto")
                ], className="collapse navbar-collapse", id="navbarNav")
            ], className="container")
        ], className="navbar navbar-expand-md navbar-dark bg-primary fixed-top")
        
    def _create_sidebar(self):
        """Create the sidebar with project information."""
        return html.Div([
            html.H5("Project Info", className="mb-3"),
            
            # Project selector
            html.Div([
                html.Label("Current Project:"),
                dcc.Dropdown(
                    id="project-selector",
                    options=[
                        {'label': 'Demo Project', 'value': 'demo'},
                        {'label': 'New Project', 'value': 'new'}
                    ],
                    value='demo',
                    clearable=False
                )
            ], className="mb-3"),
            
            # Quick stats
            html.Div([
                html.H6("Quick Stats", className="mb-2"),
                html.Div([
                    html.Small("Components: 5"),
                    html.Br(),
                    html.Small("Time Steps: 1000"),
                    html.Br(),
                    html.Small("Status: Ready")
                ], className="text-muted")
            ], className="mb-3"),
            
            # Quick actions
            html.Div([
                html.H6("Quick Actions", className="mb-2"),
                html.Button("New Simulation", className="btn btn-sm btn-outline-primary btn-block mb-2"),
                html.Button("Load Data", className="btn btn-sm btn-outline-secondary btn-block mb-2"),
                html.Button("Export Results", className="btn btn-sm btn-outline-success btn-block")
            ])
        ], className="bg-light p-3", style={'minHeight': '100vh'})
        
    def _create_dashboard_overview(self):
        """Create the dashboard overview section."""
        return html.Div([
            html.H2("Dashboard Overview", className="mb-4"),
            
            # Status cards
            html.Div([
                html.Div([
                    html.Div([
                        html.I(className="fas fa-play-circle fa-2x text-success"),
                        html.H4("Ready", className="mt-2"),
                        html.P("Simulation Status", className="text-muted mb-0")
                    ], className="text-center")
                ], className="col-md-3 col-sm-6 mb-3"),
                
                html.Div([
                    html.Div([
                        html.I(className="fas fa-microchip fa-2x text-info"),
                        html.H4("0%", className="mt-2"),
                        html.P("CPU Usage", className="text-muted mb-0")
                    ], className="text-center")
                ], className="col-md-3 col-sm-6 mb-3"),
                
                html.Div([
                    html.Div([
                        html.I(className="fas fa-memory fa-2x text-warning"),
                        html.H4("0 MB", className="mt-2"),
                        html.P("Memory Usage", className="text-muted mb-0")
                    ], className="text-center")
                ], className="col-md-3 col-sm-6 mb-3"),
                
                html.Div([
                    html.Div([
                        html.I(className="fas fa-clock fa-2x text-primary"),
                        html.H4("0s", className="mt-2"),
                        html.P("Execution Time", className="text-muted mb-0")
                    ], className="text-center")
                ], className="col-md-3 col-sm-6 mb-3")
            ], className="row")
        ], id="dashboard", className="mb-5")
        
    def _create_simulation_controls(self):
        """Create the simulation controls section."""
        return html.Div([
            html.H3("Simulation Controls", className="mb-4"),
            
            # Control panel
            html.Div([
                html.Div([
                    html.Label("Time Steps:"),
                    dcc.Input(
                        id="time-steps-input",
                        type="number",
                        value=1000,
                        min=1,
                        className="form-control"
                    )
                ], className="col-md-3 mb-3"),
                
                html.Div([
                    html.Label("Time Step (s):"),
                    dcc.Input(
                        id="dt-input",
                        type="number",
                        value=1.0,
                        min=0.1,
                        step=0.1,
                        className="form-control"
                    )
                ], className="col-md-3 mb-3"),
                
                html.Div([
                    html.Label("Parallel Processing:"),
                    dcc.Checklist(
                        id="parallel-checklist",
                        options=[{'label': 'Enable', 'value': 'enable'}],
                        value=['enable'],
                        className="mt-2"
                    )
                ], className="col-md-3 mb-3"),
                
                html.Div([
                    html.Label("Max Workers:"),
                    dcc.Input(
                        id="max-workers-input",
                        type="number",
                        value=4,
                        min=1,
                        max=16,
                        className="form-control"
                    )
                ], className="col-md-3 mb-3")
            ], className="row mb-4"),
            
            # Control buttons
            html.Div([
                html.Button([
                    html.I(className="fas fa-play mr-2"),
                    "Start Simulation"
                ], id="start-sim-btn", className="btn btn-success btn-lg mr-3"),
                
                html.Button([
                    html.I(className="fas fa-pause mr-2"),
                    "Pause"
                ], id="pause-sim-btn", className="btn btn-warning btn-lg mr-3", disabled=True),
                
                html.Button([
                    html.I(className="fas fa-stop mr-2"),
                    "Stop"
                ], id="stop-sim-btn", className="btn btn-danger btn-lg", disabled=True)
            ], className="text-center mb-4"),
            
            # Progress bar
            html.Div([
                html.Label("Progress:", className="mr-2"),
                dcc.ProgressBar(
                    id="sim-progress",
                    value=0,
                    className="mb-3"
                )
            ])
        ], id="simulation", className="mb-5")
        
    def _create_results_section(self):
        """Create the results and visualization section."""
        return html.Div([
            html.H3("Results & Visualization", className="mb-4"),
            
            # Results tabs
            dcc.Tabs([
                dcc.Tab(label="Flow Rates", children=[
                    dcc.Graph(
                        id="flow-rates-chart",
                        style={'height': '400px'}
                    )
                ]),
                
                dcc.Tab(label="Water Levels", children=[
                    dcc.Graph(
                        id="water-levels-chart",
                        style={'height': '400px'}
                    )
                ]),
                
                dcc.Tab(label="3D View", children=[
                    html.Div([
                        html.H5("3D Visualization", className="text-center mb-3"),
                        html.Div([
                            html.Button("Load Terrain", id="load-terrain-btn", 
                                      className="btn btn-primary mr-2"),
                            html.Button("Create 3D View", id="create-3d-btn", 
                                      className="btn btn-success mr-2"),
                            html.Button("Export Scene", id="export-3d-btn", 
                                      className="btn btn-info")
                        ], className="text-center mb-3"),
                        html.Div(id="3d-container", className="text-center")
                    ])
                ])
            ], id="results-tabs")
        ], id="3dview", className="mb-5")
        
    def _create_performance_section(self):
        """Create the performance monitoring section."""
        return html.Div([
            html.H3("Performance Monitoring", className="mb-4"),
            
            # Performance charts
            html.Div([
                html.Div([
                    dcc.Graph(
                        id="performance-chart",
                        style={'height': '300px'}
                    )
                ], className="col-md-6 mb-3"),
                
                html.Div([
                    dcc.Graph(
                        id="resource-usage-chart",
                        style={'height': '300px'}
                    )
                ], className="col-md-6 mb-3")
            ], className="row"),
            
            # Performance metrics table
            html.Div([
                html.H5("Detailed Metrics", className="mb-3"),
                html.Div(id="performance-table")
            ])
        ], id="analysis", className="mb-5")
        
    def _setup_callbacks(self):
        """Setup the application callbacks."""
        
        @self.app.callback(
            [Output("start-sim-btn", "disabled"),
             Output("pause-sim-btn", "disabled"),
             Output("stop-sim-btn", "disabled")],
            [Input("start-sim-btn", "n_clicks"),
             Input("pause-sim-btn", "n_clicks"),
             Input("stop-sim-btn", "n_clicks")],
            [State("start-sim-btn", "disabled")]
        )
        def update_button_states(start_clicks, pause_clicks, stop_clicks, start_disabled):
            """Update button states based on simulation status."""
            ctx = callback_context
            if not ctx.triggered:
                return False, True, True
                
            button_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            if button_id == "start-sim-btn":
                return True, False, False
            elif button_id == "pause-sim-btn":
                return False, True, False
            elif button_id == "stop-sim-btn":
                return False, True, True
                
            return start_disabled, True, True
            
        @self.app.callback(
            Output("sim-progress", "value"),
            [Input("start-sim-btn", "n_clicks")],
            [State("time-steps-input", "value")]
        )
        def update_progress(start_clicks, time_steps):
            """Update simulation progress."""
            if start_clicks is None:
                return 0
                
            # Simulate progress updates
            def progress_updater():
                for i in range(1, time_steps + 1):
                    progress = (i / time_steps) * 100
                    time.sleep(0.1)  # Simulate work
                    
            # Start progress in background
            thread = threading.Thread(target=progress_updater, daemon=True)
            thread.start()
            
            return 0
            
        @self.app.callback(
            Output("flow-rates-chart", "figure"),
            [Input("start-sim-btn", "n_clicks")]
        )
        def update_flow_chart(start_clicks):
            """Update flow rates chart."""
            if start_clicks is None:
                return self._create_empty_chart("Flow Rates")
                
            # Generate sample data
            time_steps = 100
            flow_data = {
                'Catchment1': np.random.normal(10, 2, time_steps),
                'Catchment2': np.random.normal(15, 3, time_steps),
                'Catchment3': np.random.normal(12, 2.5, time_steps)
            }
            
            fig = go.Figure()
            for component, data in flow_data.items():
                fig.add_trace(go.Scatter(
                    x=list(range(time_steps)),
                    y=data,
                    mode='lines+markers',
                    name=component
                ))
                
            fig.update_layout(
                title="Flow Rates Over Time",
                xaxis_title="Time Step",
                yaxis_title="Flow Rate (m³/s)",
                height=400
            )
            
            return fig
            
        @self.app.callback(
            Output("water-levels-chart", "figure"),
            [Input("start-sim-btn", "n_clicks")]
        )
        def update_water_level_chart(start_clicks):
            """Update water levels chart."""
            if start_clicks is None:
                return self._create_empty_chart("Water Levels")
                
            # Generate sample data
            time_steps = 100
            level_data = {
                'Reservoir1': np.random.normal(100, 5, time_steps),
                'Reservoir2': np.random.normal(95, 4, time_steps)
            }
            
            fig = go.Figure()
            for component, data in level_data.items():
                fig.add_trace(go.Scatter(
                    x=list(range(time_steps)),
                    y=data,
                    mode='lines+markers',
                    name=component
                ))
                
            fig.update_layout(
                title="Water Levels Over Time",
                xaxis_title="Time Step",
                yaxis_title="Water Level (m)",
                height=400
            )
            
            return fig
            
        @self.app.callback(
            Output("performance-chart", "figure"),
            [Input("start-sim-btn", "n_clicks")]
        )
        def update_performance_chart(start_clicks):
            """Update performance chart."""
            if start_clicks is None:
                return self._create_empty_chart("Performance")
                
            # Generate sample performance data
            time_steps = 50
            execution_times = np.cumsum(np.random.exponential(0.1, time_steps))
            cpu_usage = np.random.uniform(20, 80, time_steps)
            memory_usage = np.random.uniform(100, 500, time_steps)
            
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Execution Time', 'Resource Usage'),
                vertical_spacing=0.1
            )
            
            # Execution time
            fig.add_trace(
                go.Scatter(x=list(range(time_steps)), y=execution_times,
                          mode='lines+markers', name='Execution Time'),
                row=1, col=1
            )
            
            # CPU and Memory usage
            fig.add_trace(
                go.Scatter(x=list(range(time_steps)), y=cpu_usage,
                          mode='lines+markers', name='CPU Usage'),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(x=list(range(time_steps)), y=memory_usage,
                          mode='lines+markers', name='Memory Usage'),
                row=2, col=1
            )
            
            fig.update_layout(height=300, showlegend=True)
            return fig
            
        @self.app.callback(
            Output("resource-usage-chart", "figure"),
            [Input("start-sim-btn", "n_clicks")]
        )
        def update_resource_chart(start_clicks):
            """Update resource usage chart."""
            if start_clicks is None:
                return self._create_empty_chart("Resource Usage")
                
            # Create gauge chart for current resource usage
            fig = go.Figure()
            
            fig.add_trace(go.Indicator(
                mode="gauge+number+delta",
                value=65,  # Sample value
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Current CPU Usage (%)"},
                delta={'reference': 50},
                gauge={
                    'axis': {'range': [None, 100]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 50], 'color': "lightgray"},
                        {'range': [50, 80], 'color': "yellow"},
                        {'range': [80, 100], 'color': "red"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 90
                    }
                }
            ))
            
            fig.update_layout(height=300)
            return fig
            
        @self.app.callback(
            Output("3d-container", "children"),
            [Input("create-3d-btn", "n_clicks")]
        )
        def create_3d_view(create_clicks):
            """Create 3D visualization."""
            if create_clicks is None:
                return html.P("Click 'Create 3D View' to generate visualization")
                
            # This would integrate with the actual 3D viewer
            return html.Div([
                html.H6("3D Visualization Generated", className="text-success"),
                html.P("3D scene has been created successfully."),
                html.Div([
                    html.Button("Rotate View", className="btn btn-sm btn-outline-primary mr-2"),
                    html.Button("Zoom In", className="btn btn-sm btn-outline-secondary mr-2"),
                    html.Button("Reset Camera", className="btn btn-sm btn-outline-info")
                ])
            ])
            
    def _create_empty_chart(self, title: str) -> go.Figure:
        """Create an empty chart with a message."""
        fig = go.Figure()
        fig.add_annotation(
            text=f"No data available for {title}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            title=title,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig
        
    def run(self, host: str = "127.0.0.1"):
        """Run the web application."""
        try:
            self.app.run_server(host=host, port=self.port, debug=self.debug)
        except Exception as e:
            print(f"Failed to start web app: {e}")


def main():
    """Main function to run the responsive web app."""
    try:
        app = ResponsiveHydrologyApp()
        app.run()
    except Exception as e:
        print(f"Failed to start responsive app: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
