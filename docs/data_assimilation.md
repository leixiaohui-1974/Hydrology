# Data Assimilation

The Hydro-Suite includes a data assimilation module in `hydro_model.data_assimilation` for integrating observational data with model forecasts to improve state estimates. This is essential for applications like real-time forecasting and reanalysis.

The module provides two main families of algorithms:
1.  **Ensemble Kalman Filters (EnKF)**: Including enhanced versions like `LocalizedEnKF` and `AdaptiveEnKF`.
2.  **Particle Filters (PF)**: Including a standard `ParticleFilter` and advanced versions like `AuxiliaryParticleFilter` and `RegularizedParticleFilter`.

---

## 1. Ensemble Kalman Filter (EnKF)

EnKF is a Monte Carlo-based method that uses an ensemble of model states to represent the error statistics of the forecast. It is well-suited for high-dimensional, non-linear models.

### Adaptive EnKF Example

The `AdaptiveEnKF` automatically adjusts parameters like covariance inflation to improve filter performance and prevent divergence. Here is an example of it tracking the chaotic Lorenz '63 system.

```python
import numpy as np
from hydro_model.data_assimilation.enkf_enhanced import AdaptiveEnKF

# 1. Define the model dynamics (e.g., Lorenz '63)
def lorenz63_system(state, dt):
    sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
    x, y, z = state
    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z
    return state + np.array([dx, dy, dz]) * dt

# 2. Generate true data and noisy observations
dt = 0.01
n_steps = 200
true_states = np.zeros((n_steps, 3))
true_states[0] = [0., 1., 1.05]
for t in range(1, n_steps):
    true_states[t] = lorenz63_system(true_states[t-1], dt)
observations = true_states + np.random.normal(0, 2.0, true_states.shape)

# 3. Initialize the filter
n_ensemble = 50
enkf = AdaptiveEnKF(ensemble_size=n_ensemble)
enkf.set_state_info(state_dim=3)
enkf.set_observation_info(obs_dim=3)

# 4. Create initial ensemble and run assimilation loop
ensemble = np.random.multivariate_normal(observations[0], np.eye(3), n_ensemble).T
for t in range(1, n_steps):
    # Forecast
    for i in range(n_ensemble):
        ensemble[:, i] = lorenz63_system(ensemble[:, i], dt)

    # Assimilate
    enkf.set_ensemble(ensemble_states=ensemble, ensemble_obs=ensemble)
    ensemble = enkf.assimilate(observations[t], obs_errors=np.full(3, 2.0))

# The mean of the final ensemble is the best estimate of the state.
final_estimate = np.mean(ensemble, axis=1)
```

---

## 2. Particle Filter (PF)

Particle Filters represent the probability distribution of the state with a set of discrete "particles," each with a corresponding weight. They are very powerful for highly non-linear, non-Gaussian systems.

### Example

Here is an example of a `ParticleFilter` tracking the same Lorenz '63 system.

```python
import numpy as np
from hydro_model.data_assimilation.particle_filter import ParticleFilter

# (Use the same lorenz63_system, true_states, and observations from the EnKF example)

# 1. Define the transition and observation models for the filter
def pf_transition_model(particles):
    return np.apply_along_axis(lorenz63_system, 1, particles, dt=0.01)

def pf_observation_model(particles):
    return particles

def initial_distribution(n_particles):
    return np.random.multivariate_normal(observations[0], np.eye(3) * 5.0, n_particles)

# 2. Initialize and run the filter
pf = ParticleFilter(n_particles=1000)
pf.set_transition_model(pf_transition_model)
pf.set_observation_model(pf_observation_model)
pf.initialize_particles(initial_distribution)

process_noise = 0.1
observation_noise = 2.0

for t in range(1, n_steps):
    pf.step(
        observations[t],
        process_noise_std=process_noise,
        observation_noise_std=observation_noise
    )

# 3. Get the final state estimate
final_estimate = pf.get_state_estimate()['mean']
```
