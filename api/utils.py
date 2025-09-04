"""Utility functions for the Hydrology Framework REST API.

This module contains helper functions for data processing, validation,
formatting, and other common operations.
"""

import os
import json
import hashlib
import mimetypes
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from functools import wraps

try:
    from flask import request, current_app
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


def generate_hash(data: Union[str, bytes]) -> str:
    """Generate SHA-256 hash of data."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def format_datetime(dt: datetime, format_str: str = None) -> str:
    """Format datetime to ISO string or custom format."""
    if format_str:
        return dt.strftime(format_str)
    return dt.isoformat()


def parse_datetime(date_str: str) -> datetime:
    """Parse datetime string to datetime object."""
    try:
        # Try ISO format first
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        # Try common formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y'
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        raise ValueError(f"Unable to parse datetime: {date_str}")


def validate_email(email: str) -> bool:
    """Validate email address format."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password: str) -> Dict[str, Any]:
    """Validate password strength."""
    import re
    
    result = {
        'valid': True,
        'errors': [],
        'score': 0
    }
    
    # Check length
    if len(password) < 8:
        result['valid'] = False
        result['errors'].append('Password must be at least 8 characters long')
    else:
        result['score'] += 1
    
    # Check for uppercase
    if not re.search(r'[A-Z]', password):
        result['valid'] = False
        result['errors'].append('Password must contain at least one uppercase letter')
    else:
        result['score'] += 1
    
    # Check for lowercase
    if not re.search(r'[a-z]', password):
        result['valid'] = False
        result['errors'].append('Password must contain at least one lowercase letter')
    else:
        result['score'] += 1
    
    # Check for digits
    if not re.search(r'\d', password):
        result['valid'] = False
        result['errors'].append('Password must contain at least one digit')
    else:
        result['score'] += 1
    
    # Check for special characters
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        result['errors'].append('Password should contain at least one special character')
    else:
        result['score'] += 1
    
    return result


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    import re
    # Remove or replace unsafe characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Replace spaces with underscores
    filename = re.sub(r'\s+', '_', filename)
    # Remove multiple consecutive dots
    filename = re.sub(r'\.{2,}', '.', filename)
    return filename.strip('.')


def get_file_extension(filename: str) -> str:
    """Get file extension from filename."""
    return os.path.splitext(filename)[1].lower().lstrip('.')


def is_allowed_file(filename: str, allowed_extensions: set = None) -> bool:
    """Check if file extension is allowed."""
    if allowed_extensions is None:
        allowed_extensions = {'csv', 'txt', 'json', 'xlsx'}
    
    extension = get_file_extension(filename)
    return extension in allowed_extensions


def get_mime_type(filename: str) -> str:
    """Get MIME type for filename."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes == 0:
        return '0 B'
    
    size_names = ['B', 'KB', 'MB', 'GB', 'TB']
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f'{s} {size_names[i]}'


def paginate_data(data: List[Any], page: int, per_page: int) -> Dict[str, Any]:
    """Paginate a list of data."""
    total = len(data)
    start = (page - 1) * per_page
    end = start + per_page
    
    items = data[start:end]
    
    return {
        'items': items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
        'has_next': end < total,
        'has_prev': page > 1
    }


def validate_pagination_params(page: str = None, per_page: str = None) -> Dict[str, int]:
    """Validate and normalize pagination parameters."""
    try:
        page = int(page) if page else 1
        per_page = int(per_page) if per_page else 10
    except ValueError:
        raise ValueError("Page and per_page must be integers")
    
    if page < 1:
        raise ValueError("Page must be >= 1")
    
    if per_page < 1:
        raise ValueError("Per_page must be >= 1")
    
    max_per_page = 100  # Default max
    if FLASK_AVAILABLE and current_app:
        max_per_page = current_app.config.get('MAX_PAGE_SIZE', 100)
    
    if per_page > max_per_page:
        per_page = max_per_page
    
    return {'page': page, 'per_page': per_page}


def clean_dict(data: Dict[str, Any], remove_none: bool = True, remove_empty: bool = False) -> Dict[str, Any]:
    """Clean dictionary by removing None or empty values."""
    cleaned = {}
    
    for key, value in data.items():
        if remove_none and value is None:
            continue
        
        if remove_empty and not value:
            continue
        
        if isinstance(value, dict):
            cleaned_value = clean_dict(value, remove_none, remove_empty)
            if cleaned_value or not remove_empty:
                cleaned[key] = cleaned_value
        else:
            cleaned[key] = value
    
    return cleaned


def deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def flatten_dict(data: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten nested dictionary."""
    items = []
    
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep).items())
        else:
            items.append((new_key, value))
    
    return dict(items)


