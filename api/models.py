"""Data models for API responses and requests.

This module defines standard data structures for API communication.
"""

from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass, asdict
import json


@dataclass
class APIResponse:
    """Standard API response format."""
    
    success: bool
    data: Any = None
    message: str = ""
    timestamp: str = None
    request_id: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + 'Z'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class ErrorResponse:
    """Standard error response format."""
    
    error: str
    message: str
    status_code: int
    details: Optional[Dict[str, Any]] = None
    timestamp: str = None
    request_id: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + 'Z'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@dataclass
class SimulationRequest:
    """Request model for simulation endpoints."""
    
    config: Dict[str, Any]
    parameters: Optional[Dict[str, Any]] = None
    data_sources: Optional[Dict[str, Any]] = None
    output_format: str = 'json'
    async_execution: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SimulationRequest':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class SimulationResponse:
    """Response model for simulation results."""
    
    simulation_id: str
    status: str  # 'running', 'completed', 'failed'
    results: Optional[Dict[str, Any]] = None
    progress: Optional[float] = None
    error_message: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class ModelInfo:
    """Model information structure."""
    
    name: str
    version: str
    description: str
    parameters: List[Dict[str, Any]]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class DatasetInfo:
    """Dataset information structure."""
    
    name: str
    description: str
    format: str
    size: int
    columns: List[str]
    sample_data: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class HealthStatus:
    """Health check response structure."""
    
    status: str  # 'healthy', 'degraded', 'unhealthy'
    version: str
    uptime: float
    dependencies: Dict[str, str]
    memory_usage: Optional[Dict[str, float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class PaginatedResponse:
    """Paginated response structure."""
    
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool
    has_prev: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class ValidationError(Exception):
    """Validation error for API requests."""
    
    def __init__(self, message: str, field: str = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {'message': self.message}
        if self.field:
            result['field'] = self.field
        if self.value is not None:
            result['value'] = self.value
        return result


def validate_simulation_request(data: Dict[str, Any]) -> SimulationRequest:
    """Validate and parse simulation request."""
    if not isinstance(data, dict):
        raise ValidationError("Request data must be a JSON object")

    normalized_data = dict(data)

    # Backward compatibility: accept legacy top-level payload format.
    if 'config' not in normalized_data:
        if 'model_name' in normalized_data or 'input_data' in normalized_data:
            normalized_data['config'] = {
                'model_name': normalized_data.get('model_name'),
                'input_data': normalized_data.get('input_data', {})
            }
        else:
            raise ValidationError("Missing required field: config")

    if not isinstance(normalized_data['config'], dict):
        raise ValidationError("Config must be a JSON object", field='config')

    if normalized_data.get('parameters') is None:
        normalized_data['parameters'] = normalized_data['config'].get('parameters')

    if normalized_data.get('data_sources') is None:
        if 'input_data' in normalized_data:
            normalized_data['data_sources'] = normalized_data['input_data']
        elif 'input_data' in normalized_data['config']:
            normalized_data['data_sources'] = normalized_data['config'].get('input_data')
        else:
            normalized_data['data_sources'] = normalized_data['config'].get('data_sources')

    if 'async_execution' not in normalized_data:
        normalized_data['async_execution'] = False

    # Validate output format
    output_format = normalized_data.get('output_format', 'json')
    if output_format not in ['json', 'csv', 'netcdf']:
        raise ValidationError(
            "Invalid output format. Must be one of: json, csv, netcdf",
            field='output_format',
            value=output_format
        )

    normalized_data['output_format'] = output_format

    return SimulationRequest(
        config=normalized_data['config'],
        parameters=normalized_data.get('parameters'),
        data_sources=normalized_data.get('data_sources'),
        output_format=normalized_data['output_format'],
        async_execution=normalized_data['async_execution']
    )


def create_success_response(data: Any = None, message: str = "") -> APIResponse:
    """Create a success response."""
    return APIResponse(success=True, data=data, message=message)


def create_error_response(error: str, message: str, status_code: int = 400, 
                         details: Dict[str, Any] = None) -> ErrorResponse:
    """Create an error response."""
    return ErrorResponse(
        error=error,
        message=message,
        status_code=status_code,
        details=details
    )
