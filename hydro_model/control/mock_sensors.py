"""
Mock Sensors for Real-time Control and State Estimation
Generates pseudo-real-time observation data with Gaussian noise, drift, and packet loss.
"""
import numpy as np

class MockSensor:
    def __init__(self, noise_std=0.01, drift_std=0.001, packet_loss_rate=0.05, seed=None):
        """
        Initialize the mock sensor.
        
        Args:
            noise_std (float): Standard deviation of Gaussian white noise.
            drift_std (float): Standard deviation of the random walk step for zero-mean drift.
            packet_loss_rate (float): Probability of packet loss (0.0 to 1.0).
            seed (int, optional): Random seed for reproducibility.
        """
        self.noise_std = noise_std
        self.drift_std = drift_std
        self.packet_loss_rate = packet_loss_rate
        self.rng = np.random.default_rng(seed)
        self.current_drift = 0.0
        
    def generate(self, true_value):
        """
        Generate a single mock observation based on the true value.
        
        Args:
            true_value (float or np.ndarray): The ground truth value.
            
        Returns:
            float or np.ndarray: The mock observation. If packet loss occurs, returns np.nan.
        """
        # Packet loss
        if self.rng.random() < self.packet_loss_rate:
            if isinstance(true_value, np.ndarray):
                return np.full_like(true_value, np.nan, dtype=float)
            return np.nan
            
        # Gaussian white noise
        noise = self.rng.normal(0, self.noise_std, size=np.shape(true_value))
        
        # Zero-mean drift (random walk with mean reversion to keep it bounded/zero-mean)
        drift_step = self.rng.normal(0, self.drift_std, size=np.shape(true_value))
        self.current_drift = self.current_drift * 0.95 + drift_step  # AR(1) process for bounded zero-mean drift
        
        return true_value + noise + self.current_drift

    def generate_series(self, true_series):
        """
        Generate a series of mock observations based on a true series.
        
        Args:
            true_series (list or np.ndarray): The ground truth time series.
            
        Returns:
            np.ndarray: The mock observation time series with np.nan for lost packets.
        """
        mock_series = []
        for val in true_series:
            mock_series.append(self.generate(val))
        return np.array(mock_series)
