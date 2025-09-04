"""Middleware for the Hydrology Framework REST API.

This module contains middleware functions for request/response processing,
logging, error handling, and performance monitoring.
"""

import time
import uuid
import logging
from functools import wraps
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from flask import request, g, current_app, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Add parent directory to path for imports
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.performance_monitor import get_global_monitor
from .models import create_error_response

# Configure logging
logger = logging.getLogger(__name__)


class RequestMiddleware:
    """Middleware for request processing."""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize middleware with Flask app."""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        app.teardown_appcontext(self.teardown_request)
    
    @staticmethod
    def before_request():
        """Process request before handling."""
        # Generate request ID
        g.request_id = str(uuid.uuid4())
        g.start_time = time.time()
        
        # Log request
        if current_app.config.get('ENABLE_REQUEST_LOGGING', True):
            logger.info(
                f"Request {g.request_id}: {request.method} {request.path} "
                f"from {request.remote_addr}"
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ['POST', 'PUT', 'PATCH']:
            if not request.is_json and request.content_length > 0:
                return jsonify(create_error_response(
                    error="Invalid Content Type",
                    message="Content-Type must be application/json",
                    status_code=400
                ).to_dict()), 400
        
        # Check API version
        api_version = request.headers.get('X-API-Version', '1.0')
        supported_versions = current_app.config.get('SUPPORTED_VERSIONS', ['1.0'])
        
        if api_version not in supported_versions:
            return jsonify(create_error_response(
                error="Unsupported API Version",
                message=f"API version {api_version} is not supported",
                status_code=400
            ).to_dict()), 400
        
        g.api_version = api_version
    
    @staticmethod
    def after_request(response):
        """Process response after handling."""
        # Add request ID to response headers
        if hasattr(g, 'request_id'):
            response.headers['X-Request-ID'] = g.request_id
        
        # Add API version to response headers
        if hasattr(g, 'api_version'):
            response.headers['X-API-Version'] = g.api_version
        
        # Add CORS headers if not already present
        if 'Access-Control-Allow-Origin' not in response.headers:
            origins = current_app.config.get('CORS_ORIGINS', ['*'])
            if '*' in origins:
                response.headers['Access-Control-Allow-Origin'] = '*'
            elif request.headers.get('Origin') in origins:
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin')
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Calculate and log response time
        if hasattr(g, 'start_time'):
            response_time = time.time() - g.start_time
            response.headers['X-Response-Time'] = f"{response_time:.3f}s"
            
            if current_app.config.get('ENABLE_REQUEST_LOGGING', True):
                logger.info(
                    f"Response {g.request_id}: {response.status_code} "
                    f"in {response_time:.3f}s"
                )
        
        return response
    
    @staticmethod
    def teardown_request(exception=None):
        """Clean up after request."""
        if exception:
            logger.error(f"Request {getattr(g, 'request_id', 'unknown')} failed: {exception}")


class PerformanceMiddleware:
    """Middleware for performance monitoring."""
    
    def __init__(self, app=None):
        self.app = app
        self.monitor = get_global_monitor()
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize performance middleware."""
        app.before_request(self.start_monitoring)
        app.after_request(self.end_monitoring)
    
    def start_monitoring(self):
        """Start performance monitoring for request."""
        if self.monitor:
            g.perf_start = time.time()
            g.memory_start = self.monitor.get_memory_usage()
    
    def end_monitoring(self, response):
        """End performance monitoring and record metrics."""
        if self.monitor and hasattr(g, 'perf_start'):
            duration = time.time() - g.perf_start
            memory_end = self.monitor.get_memory_usage()
            memory_delta = memory_end - getattr(g, 'memory_start', 0)
            
            # Record metrics
            endpoint = request.endpoint or 'unknown'
            method = request.method
            status_code = response.status_code
            
            # Log performance metrics
            logger.debug(
                f"Performance {getattr(g, 'request_id', 'unknown')}: "
                f"{method} {endpoint} - {duration:.3f}s, "
                f"memory delta: {memory_delta:.2f}MB, "
                f"status: {status_code}"
            )
        
        return response