def convert_to_serializable(obj: Any) -> Any:
    """Convert object to JSON serializable format."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, set):
        return list(obj)
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    else:
        return str(obj)


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Safely load JSON string."""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: Any = None) -> str:
    """Safely dump object to JSON string."""
    try:
        return json.dumps(obj, default=convert_to_serializable, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(default) if default is not None else '{}'


def generate_api_key(length: int = 32) -> str:
    """Generate a random API key."""
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def mask_sensitive_data(data: Dict[str, Any], sensitive_fields: List[str] = None) -> Dict[str, Any]:
    """Mask sensitive fields in data."""
    if sensitive_fields is None:
        sensitive_fields = ['password', 'token', 'secret', 'key', 'api_key']
    
    masked_data = data.copy()
    
    for field in sensitive_fields:
        if field in masked_data:
            if isinstance(masked_data[field], str) and len(masked_data[field]) > 4:
                masked_data[field] = masked_data[field][:2] + '*' * (len(masked_data[field]) - 4) + masked_data[field][-2:]
            else:
                masked_data[field] = '***'
    
    return masked_data


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data against JSON schema."""
    try:
        import jsonschema
        jsonschema.validate(data, schema)
        return {'valid': True, 'errors': []}
    except ImportError:
        # Fallback to basic validation if jsonschema not available
        return basic_schema_validation(data, schema)
    except jsonschema.ValidationError as e:
        return {'valid': False, 'errors': [str(e)]}


def basic_schema_validation(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """Basic schema validation without jsonschema library."""
    errors = []
    
    # Check required fields
    required = schema.get('required', [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Check field types
    properties = schema.get('properties', {})
    for field, field_schema in properties.items():
        if field in data:
            expected_type = field_schema.get('type')
            value = data[field]
            
            if expected_type == 'string' and not isinstance(value, str):
                errors.append(f"Field '{field}' must be a string")
            elif expected_type == 'integer' and not isinstance(value, int):
                errors.append(f"Field '{field}' must be an integer")
            elif expected_type == 'number' and not isinstance(value, (int, float)):
                errors.append(f"Field '{field}' must be a number")
            elif expected_type == 'boolean' and not isinstance(value, bool):
                errors.append(f"Field '{field}' must be a boolean")
            elif expected_type == 'array' and not isinstance(value, list):
                errors.append(f"Field '{field}' must be an array")
            elif expected_type == 'object' and not isinstance(value, dict):
                errors.append(f"Field '{field}' must be an object")
    
    return {'valid': len(errors) == 0, 'errors': errors}


def rate_limit_key(identifier: str, endpoint: str) -> str:
    """Generate rate limit key for caching."""
    return f"rate_limit:{identifier}:{endpoint}"


def cache_key(prefix: str, *args) -> str:
    """Generate cache key from prefix and arguments."""
    key_parts = [prefix] + [str(arg) for arg in args]
    return ':'.join(key_parts)


def get_client_ip() -> str:
    """Get client IP address from request."""
    if not FLASK_AVAILABLE:
        return '127.0.0.1'
    
    # Check for forwarded IP first
    forwarded_ips = request.headers.get('X-Forwarded-For')
    if forwarded_ips:
        return forwarded_ips.split(',')[0].strip()
    
    # Check other common headers
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # Fall back to remote address
    return request.remote_addr or '127.0.0.1'


def get_user_agent() -> str:
    """Get user agent from request."""
    if not FLASK_AVAILABLE:
        return 'Unknown'
    
    return request.headers.get('User-Agent', 'Unknown')


def timing_decorator(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        import time
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        execution_time = end_time - start_time
        print(f"Function {func.__name__} took {execution_time:.4f} seconds")
        
        return result
    return wrapper


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry function on failure."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(delay * (2 ** attempt))  # Exponential backoff
            
        return wrapper
    return decorator