#!/usr/bin/env python3
"""Test script for the Hydrology Framework REST API.

This script tests the basic functionality of the REST API endpoints.
"""

import os
import sys
import json
import time
import requests
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


class APITester:
    """Test class for API endpoints."""
    
    def __init__(self, base_url: str = 'http://localhost:5000'):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.token = None
        
        # Set default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def set_auth_token(self, token: str):
        """Set authentication token."""
        self.token = token
        self.session.headers.update({
            'Authorization': f'Bearer {token}'
        })
    
    def test_health_check(self) -> bool:
        """Test health check endpoint."""
        print("Testing health check endpoint...")
        
        try:
            response = self.session.get(f'{self.base_url}/health')
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ Health check passed: {data.get('message', 'OK')}")
                return True
            else:
                print(f"✗ Health check failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ Health check error: {e}")
            return False
    
    def test_authentication(self, username: str = 'test_user', password: str = 'test_password') -> bool:
        """Test authentication endpoint."""
        print("Testing authentication...")
        
        try:
            auth_data = {
                'username': username,
                'password': password
            }
            
            response = self.session.post(
                f'{self.base_url}/auth/login',
                json=auth_data
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get('data', {}).get('token')
                
                if token:
                    self.set_auth_token(token)
                    print("✓ Authentication successful")
                    return True
                else:
                    print("✗ No token received")
                    return False
            else:
                print(f"✗ Authentication failed: {response.status_code}")
                if response.headers.get('content-type', '').startswith('application/json'):
                    error_data = response.json()
                    print(f"   Error: {error_data.get('error', 'Unknown error')}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ Authentication error: {e}")
            return False
    
    def test_list_models(self) -> bool:
        """Test list models endpoint."""
        print("Testing list models endpoint...")
        
        try:
            response = self.session.get(f'{self.base_url}/models')
            
            if response.status_code == 200:
                data = response.json()
                models = data.get('data', [])
                print(f"✓ Found {len(models)} models")
                
                for model in models[:2]:  # Show first 2 models
                    print(f"   - {model.get('name', 'Unknown')}: {model.get('description', 'No description')}")
                
                return True
            else:
                print(f"✗ List models failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ List models error: {e}")
            return False
    
    def test_get_model_info(self, model_name: str = 'xaj') -> bool:
        """Test get model info endpoint."""
        print(f"Testing get model info for '{model_name}'...")
        
        try:
            response = self.session.get(f'{self.base_url}/models/{model_name}')
            
            if response.status_code == 200:
                data = response.json()
                model_info = data.get('data', {})
                print(f"✓ Model info retrieved: {model_info.get('name', 'Unknown')}")
                return True
            else:
                print(f"✗ Get model info failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ Get model info error: {e}")
            return False
    
    def test_create_simulation(self) -> str:
        """Test create simulation endpoint."""
        print("Testing create simulation...")
        
        try:
            simulation_data = {
                'model_name': 'xaj',
                'parameters': {
                    'K': 0.5,
                    'B': 0.3,
                    'IM': 0.01
                },
                'input_data': {
                    'rainfall': [10.5, 15.2, 8.7, 12.1, 6.3]
                },
                'async_execution': False
            }
            
            response = self.session.post(
                f'{self.base_url}/simulations',
                json=simulation_data
            )
            
            if response.status_code == 201:
                data = response.json()
                simulation_id = data.get('data', {}).get('simulation_id')
                
                if simulation_id:
                    print(f"✓ Simulation created: {simulation_id}")
                    return simulation_id
                else:
                    print("✗ No simulation ID received")
                    return None
            else:
                print(f"✗ Create simulation failed: {response.status_code}")
                if response.headers.get('content-type', '').startswith('application/json'):
                    error_data = response.json()
                    print(f"   Error: {error_data.get('error', 'Unknown error')}")
                return None
        
        except requests.exceptions.RequestException as e:
            print(f"✗ Create simulation error: {e}")
            return None
    
    def test_get_simulation_status(self, simulation_id: str) -> bool:
        """Test get simulation status endpoint."""
        print(f"Testing get simulation status for '{simulation_id}'...")
        
        try:
            response = self.session.get(f'{self.base_url}/simulations/{simulation_id}')
            
            if response.status_code == 200:
                data = response.json()
                sim_data = data.get('data', {})
                status = sim_data.get('status', 'unknown')
                progress = sim_data.get('progress', 0)
                
                print(f"✓ Simulation status: {status} ({progress*100:.1f}% complete)")
                
                if sim_data.get('results'):
                    results = sim_data['results']
                    if isinstance(results, dict) and 'flow' in results:
                        flow_data = results['flow']
                        print(f"   Results: {len(flow_data)} flow values")
                
                return True
            else:
                print(f"✗ Get simulation status failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ Get simulation status error: {e}")
            return False
    
    def test_list_simulations(self) -> bool:
        """Test list simulations endpoint."""
        print("Testing list simulations...")
        
        try:
            response = self.session.get(f'{self.base_url}/simulations?page=1&per_page=5')
            
            if response.status_code == 200:
                data = response.json()
                paginated_data = data.get('data', {})
                items = paginated_data.get('items', [])
                total = paginated_data.get('total', 0)
                
                print(f"✓ Found {total} simulations (showing {len(items)})")
                
                for sim in items[:3]:  # Show first 3 simulations
                    sim_id = sim.get('id', 'unknown')[:8] + '...'
                    status = sim.get('status', 'unknown')
                    print(f"   - {sim_id}: {status}")
                
                return True
            else:
                print(f"✗ List simulations failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ List simulations error: {e}")
            return False
    
    def test_list_datasets(self) -> bool:
        """Test list datasets endpoint."""
        print("Testing list datasets...")
        
        try:
            response = self.session.get(f'{self.base_url}/datasets')
            
            if response.status_code == 200:
                data = response.json()
                datasets = data.get('data', [])
                print(f"✓ Found {len(datasets)} datasets")
                
                for dataset in datasets[:2]:  # Show first 2 datasets
                    name = dataset.get('name', 'Unknown')
                    format_type = dataset.get('format', 'Unknown')
                    print(f"   - {name} ({format_type})")
                
                return True
            else:
                print(f"✗ List datasets failed: {response.status_code}")
                return False
        
        except requests.exceptions.RequestException as e:
            print(f"✗ List datasets error: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, bool]:
        """Run all API tests."""
        print("=" * 50)
        print("Running Hydrology Framework API Tests")
        print("=" * 50)
        
        results = {}
        
        # Test health check (no auth required)
        results['health_check'] = self.test_health_check()
        print()
        
        # Test authentication
        results['authentication'] = self.test_authentication()
        print()
        
        # Only continue if authentication succeeded
        if results['authentication']:
            # Test model endpoints
            results['list_models'] = self.test_list_models()
            print()
            
            results['get_model_info'] = self.test_get_model_info()
            print()
            
            # Test simulation endpoints
            simulation_id = self.test_create_simulation()
            results['create_simulation'] = simulation_id is not None
            print()
            
            if simulation_id:
                # Wait a moment for simulation to process
                time.sleep(1)
                
                results['get_simulation_status'] = self.test_get_simulation_status(simulation_id)
                print()
            
            results['list_simulations'] = self.test_list_simulations()
            print()
            
            # Test dataset endpoints
            results['list_datasets'] = self.test_list_datasets()
            print()
        else:
            print("Skipping authenticated endpoints due to authentication failure")
        
        # Print summary
        print("=" * 50)
        print("Test Results Summary:")
        print("=" * 50)
        
        passed = 0
        total = 0
        
        for test_name, result in results.items():
            status = "PASS" if result else "FAIL"
            print(f"{test_name:25} : {status}")
            if result:
                passed += 1
            total += 1
        
        print(f"\nPassed: {passed}/{total} tests")
        
        return results


def main():
    """Main function to run API tests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Hydrology Framework API')
    parser.add_argument('--url', default='http://localhost:5000', 
                       help='Base URL of the API (default: http://localhost:5000)')
    parser.add_argument('--username', default='test_user',
                       help='Username for authentication (default: test_user)')
    parser.add_argument('--password', default='test_password',
                       help='Password for authentication (default: test_password)')
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = APITester(args.url)
    
    # Run tests
    try:
        results = tester.run_all_tests()
        
        # Exit with error code if any tests failed
        if not all(results.values()):
            sys.exit(1)
        else:
            print("\n🎉 All tests passed!")
            sys.exit(0)
    
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()