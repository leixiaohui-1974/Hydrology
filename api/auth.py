"""Authentication and authorization for the API.

This module provides JWT-based authentication and role-based authorization.
"""

import os
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, Optional, Callable

try:
    from flask import request, jsonify, current_app, g
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

# Add parent directory to path for imports
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from common.security import get_security_manager, User
from .models import ErrorResponse


class APIAuth:
    """API authentication manager."""
    
    def __init__(self, secret_key: str = None, token_expiry: int = 3600):
        self.secret_key = secret_key or os.environ.get('JWT_SECRET_KEY', secrets.token_urlsafe(32))
        self.token_expiry = token_expiry
        self.algorithm = 'HS256'
        
        # Initialize security manager
        try:
            self.security_manager = get_security_manager()
        except Exception:
            self.security_manager = None
    
    def generate_token(self, user: User, additional_claims: Dict[str, Any] = None) -> str:
        """Generate JWT token for user."""
        if not JWT_AVAILABLE:
            raise ImportError("PyJWT is required for token generation. Install with: pip install PyJWT")
        
        payload = {
            'user_id': user.username,
            'email': user.email,
            'roles': user.roles,
            'permissions': user.permissions,
            'exp': datetime.utcnow() + timedelta(seconds=self.token_expiry),
            'iat': datetime.utcnow(),
            'iss': 'hydrology-api'
        }
        
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token."""
        if not JWT_AVAILABLE:
            return None
        
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials."""
        if not self.security_manager:
            return None
        
        return self.security_manager.user_manager.authenticate_user(username, password)
    
    def get_user_from_token(self, token: str) -> Optional[User]:
        """Get user object from token."""
        payload = self.verify_token(token)
        if not payload:
            return None
        
        if not self.security_manager:
            return None
        
        return self.security_manager.user_manager.get_user(payload['user_id'])


# Global auth instance
api_auth = APIAuth()


def extract_token() -> Optional[str]:
    """Extract token from request headers."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    
    # Support both "Bearer <token>" and "<token>" formats
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return auth_header


def require_auth(f: Callable) -> Callable:
    """Decorator to require authentication for API endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not FLASK_AVAILABLE:
            return jsonify(ErrorResponse(
                error="Configuration Error",
                message="Flask is not available",
                status_code=500
            ).to_dict()), 500
        
        token = extract_token()
        if not token:
            return jsonify(ErrorResponse(
                error="Authentication Required",
                message="Missing authentication token",
                status_code=401
            ).to_dict()), 401
        
        payload = api_auth.verify_token(token)
        if not payload:
            return jsonify(ErrorResponse(
                error="Invalid Token",
                message="Invalid or expired authentication token",
                status_code=401
            ).to_dict()), 401
        
        # Store user info in request context
        g.current_user_id = payload['user_id']
        g.current_user_roles = payload.get('roles', [])
        g.current_user_permissions = payload.get('permissions', [])
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_role(role: str) -> Callable:
    """Decorator to require specific role for API endpoints."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'current_user_roles'):
                return jsonify(ErrorResponse(
                    error="Authentication Required",
                    message="Authentication required",
                    status_code=401
                ).to_dict()), 401
            
            if role not in g.current_user_roles:
                return jsonify(ErrorResponse(
                    error="Insufficient Permissions",
                    message=f"Role '{role}' required",
                    status_code=403
                ).to_dict()), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def require_permission(permission: str) -> Callable:
    """Decorator to require specific permission for API endpoints."""
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'current_user_permissions'):
                return jsonify(ErrorResponse(
                    error="Authentication Required",
                    message="Authentication required",
                    status_code=401
                ).to_dict()), 401
            
            if permission not in g.current_user_permissions:
                return jsonify(ErrorResponse(
                    error="Insufficient Permissions",
                    message=f"Permission '{permission}' required",
                    status_code=403
                ).to_dict()), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def generate_token(username: str, password: str) -> Optional[str]:
    """Generate token for user credentials."""
    user = api_auth.authenticate_user(username, password)
    if not user:
        return None
    
    return api_auth.generate_token(user)


def create_api_key(user_id: str, name: str = "API Key", expires_in: int = None) -> str:
    """Create a long-lived API key for programmatic access."""
    if not JWT_AVAILABLE:
        raise ImportError("PyJWT is required for API key generation")
    
    expiry = expires_in or (365 * 24 * 3600)  # 1 year default
    
    payload = {
        'user_id': user_id,
        'type': 'api_key',
        'name': name,
        'exp': datetime.utcnow() + timedelta(seconds=expiry),
        'iat': datetime.utcnow(),
        'iss': 'hydrology-api'
    }
    
    return jwt.encode(payload, api_auth.secret_key, algorithm=api_auth.algorithm)


def validate_api_key(token: str) -> Optional[Dict[str, Any]]:
    """Validate API key token."""
    payload = api_auth.verify_token(token)
    if not payload or payload.get('type') != 'api_key':
        return None
    
    return payload