"""Performance monitoring dashboard for the Hydrology framework.

This module provides a web-based dashboard for real-time performance monitoring
with interactive charts and metrics visualization.
"""
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import logging

try:
    from flask import Flask, render_template_string, jsonify, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None

try:
    import plotly.graph_objs as go
    import plotly.utils
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    go = None

from .performance_monitor import PerformanceMonitor, get_global_monitor


class PerformanceDashboard:
    """Web-based performance monitoring dashboard."""
    
    def __init__(self, 
                 monitor: Optional[PerformanceMonitor] = None,
                 host: str = '127.0.0.1',
                 port: int = 5000,
                 debug: bool = False) -> None:
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the performance dashboard. Install with: pip install flask")
        
        self.monitor: PerformanceMonitor = monitor or get_global_monitor()
        self.host: str = host
        self.port: int = port
        self.debug: bool = debug
        self.app: Flask = Flask(__name__)
        self.app.secret_key = 'hydrology_performance_dashboard'
        
        # Dashboard state
        self.is_running: bool = False
        self.server_thread: Optional[threading.Thread] = None
        
        # Setup routes
        self._setup_routes()
        
        # Setup logging
        self.logger: logging.Logger = logging.getLogger('performance_dashboard')
    
    def _setup_routes(self) -> None:
        """Setup Flask routes for the dashboard."""
        
        @self.app.route('/')
        def index():
            """Main dashboard page."""
            return render_template_string(self._get_dashboard_template())
        
        @self.app.route('/api/metrics')
        def get_metrics():
            """API endpoint for current metrics."""
            current_metrics = self.monitor.resource_monitor.get_current_metrics()
            if current_metrics:
                return jsonify({
                    'timestamp': current_metrics.timestamp.isoformat(),
                    'cpu_percent': current_metrics.cpu_percent,
                    'memory_mb': current_metrics.memory_mb,
                    'memory_percent': current_metrics.memory_percent,
                    'disk_io_read_mb': current_metrics.disk_io_read_mb,
                    'disk_io_write_mb': current_metrics.disk_io_write_mb,
                    'network_sent_mb': current_metrics.network_sent_mb,
                    'network_recv_mb': current_metrics.network_recv_mb,
                    'gpu_memory_mb': current_metrics.gpu_memory_mb,
                    'gpu_utilization': current_metrics.gpu_utilization
                })
            return jsonify({})
        
        @self.app.route('/api/metrics/history')
        def get_metrics_history():
            """API endpoint for metrics history."""
            duration_minutes = request.args.get('duration', 10, type=int)
            
            # Get metrics from history
            cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
            history = [
                {
                    'timestamp': m.timestamp.isoformat(),
                    'cpu_percent': m.cpu_percent,
                    'memory_mb': m.memory_mb,
                    'memory_percent': m.memory_percent,
                    'disk_io_read_mb': m.disk_io_read_mb,
                    'disk_io_write_mb': m.disk_io_write_mb,
                    'network_sent_mb': m.network_sent_mb,
                    'network_recv_mb': m.network_recv_mb,
                    'gpu_memory_mb': m.gpu_memory_mb,
                    'gpu_utilization': m.gpu_utilization
                }
                for m in self.monitor.resource_monitor.metrics_history
                if m.timestamp >= cutoff_time
            ]
            
            return jsonify(history)
        
        @self.app.route('/api/timing')
        def get_timing_results():
            """API endpoint for timing results."""
            limit = request.args.get('limit', 50, type=int)
            
            recent_results = self.monitor.timing_results[-limit:]
            timing_data = [
                {
                    'name': r.name,
                    'duration_seconds': r.duration_seconds,
                    'start_time': r.start_time.isoformat(),
                    'end_time': r.end_time.isoformat(),
                    'memory_before_mb': r.memory_before_mb,
                    'memory_after_mb': r.memory_after_mb,
                    'memory_peak_mb': r.memory_peak_mb,
                    'cpu_time_seconds': r.cpu_time_seconds
                }
                for r in recent_results
            ]
            
            return jsonify(timing_data)
        
        @self.app.route('/api/alerts')
        def get_alerts():
            """API endpoint for recent alerts."""
            limit = request.args.get('limit', 20, type=int)
            
            recent_alerts = self.monitor.alerts[-limit:]
            alerts_data = [
                {
                    'timestamp': a['timestamp'].isoformat(),
                    'message': a['message'],
                    'operation': a.get('result', {}).get('name', 'Unknown') if 'result' in a else 'System'
                }
                for a in recent_alerts
            ]
            
            return jsonify(alerts_data)
        
        @self.app.route('/api/report')
        def get_performance_report():
            """API endpoint for performance report."""
            report = self.monitor.get_performance_report()
            return jsonify(report)
        
        @self.app.route('/api/custom_metrics')
        def get_custom_metrics():
            """API endpoint for custom metrics."""
            metrics_data = {}
            
            for name, values in self.monitor.custom_metrics.items():
                if values:
                    recent_values = values[-100:]  # Last 100 values
                    metrics_data[name] = [
                        {
                            'timestamp': v['timestamp'].isoformat(),
                            'value': v['value'],
                            'metadata': v['metadata']
                        }
                        for v in recent_values
                    ]
            
            return jsonify(metrics_data)
        
        @self.app.route('/api/charts/cpu_memory')
        def get_cpu_memory_chart():
            """Generate CPU and memory usage chart."""
            if not PLOTLY_AVAILABLE:
                return jsonify({'error': 'Plotly not available'})
            
            duration_minutes = request.args.get('duration', 10, type=int)
            cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
            
            # Filter recent metrics
            recent_metrics = [
                m for m in self.monitor.resource_monitor.metrics_history
                if m.timestamp >= cutoff_time
            ]
            
            if not recent_metrics:
                return jsonify({'error': 'No data available'})
            
            # Prepare data
            timestamps = [m.timestamp for m in recent_metrics]
            cpu_values = [m.cpu_percent for m in recent_metrics]
            memory_values = [m.memory_mb for m in recent_metrics]
            
            # Create traces
            cpu_trace = go.Scatter(
                x=timestamps,
                y=cpu_values,
                mode='lines',
                name='CPU Usage (%)',
                line=dict(color='#ff6b6b')
            )
            
            memory_trace = go.Scatter(
                x=timestamps,
                y=memory_values,
                mode='lines',
                name='Memory Usage (MB)',
                yaxis='y2',
                line=dict(color='#4ecdc4')
            )
            
            # Create layout
            layout = go.Layout(
                title='CPU and Memory Usage',
                xaxis=dict(title='Time'),
                yaxis=dict(title='CPU Usage (%)', side='left'),
                yaxis2=dict(title='Memory Usage (MB)', side='right', overlaying='y'),
                hovermode='x unified'
            )
            
            # Create figure
            fig = go.Figure(data=[cpu_trace, memory_trace], layout=layout)
            
            return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
        
        @self.app.route('/api/charts/timing_distribution')
        def get_timing_distribution_chart():
            """Generate timing distribution chart."""
            if not PLOTLY_AVAILABLE:
                return jsonify({'error': 'Plotly not available'})
            
            if not self.monitor.timing_results:
                return jsonify({'error': 'No timing data available'})
            
            # Group by operation name
            operation_times = {}
            for result in self.monitor.timing_results[-100:]:  # Last 100 operations
                if result.name not in operation_times:
                    operation_times[result.name] = []
                operation_times[result.name].append(result.duration_seconds)
            
            # Create box plot
            traces = []
            for name, times in operation_times.items():
                trace = go.Box(
                    y=times,
                    name=name,
                    boxpoints='outliers'
                )
                traces.append(trace)
            
            layout = go.Layout(
                title='Operation Duration Distribution',
                yaxis=dict(title='Duration (seconds)'),
                xaxis=dict(title='Operation')
            )
            
            fig = go.Figure(data=traces, layout=layout)
            
            return jsonify(plotly.utils.PlotlyJSONEncoder().encode(fig))
    
    def _get_dashboard_template(self) -> str:
        """Get the HTML template for the dashboard."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hydrology Performance Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            color: #333;
        }
        .metric-label {
            color: #666;
            margin-top: 5px;
        }
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .alerts-container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-height: 400px;
            overflow-y: auto;
        }
        .alert-item {
            padding: 10px;
            margin: 5px 0;
            border-left: 4px solid #ff6b6b;
            background-color: #fff5f5;
            border-radius: 5px;
        }
        .alert-time {
            font-size: 0.8em;
            color: #666;
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-good { background-color: #4caf50; }
        .status-warning { background-color: #ff9800; }
        .status-critical { background-color: #f44336; }
        .refresh-button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin: 10px;
        }
        .refresh-button:hover {
            background: #5a6fd8;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🌊 Hydrology Performance Dashboard</h1>
        <p>Real-time monitoring of system performance and resource usage</p>
        <button class="refresh-button" onclick="refreshData()">🔄 Refresh Data</button>
        <button class="refresh-button" onclick="toggleAutoRefresh()">⏱️ Auto Refresh: <span id="auto-refresh-status">ON</span></button>
    </div>

    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-value" id="cpu-usage">--</div>
            <div class="metric-label">CPU Usage (%)</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" id="memory-usage">--</div>
            <div class="metric-label">Memory Usage (MB)</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" id="active-operations">--</div>
            <div class="metric-label">Active Operations</div>
        </div>
        <div class="metric-card">
            <div class="metric-value" id="total-alerts">--</div>
            <div class="metric-label">Total Alerts</div>
        </div>
    </div>

    <div class="chart-container">
        <div id="cpu-memory-chart" style="height: 400px;"></div>
    </div>

    <div class="chart-container">
        <div id="timing-chart" style="height: 400px;"></div>
    </div>

    <div class="alerts-container">
        <h3>Recent Alerts</h3>
        <div id="alerts-list"></div>
    </div>

    <script>
        let autoRefresh = true;
        let refreshInterval;

        function updateMetrics() {
            $.get('/api/metrics', function(data) {
                if (data.cpu_percent !== undefined) {
                    $('#cpu-usage').text(data.cpu_percent.toFixed(1));
                    updateStatusIndicator('cpu-usage', data.cpu_percent, 80);
                }
                if (data.memory_mb !== undefined) {
                    $('#memory-usage').text(data.memory_mb.toFixed(0));
                    updateStatusIndicator('memory-usage', data.memory_mb, 1000);
                }
            });

            $.get('/api/timing', function(data) {
                $('#active-operations').text(data.length);
            });

            $.get('/api/alerts', function(data) {
                $('#total-alerts').text(data.length);
                updateAlertsList(data);
            });
        }

        function updateStatusIndicator(elementId, value, threshold) {
            const element = $('#' + elementId);
            element.removeClass('status-good status-warning status-critical');
            
            if (value < threshold * 0.7) {
                element.addClass('status-good');
            } else if (value < threshold) {
                element.addClass('status-warning');
            } else {
                element.addClass('status-critical');
            }
        }

        function updateAlertsList(alerts) {
            const container = $('#alerts-list');
            container.empty();
            
            if (alerts.length === 0) {
                container.html('<p>No recent alerts</p>');
                return;
            }
            
            alerts.reverse().forEach(function(alert) {
                const alertDiv = $('<div class="alert-item"></div>');
                const time = new Date(alert.timestamp).toLocaleString();
                alertDiv.html(`
                    <div>${alert.message}</div>
                    <div class="alert-time">${time} - ${alert.operation}</div>
                `);
                container.append(alertDiv);
            });
        }

        function updateCharts() {
            // Update CPU/Memory chart
            $.get('/api/charts/cpu_memory', function(data) {
                if (data.error) {
                    $('#cpu-memory-chart').html('<p>Chart unavailable: ' + data.error + '</p>');
                } else {
                    Plotly.newPlot('cpu-memory-chart', JSON.parse(data));
                }
            });

            // Update timing distribution chart
            $.get('/api/charts/timing_distribution', function(data) {
                if (data.error) {
                    $('#timing-chart').html('<p>Chart unavailable: ' + data.error + '</p>');
                } else {
                    Plotly.newPlot('timing-chart', JSON.parse(data));
                }
            });
        }

        function refreshData() {
            updateMetrics();
            updateCharts();
        }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            $('#auto-refresh-status').text(autoRefresh ? 'ON' : 'OFF');
            
            if (autoRefresh) {
                startAutoRefresh();
            } else {
                clearInterval(refreshInterval);
            }
        }

        function startAutoRefresh() {
            refreshInterval = setInterval(function() {
                if (autoRefresh) {
                    updateMetrics();
                }
            }, 2000); // Update every 2 seconds
            
            // Update charts less frequently
            setInterval(function() {
                if (autoRefresh) {
                    updateCharts();
                }
            }, 10000); // Update every 10 seconds
        }

        // Initialize dashboard
        $(document).ready(function() {
            refreshData();
            startAutoRefresh();
        });
    </script>
</body>
</html>
        """
    
    def start(self, threaded: bool = True):
        """Start the dashboard server."""
        if self.is_running:
            self.logger.warning("Dashboard is already running")
            return
        
        self.is_running = True
        
        if threaded:
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True
            )
            self.server_thread.start()
            self.logger.info(f"Dashboard started at http://{self.host}:{self.port}")
        else:
            self._run_server()
    
    def _run_server(self):
        """Run the Flask server."""
        try:
            self.app.run(
                host=self.host,
                port=self.port,
                debug=self.debug,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            self.logger.error(f"Dashboard server error: {e}")
            self.is_running = False
    
    def stop(self):
        """Stop the dashboard server."""
        self.is_running = False
        if self.server_thread:
            self.logger.info("Dashboard server stopped")
    
    def get_url(self) -> str:
        """Get the dashboard URL."""
        return f"http://{self.host}:{self.port}"


class StaticReportGenerator:
    """Generate static HTML performance reports."""
    
    def __init__(self, monitor: Optional[PerformanceMonitor] = None):
        self.monitor = monitor or get_global_monitor()
    
    def generate_report(self, output_file: str, include_charts: bool = True):
        """Generate a static HTML performance report."""
        report_data = self.monitor.get_performance_report()
        
        html_content = self._generate_html_report(report_data, include_charts)
        
        # Write to file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _generate_html_report(self, report_data: Dict, include_charts: bool) -> str:
        """Generate HTML content for the report."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Basic report structure
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Hydrology Performance Report - {timestamp}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f9f9f9; border-radius: 5px; }}
        .alert {{ background: #ffe6e6; padding: 10px; margin: 5px 0; border-left: 4px solid #ff0000; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🌊 Hydrology Performance Report</h1>
        <p>Generated: {timestamp}</p>
    </div>
        """
        
        # Resource summary
        if 'resource_summary' in report_data:
            resource_data = report_data['resource_summary']
            html += """
    <div class="section">
        <h2>Resource Usage Summary</h2>
            """
            
            if 'cpu_percent' in resource_data:
                cpu_data = resource_data['cpu_percent']
                html += f"""
        <div class="metric">
            <h3>CPU Usage</h3>
            <p>Average: {cpu_data.get('mean', 0):.1f}%</p>
            <p>Maximum: {cpu_data.get('max', 0):.1f}%</p>
        </div>
                """
            
            if 'memory_mb' in resource_data:
                memory_data = resource_data['memory_mb']
                html += f"""
        <div class="metric">
            <h3>Memory Usage</h3>
            <p>Average: {memory_data.get('mean', 0):.1f} MB</p>
            <p>Maximum: {memory_data.get('max', 0):.1f} MB</p>
        </div>
                """
            
            html += "</div>"
        
        # Timing summary
        if 'timing_summary' in report_data:
            timing_data = report_data['timing_summary']
            html += f"""
    <div class="section">
        <h2>Operation Timing Summary</h2>
        <div class="metric">
            <p>Total Operations: {timing_data.get('total_operations', 0)}</p>
            <p>Total Time: {timing_data.get('total_time_seconds', 0):.2f} seconds</p>
            <p>Average Duration: {timing_data.get('average_duration_seconds', 0):.3f} seconds</p>
        </div>
    </div>
            """
        
        # Alerts
        if 'alerts' in report_data and report_data['alerts']:
            html += """
    <div class="section">
        <h2>Recent Alerts</h2>
            """
            
            for alert in report_data['alerts'][-10:]:  # Last 10 alerts
                html += f'<div class="alert">{alert["message"]} - {alert["timestamp"]}</div>'
            
            html += "</div>"
        
        # Recommendations
        if 'recommendations' in report_data and report_data['recommendations']:
            html += """
    <div class="section">
        <h2>Performance Recommendations</h2>
        <ul>
            """
            
            for rec in report_data['recommendations']:
                html += f"<li>{rec}</li>"
            
            html += """
        </ul>
    </div>
            """
        
        html += """
</body>
</html>
        """
        
        return html


def create_dashboard(monitor: Optional[PerformanceMonitor] = None,
                    host: str = '127.0.0.1',
                    port: int = 5000) -> PerformanceDashboard:
    """Create and return a performance dashboard instance."""
    return PerformanceDashboard(monitor, host, port)


if __name__ == '__main__':
    # Example usage
    print("Starting Performance Dashboard...")
    
    # Create monitor and dashboard
    monitor = PerformanceMonitor()
    dashboard = create_dashboard(monitor, port=5000)
    
    try:
        # Start dashboard
        dashboard.start(threaded=False)  # Run in main thread for example
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
        dashboard.stop()
        monitor.stop_monitoring()