"""RESTful API module for Hydrology Framework.

This module provides standardized REST API endpoints for accessing
hydrology modeling functionality.
"""

from .app import create_app, HydrologyAPI
from .routes import api_bp
from .models import APIResponse, ErrorResponse
from .auth import require_auth, generate_token

__all__ = [
    'create_app',
    'HydrologyAPI', 
    'api_bp',
    'APIResponse',
    'ErrorResponse',
    'require_auth',
    'generate_token'
]

__version__ = '1.0.0'