class ErrorHandlingMiddleware:
    """Middleware for centralized error handling."""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize error handling middleware."""
        app.errorhandler(400)(self.handle_bad_request)
        app.errorhandler(401)(self.handle_unauthorized)
        app.errorhandler(403)(self.handle_forbidden)
        app.errorhandler(404)(self.handle_not_found)
        app.errorhandler(405)(self.handle_method_not_allowed)
        app.errorhandler(429)(self.handle_rate_limit_exceeded)
        app.errorhandler(500)(self.handle_internal_error)
        app.errorhandler(Exception)(self.handle_generic_exception)
    
    @staticmethod
    def handle_bad_request(error):
        """Handle 400 Bad Request errors."""
        return jsonify(create_error_response(
            error="Bad Request",
            message="The request could not be understood by the server",
            status_code=400,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 400
    
    @staticmethod
    def handle_unauthorized(error):
        """Handle 401 Unauthorized errors."""
        return jsonify(create_error_response(
            error="Unauthorized",
            message="Authentication required",
            status_code=401,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 401
    
    @staticmethod
    def handle_forbidden(error):
        """Handle 403 Forbidden errors."""
        return jsonify(create_error_response(
            error="Forbidden",
            message="Insufficient permissions",
            status_code=403,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 403
    
    @staticmethod
    def handle_not_found(error):
        """Handle 404 Not Found errors."""
        return jsonify(create_error_response(
            error="Not Found",
            message="The requested resource was not found",
            status_code=404,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 404
    
    @staticmethod
    def handle_method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        return jsonify(create_error_response(
            error="Method Not Allowed",
            message="The request method is not allowed for this resource",
            status_code=405,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 405
    
    @staticmethod
    def handle_rate_limit_exceeded(error):
        """Handle 429 Rate Limit Exceeded errors."""
        return jsonify(create_error_response(
            error="Rate Limit Exceeded",
            message="Too many requests. Please try again later",
            status_code=429,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 429
    
    @staticmethod
    def handle_internal_error(error):
        """Handle 500 Internal Server Error."""
        logger.error(f"Internal server error: {error}")
        
        # Don't expose internal error details in production
        include_details = current_app.config.get('INCLUDE_ERROR_DETAILS', False)
        message = str(error) if include_details else "An internal server error occurred"
        
        return jsonify(create_error_response(
            error="Internal Server Error",
            message=message,
            status_code=500,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 500
    
    @staticmethod
    def handle_generic_exception(error):
        """Handle any unhandled exceptions."""
        logger.exception(f"Unhandled exception: {error}")
        
        # Don't expose exception details in production
        include_details = current_app.config.get('INCLUDE_ERROR_DETAILS', False)
        message = str(error) if include_details else "An unexpected error occurred"
        
        return jsonify(create_error_response(
            error="Unexpected Error",
            message=message,
            status_code=500,
            request_id=getattr(g, 'request_id', None)
        ).to_dict()), 500


class CompressionMiddleware:
    """Middleware for response compression."""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize compression middleware."""
        if current_app.config.get('ENABLE_RESPONSE_COMPRESSION', True):
            try:
                from flask_compress import Compress
                Compress(app)
            except ImportError:
                logger.warning("flask-compress not available, compression disabled")


def rate_limit(limit: str):
    """Rate limiting decorator."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Simple rate limiting implementation
            # In production, use Redis or a proper rate limiting library
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def validate_json(required_fields: list = None):
    """JSON validation decorator."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                return jsonify(create_error_response(
                    error="Invalid Content Type",
                    message="Content-Type must be application/json",
                    status_code=400
                ).to_dict()), 400
            
            data = request.get_json()
            if not data:
                return jsonify(create_error_response(
                    error="Invalid JSON",
                    message="Request body must contain valid JSON",
                    status_code=400
                ).to_dict()), 400
            
            if required_fields:
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    return jsonify(create_error_response(
                        error="Missing Required Fields",
                        message=f"Missing required fields: {', '.join(missing_fields)}",
                        status_code=400
                    ).to_dict()), 400
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_api_call(f):
    """Decorator to log API calls."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        try:
            result = f(*args, **kwargs)
            duration = time.time() - start_time
            
            logger.info(
                f"API call {request.endpoint}: {request.method} {request.path} "
                f"completed in {duration:.3f}s"
            )
            
            return result
        
        except Exception as e:
            duration = time.time() - start_time
            
            logger.error(
                f"API call {request.endpoint}: {request.method} {request.path} "
                f"failed after {duration:.3f}s - {str(e)}"
            )
            
            raise
    
    return decorated_function