"""
3D Visualization Module for Hydrology Models
============================================
This module provides 3D visualization capabilities for hydrological models,
including terrain, water flow, and model components.
"""
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import json
import os


class Terrain3DViewer:
    """
    3D terrain visualization for hydrological models.
    """
    
    def __init__(self, terrain_data: Optional[np.ndarray] = None):
        """
        Initialize the 3D terrain viewer.
        
        Args:
            terrain_data: 2D array of elevation data (DEM)
        """
        self.terrain_data = terrain_data
        self.water_surface = None
        self.flow_vectors = None
        self.components = {}
        
    def load_terrain_from_file(self, file_path: str):
        """Load terrain data from a file (GeoTIFF, CSV, etc.)."""
        if file_path.endswith('.tif') or file_path.endswith('.tiff'):
            import rasterio
            with rasterio.open(file_path) as src:
                self.terrain_data = src.read(1)
        elif file_path.endswith('.csv'):
            self.terrain_data = np.loadtxt(file_path, delimiter=',')
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
            
    def set_water_surface(self, water_levels: np.ndarray):
        """Set water surface levels for visualization."""
        if water_levels.shape != self.terrain_data.shape:
            raise ValueError("Water surface shape must match terrain shape")
        self.water_surface = water_levels
        
    def add_flow_vectors(self, u_velocities: np.ndarray, v_velocities: np.ndarray):
        """Add flow velocity vectors for visualization."""
        if u_velocities.shape != self.terrain_data.shape:
            raise ValueError("Velocity field shape must match terrain shape")
        self.flow_vectors = (u_velocities, v_velocities)
        
    def add_component(self, name: str, position: Tuple[float, float, float], 
                     size: Tuple[float, float, float], component_type: str = "generic"):
        """Add a model component to the 3D scene."""
        self.components[name] = {
            'position': position,
            'size': size,
            'type': component_type
        }
        
    def create_matplotlib_3d(self, figsize: Tuple[int, int] = (12, 8)) -> plt.Figure:
        """Create a 3D visualization using matplotlib."""
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111, projection='3d')
        
        if self.terrain_data is not None:
            # Create coordinate grids
            rows, cols = self.terrain_data.shape
            x = np.linspace(0, cols, cols)
            y = np.linspace(0, rows, rows)
            X, Y = np.meshgrid(x, y)
            Z = self.terrain_data
            
            # Plot terrain surface
            terrain_surf = ax.plot_surface(X, Y, Z, cmap='terrain', alpha=0.8)
            
            # Add water surface if available
            if self.water_surface is not None:
                water_surf = ax.plot_surface(X, Y, self.water_surface, 
                                           cmap='Blues', alpha=0.6)
                
            # Add flow vectors if available
            if self.flow_vectors is not None:
                u, v = self.flow_vectors
                # Sample vectors for visualization
                step = max(1, min(rows, cols) // 20)
                ax.quiver(X[::step, ::step], Y[::step, ::step], 
                         Z[::step, ::step], u[::step, ::step], 
                         v[::step, ::step], np.zeros_like(u[::step, ::step]),
                         length=0.5, color='blue', alpha=0.7)
        
        # Add components
        for name, comp in self.components.items():
            pos = comp['position']
            size = comp['size']
            
            # Create a simple box representation
            x, y, z = pos
            dx, dy, dz = size
            
            # Define the 8 vertices of the box
            vertices = [
                [x, y, z], [x+dx, y, z], [x+dx, y+dy, z], [x, y+dy, z],
                [x, y, z+dz], [x+dx, y, z+dz], [x+dx, y+dy, z+dz], [x, y+dy, z+dz]
            ]
            
            # Define the 6 faces of the box
            faces = [
                [vertices[0], vertices[1], vertices[2], vertices[3]],
                [vertices[4], vertices[5], vertices[6], vertices[7]],
                [vertices[0], vertices[1], vertices[5], vertices[4]],
                [vertices[2], vertices[3], vertices[7], vertices[6]],
                [vertices[1], vertices[2], vertices[6], vertices[5]],
                [vertices[4], vertices[7], vertices[3], vertices[0]]
            ]
            
            # Create 3D polygon collection
            poly3d = Poly3DCollection(faces, alpha=0.7, facecolor='red')
            ax.add_collection3d(poly3d)
            
            # Add component label
            ax.text(pos[0] + size[0]/2, pos[1] + size[1]/2, pos[2] + size[2], 
                   name, fontsize=8)
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Elevation')
        ax.set_title('3D Hydrology Model Visualization')
        
        return fig
        
    def create_plotly_3d(self, height: int = 800) -> go.Figure:
        """Create an interactive 3D visualization using Plotly."""
        if self.terrain_data is None:
            raise ValueError("Terrain data is required for 3D visualization")
            
        rows, cols = self.terrain_data.shape
        x = np.linspace(0, cols, cols)
        y = np.linspace(0, rows, rows)
        X, Y = np.meshgrid(x, y)
        Z = self.terrain_data
        
        # Create terrain surface
        terrain_surface = go.Surface(
            x=X, y=Y, z=Z,
            colorscale='terrain',
            opacity=0.8,
            name='Terrain'
        )
        
        # Create water surface if available
        water_surface = None
        if self.water_surface is not None:
            water_surface = go.Surface(
                x=X, y=Y, z=self.water_surface,
                colorscale='Blues',
                opacity=0.6,
                name='Water Surface'
            )
        
        # Create flow vectors if available
        flow_vectors = []
        if self.flow_vectors is not None:
            u, v = self.flow_vectors
            step = max(1, min(rows, cols) // 15)
            
            for i in range(0, rows, step):
                for j in range(0, cols, step):
                    if not np.isnan(u[i, j]) and not np.isnan(v[i, j]):
                        flow_vectors.append(go.Scatter3d(
                            x=[X[i, j], X[i, j] + u[i, j]],
                            y=[Y[i, j], Y[i, j] + v[i, j]],
                            z=[Z[i, j], Z[i, j]],
                            mode='lines',
                            line=dict(color='blue', width=3),
                            showlegend=False
                        ))
        
        # Create component markers
        component_markers = []
        for name, comp in self.components.items():
            pos = comp['position']
            size = comp['size']
            
            # Create component box
            x, y, z = pos
            dx, dy, dz = size
            
            # Create 8 vertices
            vertices = [
                [x, y, z], [x+dx, y, z], [x+dx, y+dy, z], [x, y+dy, z],
                [x, y, z+dz], [x+dx, y, z+dz], [x+dx, y+dy, z+dz], [x, y+dy, z+dz]
            ]
            
            # Create box faces
            faces = [
                [0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
                [2, 3, 7, 6], [1, 2, 6, 5], [4, 7, 3, 0]
            ]
            
            # Create mesh3d for the component
            component_markers.append(go.Mesh3d(
                x=[v[0] for v in vertices],
                y=[v[1] for v in vertices],
                z=[v[2] for v in vertices],
                i=[f[0] for f in faces],
                j=[f[1] for f in faces],
                k=[f[2] for f in faces],
                color='red',
                opacity=0.7,
                name=name
            ))
        
        # Combine all elements
        data = [terrain_surface]
        if water_surface:
            data.append(water_surface)
        data.extend(flow_vectors)
        data.extend(component_markers)
        
        # Create layout
        layout = go.Layout(
            title='3D Hydrology Model Visualization',
            scene=dict(
                xaxis_title='X',
                yaxis_title='Y',
                zaxis_title='Elevation',
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.5)
                )
            ),
            height=height,
            showlegend=True
        )
        
        return go.Figure(data=data, layout=layout)
        
    def create_water_depth_animation(self, time_steps: List[np.ndarray], 
                                   output_file: str = "water_depth_animation.html"):
        """Create an animated visualization of water depth over time."""
        if not time_steps:
            raise ValueError("Time steps list cannot be empty")
            
        rows, cols = time_steps[0].shape
        x = np.linspace(0, cols, cols)
        y = np.linspace(0, rows, rows)
        X, Y = np.meshgrid(x, y)
        
        # Create frames for animation
        frames = []
        for i, water_depth in enumerate(time_steps):
            frame = go.Frame(
                data=[
                    go.Surface(x=X, y=Y, z=water_depth, colorscale='Blues', opacity=0.8),
                    go.Surface(x=X, y=Y, z=self.terrain_data, colorscale='terrain', opacity=0.6)
                ],
                name=f'Frame {i}',
                traces=[0, 1]
            )
            frames.append(frame)
        
        # Create initial data
        data = [
            go.Surface(x=X, y=Y, z=time_steps[0], colorscale='Blues', opacity=0.8),
            go.Surface(x=X, y=Y, z=self.terrain_data, colorscale='terrain', opacity=0.6)
        ]
        
        # Create layout with animation controls
        layout = go.Layout(
            title='Water Depth Animation Over Time',
            scene=dict(
                xaxis_title='X',
                yaxis_title='Y',
                zaxis_title='Elevation/Depth',
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.5))
            ),
            updatemenus=[{
                'type': 'buttons',
                'showactive': False,
                'buttons': [
                    {'label': 'Play', 'method': 'animate', 'args': [None, {'frame': {'duration': 100, 'redraw': True}, 'fromcurrent': True}]},
                    {'label': 'Pause', 'method': 'animate', 'args': [[None], {'frame': {'duration': 0, 'redraw': False}, 'mode': 'immediate', 'transition': {'duration': 0}}]}
                ]
            }],
            sliders=[{
                'steps': [{'method': 'animate', 'args': [[f'Frame {i}'], {'frame': {'duration': 0, 'redraw': True}, 'mode': 'immediate', 'transition': {'duration': 0}}], 'label': f'Step {i}']} for i in range(len(time_steps))],
                'active': 0,
                'currentvalue': {'prefix': 'Time Step: '},
                'len': 0.9,
                'x': 0.1,
                'xanchor': 'left',
                'y': 0,
                'yanchor': 'top'
            }]
        )
        
        fig = go.Figure(data=data, layout=layout, frames=frames)
        fig.write_html(output_file)
        return fig


