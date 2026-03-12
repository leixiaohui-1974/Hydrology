"""API routes for the Hydrology Framework REST API.

This module defines all REST API endpoints for accessing hydrology
modeling functionality.
"""

import os
import uuid
import time
import threading
from datetime import datetime
from typing import Dict, Any, List

try:
    from flask import Blueprint, request, jsonify, current_app
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Blueprint = None

# Add parent directory to path for imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.controller import SimulationController
from common.config_parser import ConfigParser
from common.performance_monitor import get_global_monitor
from .models import (
    APIResponse, ErrorResponse, SimulationRequest, SimulationResponse,
    ModelInfo, DatasetInfo, HealthStatus, PaginatedResponse,
    ValidationError, validate_simulation_request,
    create_success_response, create_error_response
)
from .auth import require_auth, require_role, require_permission, generate_token

# Create blueprint
api_bp = Blueprint('api', __name__)

# Global simulation storage (in production, use Redis or database)
simulations: Dict[str, Dict[str, Any]] = {}
simulation_lock = threading.Lock()


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Get system information
        monitor = get_global_monitor()
        uptime = time.time() - getattr(current_app, 'start_time', time.time())
        
        # Check dependencies
        dependencies = {
            'numpy': 'available',
            'pandas': 'available', 
            'flask': 'available' if FLASK_AVAILABLE else 'unavailable'
        }
        
        try:
            import numpy
            dependencies['numpy'] = 'available'
        except ImportError:
            dependencies['numpy'] = 'unavailable'
        
        try:
            import pandas
            dependencies['pandas'] = 'available'
        except ImportError:
            dependencies['pandas'] = 'unavailable'
        
        # Determine overall status
        status = 'healthy'
        if any(dep == 'unavailable' for dep in dependencies.values()):
            status = 'degraded'
        
        health_status = HealthStatus(
            status=status,
            version='1.0.0',
            uptime=uptime,
            dependencies=dependencies,
            memory_usage=getattr(monitor, 'get_memory_usage', lambda: {'used': 0, 'total': 0})() if monitor else None
        )
        
        return jsonify(create_success_response(
            data=health_status.to_dict(),
            message="Service is running"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Health Check Failed",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/auth/login', methods=['POST'])
def login():
    """User authentication endpoint."""
    try:
        data = request.get_json(silent=True, force=True)
        if not data:
            return jsonify(create_error_response(
                error="Invalid Request",
                message="JSON data required",
                status_code=400
            ).to_dict()), 400
        
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify(create_error_response(
                error="Missing Credentials",
                message="Username and password required",
                status_code=400
            ).to_dict()), 400
        
        token = generate_token(username, password)
        if not token:
            return jsonify(create_error_response(
                error="Authentication Failed",
                message="Invalid username or password",
                status_code=401
            ).to_dict()), 401
        
        return jsonify(create_success_response(
            data={'token': token, 'token_type': 'Bearer'},
            message="Authentication successful"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Login Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/models', methods=['GET'])
@require_auth
def list_models():
    """List available hydrology models."""
    try:
        models = [
            ModelInfo(
                name="XAJ",
                version="1.0",
                description="Xinanjiang rainfall-runoff model",
                parameters=[
                    {"name": "K", "type": "float", "description": "Evapotranspiration coefficient"},
                    {"name": "B", "type": "float", "description": "Tension water capacity exponent"},
                    {"name": "IM", "type": "float", "description": "Impervious area fraction"}
                ],
                inputs=[{"name": "rainfall", "type": "timeseries", "required": True}],
                outputs=[{"name": "flow", "type": "timeseries", "unit": "m3/s"}]
            ).to_dict(),
            ModelInfo(
                name="HYMOD",
                version="1.0",
                description="HYMOD conceptual rainfall-runoff model",
                parameters=[
                    {"name": "cmax", "type": "float", "description": "Maximum storage capacity"},
                    {"name": "bexp", "type": "float", "description": "Degree of spatial variability"},
                    {"name": "alpha", "type": "float", "description": "Quick flow coefficient"}
                ],
                inputs=[{"name": "rainfall", "type": "timeseries", "required": True}],
                outputs=[{"name": "flow", "type": "timeseries", "unit": "m3/s"}]
            ).to_dict()
        ]
        
        return jsonify(create_success_response(
            data=models,
            message="Models retrieved successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Models Retrieval Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/models/<model_name>', methods=['GET'])
@require_auth
def get_model_info(model_name: str):
    """Get detailed information about a specific model."""
    try:
        # This would typically query a model registry
        model_configs = {
            'xaj': {
                'name': 'XAJ',
                'description': 'Xinanjiang rainfall-runoff model',
                'config_template': {
                    'model_type': 'xaj',
                    'parameters': {
                        'K': 0.5,
                        'B': 0.3,
                        'IM': 0.01
                    }
                }
            },
            'hymod': {
                'name': 'HYMOD',
                'description': 'HYMOD conceptual model',
                'config_template': {
                    'model_type': 'hymod',
                    'parameters': {
                        'cmax': 400.0,
                        'bexp': 2.0,
                        'alpha': 0.8
                    }
                }
            }
        }
        
        if model_name.lower() not in model_configs:
            return jsonify(create_error_response(
                error="Model Not Found",
                message=f"Model '{model_name}' not found",
                status_code=404
            ).to_dict()), 404
        
        return jsonify(create_success_response(
            data=model_configs[model_name.lower()],
            message="Model information retrieved successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Model Info Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/simulations', methods=['POST'])
@require_auth
@require_permission('run_simulation')
def create_simulation():
    """Create and run a new simulation."""
    try:
        data = request.get_json(silent=True, force=True)
        if not data:
            return jsonify(create_error_response(
                error="Invalid Request",
                message="JSON data required",
                status_code=400
            ).to_dict()), 400
        
        # Validate request
        sim_request = validate_simulation_request(data)
        
        # Generate simulation ID
        simulation_id = str(uuid.uuid4())
        
        # Store simulation info
        with simulation_lock:
            simulations[simulation_id] = {
                'id': simulation_id,
                'status': 'queued',
                'request': sim_request,
                'created_at': datetime.utcnow().isoformat(),
                'progress': 0.0
            }
        
        # Start simulation in background if async
        if sim_request.async_execution:
            thread = threading.Thread(
                target=_run_simulation_async,
                args=(simulation_id, sim_request)
            )
            thread.daemon = True
            thread.start()
            
            response = SimulationResponse(
                simulation_id=simulation_id,
                status='queued',
                start_time=datetime.utcnow().isoformat()
            )
        else:
            # Run synchronously
            response = _run_simulation_sync(simulation_id, sim_request)
        
        return jsonify(create_success_response(
            data=response.to_dict(),
            message="Simulation created successfully"
        ).to_dict()), 201
    
    except ValidationError as e:
        return jsonify(create_error_response(
            error="Validation Error",
            message=e.message,
            status_code=400,
            details=e.to_dict()
        ).to_dict()), 400

    except Exception as e:
        return jsonify(create_error_response(
            error="Simulation Creation Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/simulations/<simulation_id>', methods=['GET'])
@require_auth
def get_simulation_status(simulation_id: str):
    """Get simulation status and results."""
    try:
        with simulation_lock:
            if simulation_id not in simulations:
                return jsonify(create_error_response(
                    error="Simulation Not Found",
                    message=f"Simulation '{simulation_id}' not found",
                    status_code=404
                ).to_dict()), 404
            
            sim_data = simulations[simulation_id]
        
        response = SimulationResponse(
            simulation_id=simulation_id,
            status=sim_data['status'],
            results=sim_data.get('results'),
            progress=sim_data.get('progress'),
            error_message=sim_data.get('error_message'),
            start_time=sim_data.get('start_time'),
            end_time=sim_data.get('end_time')
        )
        
        return jsonify(create_success_response(
            data=response.to_dict(),
            message="Simulation status retrieved successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Simulation Status Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/simulations', methods=['GET'])
@require_auth
def list_simulations():
    """List user's simulations with pagination."""
    try:
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 10)), 100)
        
        with simulation_lock:
            all_sims = list(simulations.values())
        
        # Simple pagination
        total = len(all_sims)
        start = (page - 1) * per_page
        end = start + per_page
        items = all_sims[start:end]
        
        # Convert to response format
        sim_list = []
        for sim in items:
            sim_list.append({
                'id': sim['id'],
                'status': sim['status'],
                'created_at': sim['created_at'],
                'progress': sim.get('progress', 0.0)
            })
        
        paginated = PaginatedResponse(
            items=sim_list,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page,
            has_next=end < total,
            has_prev=page > 1
        )
        
        return jsonify(create_success_response(
            data=paginated.to_dict(),
            message="Simulations retrieved successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Simulations List Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/simulations/<simulation_id>', methods=['DELETE'])
@require_auth
@require_permission('delete_simulation')
def delete_simulation(simulation_id: str):
    """Delete a simulation."""
    try:
        with simulation_lock:
            if simulation_id not in simulations:
                return jsonify(create_error_response(
                    error="Simulation Not Found",
                    message=f"Simulation '{simulation_id}' not found",
                    status_code=404
                ).to_dict()), 404
            
            del simulations[simulation_id]
        
        return jsonify(create_success_response(
            message="Simulation deleted successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Simulation Deletion Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


@api_bp.route('/datasets', methods=['GET'])
@require_auth
def list_datasets():
    """List available datasets."""
    try:
        # This would typically query a data catalog
        datasets = [
            DatasetInfo(
                name="sample_rainfall",
                description="Sample rainfall time series data",
                format="CSV",
                size=1024,
                columns=["timestamp", "rainfall_mm"]
            ).to_dict(),
            DatasetInfo(
                name="sample_flow",
                description="Sample flow observation data",
                format="CSV",
                size=2048,
                columns=["timestamp", "flow_m3s"]
            ).to_dict()
        ]
        
        return jsonify(create_success_response(
            data=datasets,
            message="Datasets retrieved successfully"
        ).to_dict())
    
    except Exception as e:
        return jsonify(create_error_response(
            error="Datasets Retrieval Error",
            message=str(e),
            status_code=500
        ).to_dict()), 500


def _run_simulation_async(simulation_id: str, sim_request: SimulationRequest):
    """Run simulation asynchronously."""
    try:
        with simulation_lock:
            simulations[simulation_id]['status'] = 'running'
            simulations[simulation_id]['start_time'] = datetime.utcnow().isoformat()
        
        # Simulate progress updates
        for progress in [0.2, 0.4, 0.6, 0.8, 1.0]:
            time.sleep(1)  # Simulate work
            with simulation_lock:
                simulations[simulation_id]['progress'] = progress
        
        results = _build_mock_results(sim_request)
        
        with simulation_lock:
            simulations[simulation_id]['status'] = 'completed'
            simulations[simulation_id]['results'] = results
            simulations[simulation_id]['end_time'] = datetime.utcnow().isoformat()
    
    except Exception as e:
        with simulation_lock:
            simulations[simulation_id]['status'] = 'failed'
            simulations[simulation_id]['error_message'] = str(e)
            simulations[simulation_id]['end_time'] = datetime.utcnow().isoformat()


def _run_simulation_sync(simulation_id: str, sim_request: SimulationRequest) -> SimulationResponse:
    """Run simulation synchronously."""
    try:
        with simulation_lock:
            simulations[simulation_id]['status'] = 'running'
            simulations[simulation_id]['start_time'] = datetime.utcnow().isoformat()
        
        # Mock simulation execution
        time.sleep(2)  # Simulate work
        
        results = _build_mock_results(sim_request)
        
        end_time = datetime.utcnow().isoformat()
        
        with simulation_lock:
            simulations[simulation_id]['status'] = 'completed'
            simulations[simulation_id]['results'] = results
            simulations[simulation_id]['end_time'] = end_time
            simulations[simulation_id]['progress'] = 1.0
        
        return SimulationResponse(
            simulation_id=simulation_id,
            status='completed',
            results=results,
            progress=1.0,
            start_time=simulations[simulation_id]['start_time'],
            end_time=end_time
        )
    
    except Exception as e:
        end_time = datetime.utcnow().isoformat()
        
        with simulation_lock:
            simulations[simulation_id]['status'] = 'failed'
            simulations[simulation_id]['error_message'] = str(e)
            simulations[simulation_id]['end_time'] = end_time
        
        return SimulationResponse(
            simulation_id=simulation_id,
            status='failed',
            error_message=str(e),
            start_time=simulations[simulation_id]['start_time'],
            end_time=end_time
        )


def _extract_rainfall_series(sim_request: SimulationRequest) -> List[float]:
    """Extract numeric rainfall values from supported simulation request shapes."""
    rainfall = None

    if isinstance(sim_request.data_sources, dict):
        rainfall = sim_request.data_sources.get('rainfall')

    if rainfall is None and isinstance(sim_request.config, dict):
        input_data = sim_request.config.get('input_data')
        if isinstance(input_data, dict):
            rainfall = input_data.get('rainfall')

    if rainfall is None and isinstance(sim_request.config, dict):
        rainfall = sim_request.config.get('rainfall')

    if rainfall is None:
        return []

    if isinstance(rainfall, (int, float)):
        return [float(rainfall)]

    if isinstance(rainfall, (list, tuple)):
        numeric_rainfall = []
        for value in rainfall:
            if isinstance(value, (int, float)):
                numeric_rainfall.append(float(value))
        return numeric_rainfall

    return []


def _build_mock_results(sim_request: SimulationRequest) -> Dict[str, Any]:
    """Build mock simulation results using request rainfall when available."""
    rainfall = _extract_rainfall_series(sim_request)
    if rainfall:
        flow = [value * 0.8 for value in rainfall]
        timestamps = [f'2023-01-01T{hour:02d}:00:00Z' for hour in range(len(rainfall))]
        return {
            'flow': flow,
            'timestamps': timestamps
        }

    return {
        'flow': [1.2, 1.5, 2.1, 1.8, 1.3],
        'timestamps': ['2023-01-01T00:00:00Z', '2023-01-01T01:00:00Z',
                       '2023-01-01T02:00:00Z', '2023-01-01T03:00:00Z',
                       '2023-01-01T04:00:00Z']
    }
