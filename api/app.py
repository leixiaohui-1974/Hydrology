"""Main Flask application for Hydrology Framework REST API.

This module creates and configures the Flask application with all necessary
routes, middleware, and error handlers.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from flask import Flask, jsonify, request, g
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None
    CORS = None

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    LIMITER_AVAILABLE = True
except ImportError:
    LIMITER_AVAILABLE = False
    Limiter = None

# Add parent directory to path for imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.error_handler import HydrologyError, ValidationError, SecurityError
from common.security import get_security_manager
from .routes import api_bp
from .models import APIResponse, ErrorResponse


class HydrologyAPI:
    """Main API application class."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for the API. Install with: pip install flask flask-cors")
        
        self.config = config or {}
        self.app = None
        self.limiter = None
        self.security_manager = None
        
        # Setup logging
        self.logger = logging.getLogger('hydrology_api')
        
    def create_app(self) -> Flask:
        """Create and configure Flask application."""
        app = Flask(__name__)
        
        # Configuration
        app.config.update({
            'SECRET_KEY': self.config.get('secret_key', os.urandom(24)),
            'DEBUG': self.config.get('debug', False),
            'TESTING': self.config.get('testing', False),
            'JSON_SORT_KEYS': False,
            'JSONIFY_PRETTYPRINT_REGULAR': True
        })
        
        # Enable CORS
        if CORS:
            CORS(app, resources={
                r"/api/*": {
                    "origins": self.config.get('cors_origins', ['*']),
                    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                    "allow_headers": ["Content-Type", "Authorization"]
                }
            })
        
        # Rate limiting
        if LIMITER_AVAILABLE:
            self.limiter = Limiter(
                app,
                key_func=get_remote_address,
                default_limits=["1000 per hour", "100 per minute"]
            )
        
        # Initialize security
        try:
            self.security_manager = get_security_manager()
            if self._is_development_or_testing(app):
                self.security_manager.ensure_development_test_user()
        except Exception as e:
            self.logger.warning(f"Security manager initialization failed: {e}")
        
        # Register blueprints
        app.register_blueprint(api_bp, url_prefix='/api/v1')
        
        # Register error handlers
        self._register_error_handlers(app)
        
        # Register middleware
        self._register_middleware(app)
        
        self.app = app
        return app

    def _is_development_or_testing(self, app: Flask) -> bool:
        """Determine whether the app is running in development/testing mode."""
        mode = str(
            self.config.get('environment')
            or self.config.get('config_name')
            or self.config.get('mode')
            or os.environ.get('FLASK_ENV', '')
        ).lower()

        return bool(
            app.config.get('DEBUG')
            or app.config.get('TESTING')
            or mode in {'dev', 'development', 'test', 'testing'}
        )
    
    def _register_error_handlers(self, app: Flask):
        """Register error handlers."""
        
        @app.errorhandler(ValidationError)
        def handle_validation_error(error):
            return jsonify(ErrorResponse(
                error="Validation Error",
                message=str(error),
                status_code=400
            ).to_dict()), 400
        
        @app.errorhandler(SecurityError)
        def handle_security_error(error):
            return jsonify(ErrorResponse(
                error="Security Error",
                message=str(error),
                status_code=403
            ).to_dict()), 403
        
        @app.errorhandler(HydrologyError)
        def handle_hydrology_error(error):
            return jsonify(ErrorResponse(
                error="Hydrology Error",
                message=str(error),
                status_code=500
            ).to_dict()), 500
        
        @app.errorhandler(404)
        def handle_not_found(error):
            return jsonify(ErrorResponse(
                error="Not Found",
                message="The requested resource was not found",
                status_code=404
            ).to_dict()), 404
        
        @app.errorhandler(405)
        def handle_method_not_allowed(error):
            return jsonify(ErrorResponse(
                error="Method Not Allowed",
                message="The method is not allowed for the requested URL",
                status_code=405
            ).to_dict()), 405
        
        @app.errorhandler(500)
        def handle_internal_error(error):
            return jsonify(ErrorResponse(
                error="Internal Server Error",
                message="An internal server error occurred",
                status_code=500
            ).to_dict()), 500
    
    def _register_middleware(self, app: Flask):
        """Register middleware."""
        
        @app.before_request
        def before_request():
            """Execute before each request."""
            g.start_time = datetime.utcnow()
            
            # Log request
            self.logger.info(f"{request.method} {request.path} - {request.remote_addr}")
        
        @app.after_request
        def after_request(response):
            """Execute after each request."""
            # Calculate request duration
            if hasattr(g, 'start_time'):
                duration = (datetime.utcnow() - g.start_time).total_seconds()
                response.headers['X-Response-Time'] = f"{duration:.3f}s"
            
            # Add API version header
            response.headers['X-API-Version'] = '1.0.0'
            
            # Log response
            self.logger.info(f"Response: {response.status_code} - {response.content_length or 0} bytes")
            
            return response
    
    def run(self, host: str = '127.0.0.1', port: int = 8000, debug: bool = None):
        """Run the API server."""
        if not self.app:
            self.create_app()
        
        debug = debug if debug is not None else self.config.get('debug', False)
        
        self.logger.info(f"Starting Hydrology API server on {host}:{port}")
        self.app.run(host=host, port=port, debug=debug, threaded=True)


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    """Factory function to create Flask application."""
    api = HydrologyAPI(config)
    return api.create_app()


if __name__ == '__main__':
    # Development server
    app = create_app({'debug': True})
    app.run(host='127.0.0.1', port=8000)
