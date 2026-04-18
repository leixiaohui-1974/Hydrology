"""Common utilities and components for the Hydrology framework.

This module provides shared functionality including configuration management,
error handling, performance monitoring, and base components.
"""

# Import core components
from .config_parser import ConfigParser
from .error_handler import (
    HydrologyError,
    ValidationError,
    ComputationError,
    DataError,
    ConfigurationError,
    error_handler,
    handle_errors,
    validate_input
)
from .base_model import BaseModelComponent
from .controller import SimulationController as Controller

# Import performance monitoring components
try:
    from .performance_monitor import (
        PerformanceMonitor,
        PerformanceTimer,
        MemoryProfiler,
        ResourceMonitor,
        PerformanceMetrics,
        TimingResult,
        performance_monitor,
        get_global_monitor,
        set_global_monitor
    )
    PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError as e:
    PERFORMANCE_MONITORING_AVAILABLE = False
    _performance_import_error = str(e)

# Import performance dashboard (optional)
try:
    from .performance_dashboard import (
        PerformanceDashboard,
        StaticReportGenerator,
        create_dashboard
    )
    PERFORMANCE_DASHBOARD_AVAILABLE = True
except ImportError as e:
    PERFORMANCE_DASHBOARD_AVAILABLE = False
    _dashboard_import_error = str(e)

# Import security components
try:
    from .security import (
        InputValidator,
        DataEncryption,
        PasswordManager,
        User,
        UserManager,
        SessionManager,
        SecurityManager,
        setup_security,
        get_security_manager,
        require_permission,
        require_role
    )
    from .security_audit import (
        SecurityEvent,
        SecurityEventType,
        SecurityEventSeverity,
        SecurityAuditLogger,
        SecurityMonitor,
        SecurityAuditManager
    )
    SECURITY_AVAILABLE = True
except ImportError as e:
    SECURITY_AVAILABLE = False
    _security_import_error = str(e)

# Version information
__version__ = '1.0.0'
__author__ = 'Hydrology Framework Team'

# Export all public components
__all__ = [
    # Core components
    'ConfigParser',
    'HydrologyError',
    'ValidationError', 
    'ComputationError',
    'DataError',
    'ConfigurationError',
    'error_handler',
    'handle_errors',
    'validate_input',
    'BaseModelComponent',
    'Controller',
    
    # Performance monitoring (if available)
    'PerformanceMonitor',
    'PerformanceTimer',
    'MemoryProfiler',
    'ResourceMonitor',
    'PerformanceMetrics',
    'TimingResult',
    'performance_monitor',
    'get_global_monitor',
    'set_global_monitor',
    
    # Performance dashboard (if available)
    'PerformanceDashboard',
    'StaticReportGenerator',
    'create_dashboard',
    
    # Security components (if available)
    'InputValidator',
    'DataEncryption',
    'PasswordManager',
    'User',
    'UserManager',
    'SessionManager',
    'SecurityManager',
    'setup_security',
    'get_security_manager',
    'require_permission',
    'require_role',
    'SecurityEvent',
    'SecurityEventType',
    'SecurityEventSeverity',
    'SecurityAuditLogger',
    'SecurityMonitor',
    'SecurityAuditManager',
    
    # Utility functions
    'setup_performance_monitoring',
    'setup_security_system',
    'get_system_info',
    'check_dependencies'
]

# Remove unavailable components from __all__
if not PERFORMANCE_MONITORING_AVAILABLE:
    performance_components = [
        'PerformanceMonitor', 'PerformanceTimer', 'MemoryProfiler',
        'ResourceMonitor', 'PerformanceMetrics', 'TimingResult',
        'performance_monitor', 'get_global_monitor', 'set_global_monitor'
    ]
    __all__ = [item for item in __all__ if item not in performance_components]

if not PERFORMANCE_DASHBOARD_AVAILABLE:
    dashboard_components = [
        'PerformanceDashboard', 'StaticReportGenerator', 'create_dashboard'
    ]
    __all__ = [item for item in __all__ if item not in dashboard_components]

if not SECURITY_AVAILABLE:
    security_components = [
        'InputValidator', 'DataEncryption', 'PasswordManager', 'User',
        'UserManager', 'SessionManager', 'SecurityManager', 'setup_security',
        'get_security_manager', 'require_permission', 'require_role',
        'SecurityEvent', 'SecurityEventType', 'SecurityEventSeverity',
        'SecurityAuditLogger', 'SecurityMonitor', 'SecurityAuditManager',
        'setup_security_system'
    ]
    __all__ = [item for item in __all__ if item not in security_components]


