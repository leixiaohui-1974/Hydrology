"""
Real-time Dashboard for Hydrology Simulations
============================================
This module provides a real-time dashboard for monitoring simulation progress,
performance metrics, and model outputs.
"""
import dash
from dash import dcc, html, Input, Output, callback_context
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


class RealTimeDashboard:
    """
    Real-time dashboard for monitoring hydrological simulations.
    """
    
    def __init__(self, port: int = 8050, debug: bool = True):
        """
        Initialize the real-time dashboard.
        
        Args:
            port: Port number for the dashboard
            debug: Enable debug mode
        """
        self.app = dash.Dash(__name__, external_stylesheets=[
            'https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css'
        ])
        self.port = port
        self.debug = debug
        
        # Data storage
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
        
        # Update queue for real-time data
        self.update_queue = queue.Queue()
        self.update_thread = None
        self.stop_updates = False
        
        # Setup dashboard layout
        self._setup_layout()
        self._setup_callbacks()
        
    def _setup_layout(self):
        """Setup the dashboard layout."""
        self.app.layout = html.Div([
            # Header
            html.Div([
                html.H1("Hydrology Simulation Dashboard", 
                       className="text-center text-primary mb-4"),
                html.Div([
                    html.Span("Status: ", className="font-weight-bold"),
                    html.Span(id="simulation-status", 
                             children="Ready", 
                             className="badge badge-success")
                ], className="text-center mb-3")
            ], className="container-fluid"),
            
            # Main content
            html.Div([
                # First row - Performance metrics
                html.Div([
                    html.Div([
                        html.H4("Performance Metrics", className="text-center"),
                        dcc.Graph(id="performance-chart", style={'height': '300px'})
                    ], className="col-md-6"),
                    html.Div([
                        html.H4("Resource Usage", className="text-center"),
                        dcc.Graph(id="resource-chart", style={'height': '300px'})
                    ], className="col-md-6")
                ], className="row mb-4"),
                
                # Second row - Simulation results
                html.Div([
                    html.Div([
                        html.H4("Flow Rates", className="text-center"),
                        dcc.Graph(id="flow-chart", style={'height': '300px'})
                    ], className="col-md-6"),
                    html.Div([
                        html.H4("Water Levels", className="text-center"),
                        dcc.Graph(id="water-level-chart", style={'height': '300px'})
                    ], className="col-md-6")
                ], className="row mb-4"),
                
                # Third row - 3D visualization and controls
                html.Div([
                    html.Div([
                        html.H4("3D Model View", className="text-center"),
                        html.Div(id="3d-container", style={'height': '400px'})
                    ], className="col-md-8"),
                    html.Div([
                        html.H4("Controls", className="text-center"),
                        html.Div([
                            html.Button("Start Simulation", 
                                      id="start-btn", 
                                      className="btn btn-success btn-block mb-2"),
                            html.Button("Pause Simulation", 
                                      id="pause-btn", 
                                      className="btn btn-warning btn-block mb-2"),
                            html.Button("Stop Simulation", 
                                      id="stop-btn", 
                                      className="btn btn-danger btn-block mb-2"),
                            html.Button("Export Results", 
                                      id="export-btn", 
                                      className="btn btn-info btn-block mb-2")
                        ]),
                        html.Hr(),
                        html.H5("Simulation Info"),
                        html.Div(id="simulation-info")
                    ], className="col-md-4")
                ], className="row mb-4"),
                
                # Fourth row - Logs and alerts
                html.Div([
                    html.Div([
                        html.H4("Simulation Logs", className="text-center"),
                        html.Div(id="logs-container", 
                                style={'height': '200px', 'overflow-y': 'scroll',
                                       'border': '1px solid #ddd', 'padding': '10px'})
                    ], className="col-md-6"),
                    html.Div([
                        html.H4("Alerts & Warnings", className="text-center"),
                        html.Div(id="alerts-container",
                                style={'height': '200px', 'overflow-y': 'scroll',
                                       'border': '1px solid #ddd', 'padding': '10px'})
                    ], className="col-md-6")
                ], className="row")
            ], className="container-fluid"),
            
            # Hidden div for storing data
            html.Div(id="data-store", style={'display': 'none'}),
            
            # Update interval
            dcc.Interval(
                id='interval-component',
                interval=1000,  # Update every second
                n_intervals=0
            )
        ])
        
    def _setup_callbacks(self):
        """Setup dashboard callbacks."""
        
        @self.app.callback(
            Output("performance-chart", "figure"),
            Input("interval-component", "n_intervals")
        )
        def update_performance_chart(n):
            """Update performance metrics chart."""
            if not self.simulation_data['performance_metrics']['execution_time']:
                return self._create_empty_chart("Performance Metrics")
                
            df = pd.DataFrame({
                'Time': range(len(self.simulation_data['performance_metrics']['execution_time'])),
                'Execution Time': self.simulation_data['performance_metrics']['execution_time'],
                'CPU Usage': self.simulation_data['performance_metrics']['cpu_usage'],
                'Memory Usage': self.simulation_data['performance_metrics']['memory_usage']
            })
            
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=('Execution Time', 'Resource Usage'),
                vertical_spacing=0.1
            )
            
            # Execution time
            fig.add_trace(
                go.Scatter(x=df['Time'], y=df['Execution Time'], 
                          mode='lines+markers', name='Execution Time'),
                row=1, col=1
            )
            
            # CPU and Memory usage
            fig.add_trace(
                go.Scatter(x=df['Time'], y=df['CPU Usage'], 
                          mode='lines+markers', name='CPU Usage'),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(x=df['Time'], y=df['Memory Usage'], 
                          mode='lines+markers', name='Memory Usage'),
                row=2, col=1
            )
            
            fig.update_layout(height=300, showlegend=True)
            return fig
            
        @self.app.callback(
            Output("resource-chart", "figure"),
            Input("interval-component", "n_intervals")
        )
        def update_resource_chart(n):
            """Update resource usage chart."""
            if not self.simulation_data['performance_metrics']['cpu_usage']:
                return self._create_empty_chart("Resource Usage")
                
            df = pd.DataFrame({
                'Time': range(len(self.simulation_data['performance_metrics']['cpu_usage'])),
                'CPU': self.simulation_data['performance_metrics']['cpu_usage'],
                'Memory': self.simulation_data['performance_metrics']['memory_usage']
            })
            
            fig = go.Figure()
            
            # CPU usage gauge
            fig.add_trace(go.Indicator(
                mode="gauge+number+delta",
                value=df['CPU'].iloc[-1] if len(df) > 0 else 0,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "CPU Usage (%)"},
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
            Output("flow-chart", "figure"),
            Input("interval-component", "n_intervals")
        )
        def update_flow_chart(n):
            """Update flow rates chart."""
            if not self.simulation_data['flow_rates']:
                return self._create_empty_chart("Flow Rates")
                
            fig = go.Figure()
            
            for component, flow_data in self.simulation_data['flow_rates'].items():
                if flow_data:  # Check if flow data exists
                    fig.add_trace(go.Scatter(
                        x=self.simulation_data['time_steps'][:len(flow_data)],
                        y=flow_data,
                        mode='lines+markers',
                        name=component
                    ))
            
            fig.update_layout(
                title="Flow Rates Over Time",
                xaxis_title="Time Step",
                yaxis_title="Flow Rate (m³/s)",
                height=300
            )
            return fig
            
        @self.app.callback(
            Output("water-level-chart", "figure"),
            Input("interval-component", "n_intervals")
        )
        def update_water_level_chart(n):
            """Update water levels chart."""
            if not self.simulation_data['water_levels']:
                return self._create_empty_chart("Water Levels")
                
            fig = go.Figure()
            
            for component, level_data in self.simulation_data['water_levels'].items():
                if level_data:  # Check if level data exists
                    fig.add_trace(go.Scatter(
                        x=self.simulation_data['time_steps'][:len(level_data)],
                        y=level_data,
                        mode='lines+markers',
                        name=component
                    ))
            
            fig.update_layout(
                title="Water Levels Over Time",
                xaxis_title="Time Step",
                yaxis_title="Water Level (m)",
                height=300
            )
            return fig
            
        @self.app.callback(
            Output("simulation-status", "children"),
            Output("simulation-status", "className"),
            Input("interval-component", "n_intervals")
        )
        def update_status(n):
            """Update simulation status."""
            # This would be updated based on actual simulation state
            return "Running", "badge badge-primary"
            
        @self.app.callback(
            Output("simulation-info", "children"),
            Input("interval-component", "n_intervals")
        )
        def update_simulation_info(n):
            """Update simulation information."""
            if not self.simulation_data['time_steps']:
                return html.P("No simulation data available")
                
            current_step = len(self.simulation_data['time_steps'])
            total_steps = max(self.simulation_data['time_steps']) if self.simulation_data['time_steps'] else 0
            
            return html.Div([
                html.P(f"Current Step: {current_step}"),
                html.P(f"Total Steps: {total_steps}"),
                html.P(f"Progress: {current_step/total_steps*100:.1f}%" if total_steps > 0 else "0%"),
                html.P(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
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
        
    def start_update_thread(self):
        """Start the background update thread."""
        if self.update_thread is None or not self.update_thread.is_alive():
            self.stop_updates = False
            self.update_thread = threading.Thread(target=self._update_loop)
            self.update_thread.daemon = True
            self.update_thread.start()
            
    def stop_update_thread(self):
        """Stop the background update thread."""
        self.stop_updates = True
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join()
            
    def _update_loop(self):
        """Background loop for updating dashboard data."""
        while not self.stop_updates:
            try:
                # Process updates from queue
                while not self.update_queue.empty():
                    update_data = self.update_queue.get_nowait()
                    self._process_update(update_data)
                    
                time.sleep(1)  # Update every second
            except Exception as e:
                print(f"Error in update loop: {e}")
                time.sleep(5)  # Wait longer on error
                
    def _process_update(self, update_data: Dict[str, Any]):
        """Process an update from the simulation."""
        if 'type' not in update_data:
            return
            
        update_type = update_data['type']
        
        if update_type == 'flow_rate':
            component = update_data.get('component', 'unknown')
            flow_rate = update_data.get('value', 0.0)
            time_step = update_data.get('time_step', 0)
            
            if component not in self.simulation_data['flow_rates']:
                self.simulation_data['flow_rates'][component] = []
                
            # Ensure we have enough time steps
            while len(self.simulation_data['time_steps']) <= time_step:
                self.simulation_data['time_steps'].append(len(self.simulation_data['time_steps']))
                
            # Ensure we have enough flow data
            while len(self.simulation_data['flow_rates'][component]) <= time_step:
                self.simulation_data['flow_rates'][component].append(0.0)
                
            self.simulation_data['flow_rates'][component][time_step] = flow_rate
            
        elif update_type == 'water_level':
            component = update_data.get('component', 'unknown')
            water_level = update_data.get('value', 0.0)
            time_step = update_data.get('time_step', 0)
            
            if component not in self.simulation_data['water_levels']:
                self.simulation_data['water_levels'][component] = []
                
            # Ensure we have enough time steps
            while len(self.simulation_data['time_steps']) <= time_step:
                self.simulation_data['time_steps'].append(len(self.simulation_data['time_steps']))
                
            # Ensure we have enough water level data
            while len(self.simulation_data['water_levels'][component]) <= time_step:
                self.simulation_data['water_levels'][component].append(0.0)
                
            self.simulation_data['water_levels'][component][time_step] = water_level
            
        elif update_type == 'performance':
            cpu_usage = update_data.get('cpu_usage', 0.0)
            memory_usage = update_data.get('memory_usage', 0.0)
            execution_time = update_data.get('execution_time', 0.0)
            
            self.simulation_data['performance_metrics']['cpu_usage'].append(cpu_usage)
            self.simulation_data['performance_metrics']['memory_usage'].append(memory_usage)
            self.simulation_data['performance_metrics']['execution_time'].append(execution_time)
            
            # Keep only last 1000 data points
            max_points = 1000
            for key in self.simulation_data['performance_metrics']:
                if len(self.simulation_data['performance_metrics'][key]) > max_points:
                    self.simulation_data['performance_metrics'][key] = \
                        self.simulation_data['performance_metrics'][key][-max_points:]
                        
    def add_flow_rate_update(self, component: str, flow_rate: float, time_step: int):
        """Add a flow rate update to the dashboard."""
        self.update_queue.put({
            'type': 'flow_rate',
            'component': component,
            'value': flow_rate,
            'time_step': time_step
        })
        
    def add_water_level_update(self, component: str, water_level: float, time_step: int):
        """Add a water level update to the dashboard."""
        self.update_queue.put({
            'type': 'water_level',
            'component': component,
            'value': water_level,
            'time_step': time_step
        })
        
    def add_performance_update(self, cpu_usage: float, memory_usage: float, execution_time: float):
        """Add a performance update to the dashboard."""
        self.update_queue.put({
            'type': 'performance',
            'cpu_usage': cpu_usage,
            'memory_usage': memory_usage,
            'execution_time': execution_time
        })
        
    def run(self, host: str = "127.0.0.1"):
        """Run the dashboard."""
        self.start_update_thread()
        try:
            self.app.run_server(host=host, port=self.port, debug=self.debug)
        finally:
            self.stop_update_thread()
            
    def export_data(self, filename: str = None):
        """Export dashboard data to a file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dashboard_data_{timestamp}.json"
            
        # Convert numpy arrays to lists for JSON serialization
        export_data = {}
        for key, value in self.simulation_data.items():
            if isinstance(value, dict):
                export_data[key] = {}
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, list):
                        export_data[key][sub_key] = [float(v) if isinstance(v, (int, float)) else v for v in sub_value]
                    else:
                        export_data[key][sub_key] = sub_value
            elif isinstance(value, list):
                export_data[key] = [float(v) if isinstance(v, (int, float)) else v for v in value]
            else:
                export_data[key] = value
                
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
            
        return filename


class SimulationMonitor:
    """
    Monitor class for integrating with simulation controllers.
    """
    
    def __init__(self, dashboard: RealTimeDashboard):
        """
        Initialize the simulation monitor.
        
        Args:
            dashboard: The real-time dashboard instance
        """
        self.dashboard = dashboard
        self.simulation_running = False
        self.current_time_step = 0
        
    def start_monitoring(self):
        """Start monitoring the simulation."""
        self.simulation_running = True
        self.current_time_step = 0
        
    def stop_monitoring(self):
        """Stop monitoring the simulation."""
        self.simulation_running = False
        
    def update_simulation_step(self, time_step: int, component_results: Dict[str, Any]):
        """Update the dashboard with simulation step results."""
        if not self.simulation_running:
            return
            
        self.current_time_step = time_step
        
        # Update flow rates
        for component, results in component_results.items():
            if 'outflow' in results:
                self.dashboard.add_flow_rate_update(
                    component, results['outflow'], time_step
                )
                
            if 'water_level' in results:
                self.dashboard.add_water_level_update(
                    component, results['water_level'], time_step
                )
                
    def update_performance(self, cpu_usage: float, memory_usage: float, execution_time: float):
        """Update the dashboard with performance metrics."""
        if not self.simulation_running:
            return
            
        self.dashboard.add_performance_update(cpu_usage, memory_usage, execution_time)


# Utility function for quick dashboard creation
def create_dashboard(port: int = 8050) -> RealTimeDashboard:
    """Create and return a real-time dashboard instance."""
    return RealTimeDashboard(port=port)


if __name__ == "__main__":
    # Example usage
    dashboard = RealTimeDashboard()
    monitor = SimulationMonitor(dashboard)
    
    # Simulate some data updates
    def simulate_data():
        for i in range(100):
            if monitor.simulation_running:
                # Simulate flow rates
                monitor.update_simulation_step(i, {
                    'Catchment1': {'outflow': np.random.normal(10, 2)},
                    'Catchment2': {'outflow': np.random.normal(15, 3)}
                })
                
                # Simulate performance metrics
                monitor.update_performance(
                    cpu_usage=np.random.uniform(20, 80),
                    memory_usage=np.random.uniform(100, 500),
                    execution_time=i * 0.1
                )
                
                time.sleep(1)
    
    # Start monitoring and simulation
    monitor.start_monitoring()
    
    # Start simulation in background thread
    sim_thread = threading.Thread(target=simulate_data)
    sim_thread.daemon = True
    sim_thread.start()
    
    # Run dashboard
    dashboard.run()

