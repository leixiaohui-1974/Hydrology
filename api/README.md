# Hydrology Framework REST API

A comprehensive RESTful API for the Hydrology Framework, providing programmatic access to hydrology modeling and simulation capabilities.

## Features

- **Model Management**: List and configure hydrology models (XAJ, HYMOD, etc.)
- **Simulation Execution**: Run simulations synchronously or asynchronously
- **Data Management**: Access and manage datasets
- **Authentication & Authorization**: JWT-based security with role-based access
- **Performance Monitoring**: Built-in performance tracking and health checks
- **Rate Limiting**: Configurable rate limiting to prevent abuse
- **Comprehensive Error Handling**: Detailed error responses with request tracking

## Quick Start

### Prerequisites

```bash
# Required packages
pip install flask flask-cors

# Optional packages for enhanced functionality
pip install flask-limiter redis cryptography bcrypt PyJWT
```

### Starting the API Server

```bash
# Start development server
python run_api.py

# Start with custom configuration
python run_api.py --host 0.0.0.0 --port 8080 --config production

# Start with debug mode
python run_api.py --debug --reload
```

The API will be available at `http://localhost:5000` by default.

### Testing the API

```bash
# Run automated tests
python api/test_api.py

# Test against custom server
python api/test_api.py --url http://localhost:8080
```

## API Endpoints

### Health Check

```http
GET /health
```

Returns server health status and system information.

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 3600.5,
    "dependencies": {
      "numpy": "available",
      "pandas": "available",
      "flask": "available"
    }
  },
  "message": "Service is running"
}
```

### Authentication

#### Login

```http
POST /auth/login
Content-Type: application/json

{
  "username": "your_username",
  "password": "your_password"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "Bearer"
  },
  "message": "Authentication successful"
}
```

### Models

#### List Available Models

```http
GET /models
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "name": "XAJ",
      "version": "1.0",
      "description": "Xinanjiang rainfall-runoff model",
      "parameters": [
        {"name": "K", "type": "float", "description": "Evapotranspiration coefficient"},
        {"name": "B", "type": "float", "description": "Tension water capacity exponent"}
      ]
    }
  ]
}
```

#### Get Model Information

```http
GET /models/{model_name}
Authorization: Bearer <token>
```

### Simulations

#### Create Simulation

```http
POST /simulations
Authorization: Bearer <token>
Content-Type: application/json

{
  "model_name": "xaj",
  "parameters": {
    "K": 0.5,
    "B": 0.3,
    "IM": 0.01
  },
  "input_data": {
    "rainfall": [10.5, 15.2, 8.7, 12.1, 6.3]
  },
  "async_execution": false
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "simulation_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "completed",
    "results": {
      "flow": [1.2, 1.5, 2.1, 1.8, 1.3],
      "timestamps": ["2023-01-01T00:00:00Z", "2023-01-01T01:00:00Z"]
    }
  }
}
```

#### Get Simulation Status

```http
GET /simulations/{simulation_id}
Authorization: Bearer <token>
```

#### List Simulations

```http
GET /simulations?page=1&per_page=10
Authorization: Bearer <token>
```

#### Delete Simulation

```http
DELETE /simulations/{simulation_id}
Authorization: Bearer <token>
```

### Datasets

#### List Available Datasets

```http
GET /datasets
Authorization: Bearer <token>
```

## Authentication

The API uses JWT (JSON Web Tokens) for authentication. Include the token in the Authorization header:

```http
Authorization: Bearer <your_jwt_token>
```

### Default Test Credentials

- Username: `test_user`
- Password: `test_password`

## Error Handling

All API responses follow a consistent format:

**Success Response:**
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation successful",
  "timestamp": "2023-01-01T12:00:00Z"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error Type",
  "message": "Detailed error message",
  "status_code": 400,
  "timestamp": "2023-01-01T12:00:00Z",
  "request_id": "req_123456"
}
```

### Common HTTP Status Codes

- `200 OK` - Request successful
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

## Configuration

The API supports multiple configuration environments:

- **Development** (`development`): Debug mode, relaxed security
- **Testing** (`testing`): In-memory database, disabled rate limiting
- **Production** (`production`): Optimized for production use
- **Docker** (`docker`): Container-optimized settings

### Environment Variables

```bash
# Security
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret

# Database
DATABASE_URL=postgresql://user:pass@localhost/hydrology

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com

# Configuration
FLASK_ENV=production
```

## Rate Limiting

Default rate limits:
- Development: 1000 requests/hour
- Production: 60 requests/hour

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## Monitoring and Logging

### Health Monitoring

The `/health` endpoint provides:
- Service status
- Uptime information
- Dependency status
- Memory usage

### Request Logging

All requests are logged with:
- Request ID for tracing
- Response time
- Status code
- Client IP

### Performance Metrics

Response headers include:
```http
X-Request-ID: req_123456789
X-Response-Time: 0.045s
X-API-Version: 1.0
```

## Development

### Project Structure

```
api/
├── __init__.py          # Package initialization
├── app.py              # Flask application factory
├── auth.py             # Authentication and authorization
├── config.py           # Configuration classes
├── middleware.py       # Request/response middleware
├── models.py           # API data models
├── routes.py           # API route definitions
├── utils.py            # Utility functions
├── test_api.py         # API test suite
└── README.md           # This file
```

### Adding New Endpoints

1. Define route in `routes.py`
2. Add authentication/authorization decorators
3. Implement request validation
4. Add error handling
5. Update tests in `test_api.py`

### Running Tests

```bash
# Run API tests
python api/test_api.py

# Run with custom parameters
python api/test_api.py --url http://localhost:8080 --username admin --password secret
```

## Deployment

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "run_api.py", "--host", "0.0.0.0", "--config", "docker"]
```

### Production Considerations

1. **Use a production WSGI server** (Gunicorn, uWSGI)
2. **Set up reverse proxy** (Nginx, Apache)
3. **Configure SSL/TLS** for HTTPS
4. **Use external database** (PostgreSQL, MySQL)
5. **Set up Redis** for caching and sessions
6. **Configure monitoring** (Prometheus, Grafana)
7. **Set up logging** (ELK stack, Fluentd)

## Security

### Best Practices

- Always use HTTPS in production
- Rotate JWT secrets regularly
- Implement proper input validation
- Use rate limiting to prevent abuse
- Monitor for suspicious activity
- Keep dependencies updated

### Security Headers

The API automatically adds security headers:
```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
```

## Support

For issues and questions:
1. Check the logs for error details
2. Verify configuration settings
3. Test with the provided test suite
4. Review the API documentation

## License

This API is part of the Hydrology Framework and follows the same license terms.