def setup_performance_monitoring(config_file: str = None, 
                               auto_start: bool = True,
                               enable_dashboard: bool = False,
                               dashboard_port: int = 5000) -> dict:
    """Setup performance monitoring with optional configuration.
    
    Args:
        config_file: Path to performance configuration file
        auto_start: Whether to start monitoring automatically
        enable_dashboard: Whether to start the web dashboard
        dashboard_port: Port for the web dashboard
    
    Returns:
        Dictionary containing monitoring components
    """
    result = {
        'monitor': None,
        'dashboard': None,
        'config': None,
        'status': 'failed'
    }
    
    if not PERFORMANCE_MONITORING_AVAILABLE:
        result['error'] = f"Performance monitoring not available: {_performance_import_error}"
        return result
    
    try:
        # Load configuration if provided
        config = None
        if config_file:
            try:
                config_parser = ConfigParser()
                config = config_parser.load_config(config_file)
                result['config'] = config
            except Exception as e:
                print(f"Warning: Could not load performance config: {e}")
        
        # Create performance monitor
        monitor_kwargs = {}
        if config and 'resource_monitoring' in config:
            resource_config = config['resource_monitoring']
            monitor_kwargs.update({
                'auto_start_resource_monitoring': resource_config.get('auto_start', True),
                'resource_monitoring_interval': resource_config.get('interval_seconds', 1.0)
            })
        
        if config and 'logging' in config and config['logging'].get('enabled', True):
            monitor_kwargs['log_file'] = config['logging'].get('log_file', 'logs/performance.log')
        
        monitor = PerformanceMonitor(**monitor_kwargs)
        
        # Set thresholds if configured
        if config and 'thresholds' in config:
            monitor.set_thresholds(**config['thresholds'])
        
        # Start monitoring if requested
        if auto_start:
            monitor.start_monitoring()
        
        result['monitor'] = monitor
        set_global_monitor(monitor)
        
        # Setup dashboard if requested
        if enable_dashboard and PERFORMANCE_DASHBOARD_AVAILABLE:
            try:
                dashboard = create_dashboard(monitor, port=dashboard_port)
                dashboard.start(threaded=True)
                result['dashboard'] = dashboard
                print(f"Performance dashboard available at: {dashboard.get_url()}")
            except Exception as e:
                print(f"Warning: Could not start dashboard: {e}")
        elif enable_dashboard and not PERFORMANCE_DASHBOARD_AVAILABLE:
            print(f"Warning: Dashboard not available: {_dashboard_import_error}")
        
        result['status'] = 'success'
        print("Performance monitoring setup completed successfully")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"Error setting up performance monitoring: {e}")
    
    return result


def get_system_info() -> dict:
    """Get basic system information.
    
    Returns:
        Dictionary containing system information
    """
    import platform
    import sys
    
    info = {
        'platform': platform.platform(),
        'system': platform.system(),
        'processor': platform.processor(),
        'python_version': sys.version,
        'python_executable': sys.executable,
    }
    
    # Add memory information if psutil is available
    try:
        import psutil
        memory = psutil.virtual_memory()
        info.update({
            'total_memory_gb': memory.total / (1024**3),
            'available_memory_gb': memory.available / (1024**3),
            'cpu_count': psutil.cpu_count(),
            'cpu_count_logical': psutil.cpu_count(logical=True)
        })
    except ImportError:
        pass
    
    # Add GPU information if available
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            info['gpu_info'] = [
                {
                    'name': gpu.name,
                    'memory_total_mb': gpu.memoryTotal,
                    'driver_version': gpu.driver
                }
                for gpu in gpus
            ]
    except ImportError:
        pass
    
    return info


def setup_security_system(config_file: str = None,
                         auto_start_audit: bool = True,
                         enable_monitoring: bool = True) -> dict:
    """Setup security system with optional configuration.
    
    Args:
        config_file: Path to security configuration file
        auto_start_audit: Whether to start audit logging automatically
        enable_monitoring: Whether to enable security monitoring
    
    Returns:
        Dictionary containing security components
    """
    result = {
        'security_manager': None,
        'config': None,
        'status': 'failed'
    }
    
    if not SECURITY_AVAILABLE:
        result['error'] = f"Security system not available: {_security_import_error}"
        return result
    
    try:
        # Load configuration if provided
        config = None
        if config_file:
            try:
                from ..config.security_config import SecurityConfig
                config = SecurityConfig(config_file)
                result['config'] = config
            except Exception as e:
                print(f"Warning: Could not load security config: {e}")
        
        # Create security manager
        manager_config = {}
        if config:
            manager_config = config.to_dict()
        
        # Override with function parameters
        if 'audit' not in manager_config:
            manager_config['audit'] = {}
        manager_config['audit']['auto_start'] = auto_start_audit
        manager_config['audit']['enable_monitoring'] = enable_monitoring
        
        # Setup security system
        security_manager = setup_security(manager_config)
        result['security_manager'] = security_manager
        
        result['status'] = 'success'
        print("Security system setup completed successfully")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"Error setting up security system: {e}")
    
    return result


def check_dependencies() -> dict:
    """Check availability of optional dependencies.
    
    Returns:
        Dictionary showing which dependencies are available
    """
    dependencies = {
        'core': {
            'numpy': False,
            'pandas': False,
            'yaml': False
        },
        'performance': {
            'psutil': False,
            'memory_profiler': False
        },
        'dashboard': {
            'flask': False,
            'plotly': False
        },
        'security': {
            'cryptography': False,
            'bcrypt': False,
            'pyjwt': False
        },
        'testing': {
            'pytest': False,
            'pytest_cov': False,
            'pytest_benchmark': False
        },
        'gpu': {
            'GPUtil': False
        }
    }
    
    # Check each dependency
    for category, deps in dependencies.items():
        for dep_name in deps.keys():
            try:
                __import__(dep_name)
                dependencies[category][dep_name] = True
            except ImportError:
                pass
    
    # Special cases for renamed imports
    try:
        import yaml
        dependencies['core']['yaml'] = True
    except ImportError:
        pass
    
    return dependencies