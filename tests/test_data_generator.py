"""Test data generator for creating synthetic datasets for testing.

This module provides utilities to generate realistic hydrological data
for testing various components of the framework.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union
import json
import os


class WeatherDataGenerator:
    """Generate synthetic weather data for testing."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize the weather data generator.
        
        Args:
            seed: Random seed for reproducible results
        """
        if seed is not None:
            np.random.seed(seed)
        
        # Default climate parameters
        self.climate_params = {
            'annual_rainfall': 800,  # mm/year
            'rainfall_seasonality': 0.3,  # 0 = uniform, 1 = highly seasonal
            'temperature_mean': 15,  # °C
            'temperature_amplitude': 10,  # °C seasonal variation
            'pet_coefficient': 0.1,  # PET = coeff * temperature + base
            'pet_base': 1.0,  # mm/day base PET
            'storm_frequency': 0.1,  # probability of storm per day
            'storm_intensity': 20,  # mm/day average storm intensity
        }
    
    def set_climate_params(self, **params):
        """Update climate parameters."""
        self.climate_params.update(params)
    
    def generate_rainfall(self, 
                         start_date: str, 
                         end_date: str, 
                         timestep_hours: int = 24) -> pd.Series:
        """Generate synthetic rainfall time series.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timestep_hours: Time step in hours
            
        Returns:
            Pandas Series with rainfall data
        """
        dates = pd.date_range(start_date, end_date, freq=f'{timestep_hours}H')
        n_steps = len(dates)
        
        # Seasonal pattern
        day_of_year = dates.dayofyear
        seasonal_factor = 1 + self.climate_params['rainfall_seasonality'] * \
                         np.sin(2 * np.pi * (day_of_year - 80) / 365)
        
        # Base rainfall rate (mm per timestep)
        base_rate = (self.climate_params['annual_rainfall'] / 365) * \
                   (timestep_hours / 24) * seasonal_factor
        
        # Storm events
        storm_prob = self.climate_params['storm_frequency'] * (timestep_hours / 24)
        is_storm = np.random.random(n_steps) < storm_prob
        
        # Generate rainfall
        rainfall = np.zeros(n_steps)
        
        # Background rainfall (light, frequent)
        background = np.random.exponential(base_rate * 0.5, n_steps)
        background[background < 0.1] = 0  # No trace amounts
        
        # Storm rainfall (heavy, infrequent)
        storm_intensity = np.random.exponential(
            self.climate_params['storm_intensity'] * (timestep_hours / 24), 
            n_steps
        )
        
        rainfall = background + is_storm * storm_intensity
        
        return pd.Series(rainfall, index=dates, name='rainfall_mm')
    
    def generate_temperature(self, 
                           start_date: str, 
                           end_date: str, 
                           timestep_hours: int = 24) -> pd.Series:
        """Generate synthetic temperature time series.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timestep_hours: Time step in hours
            
        Returns:
            Pandas Series with temperature data
        """
        dates = pd.date_range(start_date, end_date, freq=f'{timestep_hours}H')
        n_steps = len(dates)
        
        # Seasonal pattern
        day_of_year = dates.dayofyear
        seasonal_temp = self.climate_params['temperature_mean'] + \
                       self.climate_params['temperature_amplitude'] * \
                       np.sin(2 * np.pi * (day_of_year - 80) / 365)
        
        # Daily variation (if hourly data)
        if timestep_hours <= 24:
            hour_of_day = dates.hour
            daily_variation = 3 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
        else:
            daily_variation = 0
        
        # Random variation
        random_variation = np.random.normal(0, 2, n_steps)
        
        temperature = seasonal_temp + daily_variation + random_variation
        
        return pd.Series(temperature, index=dates, name='temperature_c')
    
    def generate_pet(self, temperature: pd.Series) -> pd.Series:
        """Generate potential evapotranspiration from temperature.
        
        Args:
            temperature: Temperature time series
            
        Returns:
            Pandas Series with PET data
        """
        # Simple temperature-based PET calculation
        pet = self.climate_params['pet_base'] + \
              self.climate_params['pet_coefficient'] * np.maximum(temperature, 0)
        
        # Add some random variation
        pet_variation = np.random.normal(1, 0.1, len(pet))
        pet = pet * pet_variation
        
        # Ensure non-negative
        pet = np.maximum(pet, 0)
        
        return pd.Series(pet, index=temperature.index, name='pet_mm')
    
    def generate_weather_dataset(self, 
                               start_date: str, 
                               end_date: str, 
                               timestep_hours: int = 24) -> pd.DataFrame:
        """Generate complete weather dataset.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            timestep_hours: Time step in hours
            
        Returns:
            DataFrame with rainfall, temperature, and PET
        """
        rainfall = self.generate_rainfall(start_date, end_date, timestep_hours)
        temperature = self.generate_temperature(start_date, end_date, timestep_hours)
        pet = self.generate_pet(temperature)
        
        return pd.DataFrame({
            'rainfall': rainfall,
            'temperature': temperature,
            'pet': pet
        })


class FlowDataGenerator:
    """Generate synthetic streamflow data for testing."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize the flow data generator."""
        if seed is not None:
            np.random.seed(seed)
        
        self.flow_params = {
            'baseflow': 5.0,  # m³/s
            'baseflow_recession': 0.95,  # daily recession coefficient
            'runoff_coefficient': 0.3,  # fraction of rainfall that becomes runoff
            'lag_time': 2.0,  # hours
            'attenuation': 0.8,  # flow attenuation factor
            'noise_level': 0.1,  # relative noise level
        }
    
    def set_flow_params(self, **params):
        """Update flow parameters."""
        self.flow_params.update(params)
    
    def generate_baseflow(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """Generate baseflow time series.
        
        Args:
            dates: Time index
            
        Returns:
            Baseflow array
        """
        n_steps = len(dates)
        baseflow = np.zeros(n_steps)
        
        # Initial baseflow
        baseflow[0] = self.flow_params['baseflow']
        
        # Recession curve
        recession = self.flow_params['baseflow_recession']
        
        for i in range(1, n_steps):
            # Daily recession
            timestep_days = (dates[i] - dates[i-1]).total_seconds() / 86400
            baseflow[i] = baseflow[i-1] * (recession ** timestep_days)
        
        return baseflow
    
    def generate_quickflow(self, 
                          rainfall: pd.Series, 
                          dates: pd.DatetimeIndex) -> np.ndarray:
        """Generate quickflow from rainfall.
        
        Args:
            rainfall: Rainfall time series
            dates: Time index
            
        Returns:
            Quickflow array
        """
        n_steps = len(dates)
        quickflow = np.zeros(n_steps)
        
        # Convert rainfall to runoff
        runoff = rainfall * self.flow_params['runoff_coefficient']
        
        # Apply lag and attenuation
        lag_steps = max(1, int(self.flow_params['lag_time'] / 
                              ((dates[1] - dates[0]).total_seconds() / 3600)))
        
        for i in range(len(runoff)):
            if runoff.iloc[i] > 0:
                # Distribute runoff over time with lag and attenuation
                for j in range(min(lag_steps * 2, n_steps - i)):
                    delay_factor = np.exp(-j / lag_steps)
                    if i + j < n_steps:
                        quickflow[i + j] += (runoff.iloc[i] * delay_factor * 
                                           self.flow_params['attenuation'])
        
        return quickflow
    
    def generate_streamflow(self, 
                          rainfall: pd.Series, 
                          add_noise: bool = True) -> pd.Series:
        """Generate streamflow from rainfall.
        
        Args:
            rainfall: Rainfall time series
            add_noise: Whether to add measurement noise
            
        Returns:
            Streamflow time series
        """
        dates = rainfall.index
        
        # Generate components
        baseflow = self.generate_baseflow(dates)
        quickflow = self.generate_quickflow(rainfall, dates)
        
        # Total flow
        total_flow = baseflow + quickflow
        
        # Add noise if requested
        if add_noise:
            noise = np.random.normal(1, self.flow_params['noise_level'], len(total_flow))
            total_flow = total_flow * noise
        
        # Ensure non-negative
        total_flow = np.maximum(total_flow, 0)
        
        return pd.Series(total_flow, index=dates, name='streamflow_m3s')


class MeshDataGenerator:
    """Generate synthetic mesh data for 2D model testing."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize the mesh data generator."""
        if seed is not None:
            np.random.seed(seed)
    
    def generate_regular_grid(self, 
                            nx: int, 
                            ny: int, 
                            dx: float = 1.0, 
                            dy: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
        """Generate regular grid points and triangles.
        
        Args:
            nx: Number of points in x direction
            ny: Number of points in y direction
            dx: Grid spacing in x direction
            dy: Grid spacing in y direction
            
        Returns:
            Tuple of (points, triangles) arrays
        """
        # Generate grid points
        x = np.arange(nx) * dx
        y = np.arange(ny) * dy
        X, Y = np.meshgrid(x, y)
        points = np.column_stack([X.ravel(), Y.ravel()])
        
        # Generate triangles
        triangles = []
        for i in range(ny - 1):
            for j in range(nx - 1):
                # Two triangles per grid cell
                p1 = i * nx + j
                p2 = i * nx + (j + 1)
                p3 = (i + 1) * nx + j
                p4 = (i + 1) * nx + (j + 1)
                
                triangles.append([p1, p2, p3])
                triangles.append([p2, p4, p3])
        
        return points, np.array(triangles)
    
    def generate_terrain(self, 
                        points: np.ndarray, 
                        terrain_type: str = 'valley') -> np.ndarray:
        """Generate terrain elevation for mesh points.
        
        Args:
            points: Array of (x, y) coordinates
            terrain_type: Type of terrain ('flat', 'slope', 'valley', 'hill')
            
        Returns:
            Array of elevation values
        """
        x = points[:, 0]
        y = points[:, 1]
        
        if terrain_type == 'flat':
            elevation = np.zeros_like(x)
        
        elif terrain_type == 'slope':
            # Linear slope in x direction
            elevation = 0.01 * x
        
        elif terrain_type == 'valley':
            # V-shaped valley
            x_center = (x.max() + x.min()) / 2
            elevation = 0.001 * (x - x_center) ** 2 + 0.005 * y
        
        elif terrain_type == 'hill':
            # Gaussian hill
            x_center = (x.max() + x.min()) / 2
            y_center = (y.max() + y.min()) / 2
            sigma_x = (x.max() - x.min()) / 4
            sigma_y = (y.max() - y.min()) / 4
            
            elevation = 10 * np.exp(-((x - x_center) ** 2 / (2 * sigma_x ** 2) +
                                    (y - y_center) ** 2 / (2 * sigma_y ** 2)))
        
        else:
            raise ValueError(f"Unknown terrain type: {terrain_type}")
        
        # Add some random variation
        elevation += np.random.normal(0, 0.1, len(elevation))
        
        return elevation
    
    def generate_initial_conditions(self, 
                                  points: np.ndarray, 
                                  scenario: str = 'dry') -> Dict[str, np.ndarray]:
        """Generate initial conditions for 2D simulation.
        
        Args:
            points: Array of (x, y) coordinates
            scenario: Initial condition scenario
            
        Returns:
            Dictionary with initial condition arrays
        """
        n_points = len(points)
        
        if scenario == 'dry':
            h = np.zeros(n_points)  # No initial water
            uh = np.zeros(n_points)  # No initial momentum
            vh = np.zeros(n_points)
        
        elif scenario == 'wet':
            h = np.full(n_points, 0.1)  # 10 cm initial water depth
            uh = np.zeros(n_points)
            vh = np.zeros(n_points)
        
        elif scenario == 'dam_break':
            # Dam break scenario
            x = points[:, 0]
            x_center = (x.max() + x.min()) / 2
            
            h = np.where(x < x_center, 2.0, 0.1)  # High water upstream
            uh = np.zeros(n_points)
            vh = np.zeros(n_points)
        
        elif scenario == 'channel_flow':
            # Steady channel flow
            y = points[:, 1]
            y_center = (y.max() + y.min()) / 2
            channel_width = (y.max() - y.min()) / 4
            
            # Water only in channel
            in_channel = np.abs(y - y_center) < channel_width
            h = np.where(in_channel, 1.0, 0.0)
            uh = np.where(in_channel, 1.0, 0.0)  # Flow in x direction
            vh = np.zeros(n_points)
        
        else:
            raise ValueError(f"Unknown scenario: {scenario}")
        
        return {
            'h': h,
            'uh': uh,
            'vh': vh
        }


class TestDataManager:
    """Manage test datasets and scenarios."""
    
    def __init__(self, data_dir: str = 'test_data'):
        """Initialize test data manager.
        
        Args:
            data_dir: Directory to store test data
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        self.weather_gen = WeatherDataGenerator()
        self.flow_gen = FlowDataGenerator()
        self.mesh_gen = MeshDataGenerator()
    
    def create_test_scenario(self, 
                           scenario_name: str, 
                           config: Dict) -> str:
        """Create a complete test scenario.
        
        Args:
            scenario_name: Name of the scenario
            config: Configuration dictionary
            
        Returns:
            Path to scenario directory
        """
        scenario_dir = os.path.join(self.data_dir, scenario_name)
        os.makedirs(scenario_dir, exist_ok=True)
        
        # Save configuration
        config_file = os.path.join(scenario_dir, 'config.json')
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Generate weather data if requested
        if 'weather' in config:
            weather_config = config['weather']
            weather_data = self.weather_gen.generate_weather_dataset(
                weather_config['start_date'],
                weather_config['end_date'],
                weather_config.get('timestep_hours', 24)
            )
            
            weather_file = os.path.join(scenario_dir, 'weather.csv')
            weather_data.to_csv(weather_file)
            
            # Generate streamflow if requested
            if config.get('generate_flow', False):
                flow_data = self.flow_gen.generate_streamflow(weather_data['rainfall'])
                flow_file = os.path.join(scenario_dir, 'streamflow.csv')
                flow_data.to_csv(flow_file)
        
        # Generate mesh data if requested
        if 'mesh' in config:
            mesh_config = config['mesh']
            points, triangles = self.mesh_gen.generate_regular_grid(
                mesh_config['nx'],
                mesh_config['ny'],
                mesh_config.get('dx', 1.0),
                mesh_config.get('dy', 1.0)
            )
            
            # Save mesh
            np.savetxt(os.path.join(scenario_dir, 'points.txt'), points)
            np.savetxt(os.path.join(scenario_dir, 'triangles.txt'), triangles, fmt='%d')
            
            # Generate terrain
            terrain_type = mesh_config.get('terrain_type', 'flat')
            elevation = self.mesh_gen.generate_terrain(points, terrain_type)
            np.savetxt(os.path.join(scenario_dir, 'elevation.txt'), elevation)
            
            # Generate initial conditions
            scenario_type = mesh_config.get('scenario', 'dry')
            initial_conditions = self.mesh_gen.generate_initial_conditions(points, scenario_type)
            
            for var, values in initial_conditions.items():
                np.savetxt(os.path.join(scenario_dir, f'initial_{var}.txt'), values)
        
        return scenario_dir
    
    def get_standard_scenarios(self) -> Dict[str, Dict]:
        """Get predefined standard test scenarios.
        
        Returns:
            Dictionary of scenario configurations
        """
        scenarios = {
            'simple_rainfall': {
                'description': 'Simple rainfall-runoff test',
                'weather': {
                    'start_date': '2020-01-01',
                    'end_date': '2020-01-31',
                    'timestep_hours': 24
                },
                'generate_flow': True
            },
            
            'storm_event': {
                'description': 'Intense storm event',
                'weather': {
                    'start_date': '2020-06-01',
                    'end_date': '2020-06-07',
                    'timestep_hours': 1
                },
                'generate_flow': True
            },
            
            'annual_simulation': {
                'description': 'Full year simulation',
                'weather': {
                    'start_date': '2020-01-01',
                    'end_date': '2020-12-31',
                    'timestep_hours': 24
                },
                'generate_flow': True
            },
            
            'small_2d_mesh': {
                'description': 'Small 2D mesh for testing',
                'mesh': {
                    'nx': 10,
                    'ny': 10,
                    'dx': 10.0,
                    'dy': 10.0,
                    'terrain_type': 'slope',
                    'scenario': 'dry'
                }
            },
            
            'dam_break_test': {
                'description': 'Dam break simulation',
                'mesh': {
                    'nx': 50,
                    'ny': 20,
                    'dx': 2.0,
                    'dy': 2.0,
                    'terrain_type': 'valley',
                    'scenario': 'dam_break'
                }
            },
            
            'channel_flow_test': {
                'description': 'Channel flow simulation',
                'mesh': {
                    'nx': 30,
                    'ny': 15,
                    'dx': 5.0,
                    'dy': 5.0,
                    'terrain_type': 'slope',
                    'scenario': 'channel_flow'
                }
            }
        }
        
        return scenarios
    
    def create_all_standard_scenarios(self):
        """Create all standard test scenarios."""
        scenarios = self.get_standard_scenarios()
        
        for name, config in scenarios.items():
            print(f"Creating scenario: {name}")
            scenario_dir = self.create_test_scenario(name, config)
            print(f"  Created in: {scenario_dir}")
    
    def load_scenario_data(self, scenario_name: str) -> Dict:
        """Load data from a test scenario.
        
        Args:
            scenario_name: Name of the scenario
            
        Returns:
            Dictionary with loaded data
        """
        scenario_dir = os.path.join(self.data_dir, scenario_name)
        
        if not os.path.exists(scenario_dir):
            raise FileNotFoundError(f"Scenario not found: {scenario_name}")
        
        data = {}
        
        # Load configuration
        config_file = os.path.join(scenario_dir, 'config.json')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                data['config'] = json.load(f)
        
        # Load weather data
        weather_file = os.path.join(scenario_dir, 'weather.csv')
        if os.path.exists(weather_file):
            data['weather'] = pd.read_csv(weather_file, index_col=0, parse_dates=True)
        
        # Load streamflow data
        flow_file = os.path.join(scenario_dir, 'streamflow.csv')
        if os.path.exists(flow_file):
            data['streamflow'] = pd.read_csv(flow_file, index_col=0, parse_dates=True)
        
        # Load mesh data
        points_file = os.path.join(scenario_dir, 'points.txt')
        if os.path.exists(points_file):
            data['points'] = np.loadtxt(points_file)
            
            triangles_file = os.path.join(scenario_dir, 'triangles.txt')
            if os.path.exists(triangles_file):
                data['triangles'] = np.loadtxt(triangles_file, dtype=int)
            
            elevation_file = os.path.join(scenario_dir, 'elevation.txt')
            if os.path.exists(elevation_file):
                data['elevation'] = np.loadtxt(elevation_file)
            
            # Load initial conditions
            for var in ['h', 'uh', 'vh']:
                ic_file = os.path.join(scenario_dir, f'initial_{var}.txt')
                if os.path.exists(ic_file):
                    if 'initial_conditions' not in data:
                        data['initial_conditions'] = {}
                    data['initial_conditions'][var] = np.loadtxt(ic_file)
        
        return data


if __name__ == '__main__':
    # Example usage
    print("Test Data Generator Example")
    print("=" * 40)
    
    # Create test data manager
    manager = TestDataManager()
    
    # Create all standard scenarios
    manager.create_all_standard_scenarios()
    
    # Load and display a scenario
    data = manager.load_scenario_data('simple_rainfall')
    
    if 'weather' in data:
        weather = data['weather']
        print(f"\nWeather data summary:")
        print(f"Period: {weather.index[0]} to {weather.index[-1]}")
        print(f"Total rainfall: {weather['rainfall'].sum():.1f} mm")
        print(f"Mean temperature: {weather['temperature'].mean():.1f} °C")
        print(f"Mean PET: {weather['pet'].mean():.1f} mm/day")
    
    if 'streamflow' in data:
        flow = data['streamflow']
        print(f"\nStreamflow data summary:")
        print(f"Mean flow: {flow.iloc[:, 0].mean():.2f} m³/s")
        print(f"Peak flow: {flow.iloc[:, 0].max():.2f} m³/s")
    
    print("\nTest data generation completed!")