class Hydrology3DViewer:
    """
    High-level 3D viewer for hydrological models.
    """
    
    def __init__(self):
        self.terrain_viewer = None
        self.model_components = {}
        self.simulation_results = {}
        
    def load_model_from_config(self, config_file: str):
        """Load a hydrological model configuration for 3D visualization."""
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        # Load terrain data if specified
        if 'terrain_file' in config:
            self.terrain_viewer = Terrain3DViewer()
            self.terrain_viewer.load_terrain_from_file(config['terrain_file'])
            
        # Load model components
        if 'components' in config:
            for comp in config['components']:
                if 'position' in comp and 'size' in comp:
                    self.add_component(
                        comp['name'],
                        tuple(comp['position']),
                        tuple(comp['size']),
                        comp.get('type', 'generic')
                    )
                    
    def add_component(self, name: str, position: Tuple[float, float, float], 
                     size: Tuple[float, float, float], component_type: str = "generic"):
        """Add a model component to the 3D scene."""
        if self.terrain_viewer:
            self.terrain_viewer.add_component(name, position, size, component_type)
        self.model_components[name] = {
            'position': position,
            'size': size,
            'type': component_type
        }
        
    def update_water_surface(self, water_levels: np.ndarray):
        """Update water surface levels for visualization."""
        if self.terrain_viewer:
            self.terrain_viewer.set_water_surface(water_levels)
            
    def update_flow_field(self, u_velocities: np.ndarray, v_velocities: np.ndarray):
        """Update flow velocity field for visualization."""
        if self.terrain_viewer:
            self.terrain_viewer.add_flow_vectors(u_velocities, v_velocities)
            
    def create_visualization(self, output_type: str = "plotly", 
                           output_file: str = None) -> Any:
        """Create a 3D visualization of the hydrological model."""
        if not self.terrain_viewer:
            raise ValueError("No terrain data loaded. Use load_model_from_config() first.")
            
        if output_type == "matplotlib":
            fig = self.terrain_viewer.create_matplotlib_3d()
            if output_file:
                fig.savefig(output_file, dpi=300, bbox_inches='tight')
            return fig
        elif output_type == "plotly":
            fig = self.terrain_viewer.create_plotly_3d()
            if output_file:
                fig.write_html(output_file)
            return fig
        else:
            raise ValueError(f"Unsupported output type: {output_type}")
            
    def create_animation(self, time_series: List[np.ndarray], 
                        output_file: str = "hydrology_animation.html"):
        """Create an animated visualization of the model over time."""
        if not self.terrain_viewer:
            raise ValueError("No terrain data loaded.")
            
        return self.terrain_viewer.create_water_depth_animation(time_series, output_file)


# Utility functions for easy 3D visualization
def quick_3d_visualization(terrain_file: str, output_file: str = None) -> go.Figure:
    """Quick 3D visualization of terrain data."""
    viewer = Terrain3DViewer()
    viewer.load_terrain_from_file(terrain_file)
    
    fig = viewer.create_plotly_3d()
    if output_file:
        fig.write_html(output_file)
    return fig


def create_component_3d_scene(components: List[Dict], terrain_file: str = None) -> go.Figure:
    """Create a 3D scene with model components."""
    viewer = Hydrology3DViewer()
    
    if terrain_file:
        viewer.load_model_from_config({'terrain_file': terrain_file})
    
    # Add components
    for comp in components:
        viewer.add_component(
            comp['name'],
            comp['position'],
            comp['size'],
            comp.get('type', 'generic')
        )
    
    return viewer.create_visualization("plotly")

