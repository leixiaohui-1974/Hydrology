#!/usr/bin/env python3
"""Startup script for the Hydrology Framework REST API.

This script starts the Flask development server for the API.
"""

import os
import sys
import logging
from datetime import datetime

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

try:
    from api.app import create_app
    from api.config import get_config
except ImportError as e:
    print(f"Error importing API modules: {e}")
    print("Make sure Flask is installed: pip install flask flask-cors")
    sys.exit(1)


def setup_logging(config_name='development'):
    """Setup logging configuration."""
    config_class = get_config(config_name)
    
    log_level = getattr(logging, config_class.LOG_LEVEL, logging.INFO)
    log_format = config_class.LOG_FORMAT
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('api.log')
        ]
    )


def main():
    """Main function to start the API server."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Start Hydrology Framework API')
    parser.add_argument('--host', default='127.0.0.1',
                       help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to bind to (default: 5000)')
    parser.add_argument('--config', default='development',
                       choices=['development', 'testing', 'production', 'docker'],
                       help='Configuration to use (default: development)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    parser.add_argument('--reload', action='store_true',
                       help='Enable auto-reload on code changes')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.config)
    logger = logging.getLogger(__name__)
    
    # Create Flask app
    try:
        app = create_app(args.config)
        
        # Store start time for health checks
        app.start_time = datetime.now().timestamp()
        
        logger.info(f"Starting Hydrology Framework API")
        logger.info(f"Configuration: {args.config}")
        logger.info(f"Host: {args.host}")
        logger.info(f"Port: {args.port}")
        logger.info(f"Debug: {args.debug or app.config.get('DEBUG', False)}")
        
        # Print available endpoints
        print("\n" + "="*50)
        print("Hydrology Framework REST API")
        print("="*50)
        print(f"Server starting at: http://{args.host}:{args.port}")
        print("\nAvailable endpoints:")
        print(f"  Health Check:     GET  http://{args.host}:{args.port}/health")
        print(f"  Authentication:   POST http://{args.host}:{args.port}/auth/login")
        print(f"  List Models:      GET  http://{args.host}:{args.port}/models")
        print(f"  Model Info:       GET  http://{args.host}:{args.port}/models/<name>")
        print(f"  Create Simulation: POST http://{args.host}:{args.port}/simulations")
        print(f"  List Simulations: GET  http://{args.host}:{args.port}/simulations")
        print(f"  Simulation Status: GET  http://{args.host}:{args.port}/simulations/<id>")
        print(f"  List Datasets:    GET  http://{args.host}:{args.port}/datasets")
        print("\nAuthentication:")
        print("  Use POST /auth/login with username/password to get a token")
        print("  Include 'Authorization: Bearer <token>' header in requests")
        print("\nTesting:")
        print(f"  Run: python api/test_api.py --url http://{args.host}:{args.port}")
        print("="*50 + "\n")
        
        # Start the server
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug or app.config.get('DEBUG', False),
            use_reloader=args.reload,
            threaded=True
        )
    
    except ImportError as e:
        logger.error(f"Missing dependencies: {e}")
        print("\nMissing dependencies. Please install required packages:")
        print("pip install flask flask-cors")
        print("\nOptional packages for enhanced functionality:")
        print("pip install flask-limiter redis")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        print(f"\nError starting server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)