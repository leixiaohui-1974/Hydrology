import numpy as np

class EnsembleKalmanFilter:
    """
    一个通用的集合卡尔曼滤波器 (EnKF) 实现。
    """
    def __init__(self, n_ensemble):
        """
        初始化滤波器。
        :param n_ensemble: 集合中的成员数量。
        """
        self.n_ensemble = n_ensemble
        self.states = None
        self.P = None # 状态协方差矩阵

    def initialize(self, initial_states):
        """
        初始化状态集合。
        :param initial_states: 一个 (n_states, n_ensemble) 的 numpy 数组，
                               其中 n_states 是状态变量的数量。
        """
        if initial_states.shape[1] != self.n_ensemble:
            raise ValueError("初始状态集合的大小与指定的 n_ensemble 不匹配。")
        self.states = initial_states
        self.P = np.cov(self.states)

    def forecast(self, model_forward, **kwargs):
        """
        预测步骤：将每个集合成员向前推进一个时间步。
        :param model_forward: 一个函数，接收一个状态向量和 **kwargs，
                              返回更新后的状态向量和对应的观测预测。
        """
        if self.states is None:
            raise RuntimeError("滤波器未初始化。请先调用 initialize()。")

        forecast_states = []
        forecast_observations = []

        for i in range(self.n_ensemble):
            state_col = self.states[:, i]
            new_state, obs_pred = model_forward(state_col, **kwargs)
            forecast_states.append(new_state)
            forecast_observations.append(obs_pred)

        self.states = np.array(forecast_states).T
        self.P = np.cov(self.states)

        # Reshape to (n_ensemble, n_obs)
        return np.array(forecast_observations).reshape(self.n_ensemble, -1)

    def analysis(self, observation, forecast_observations, R):
        """
        分析步骤：使用观测值更新状态集合。
        :param observation: 当前时间步的实际观测值向量 (n_obs,)
        :param forecast_observations: 来自预测步骤的观测预测集合 (n_ensemble, n_obs)
        :param R: 观测误差协方差矩阵 (n_obs, n_obs)。
        """
        y = np.atleast_1d(observation) # Ensure y is a vector

        # Transpose predictions to shape (n_obs, n_ensemble)
        y_pred_ensemble = forecast_observations.T

        n_obs = y_pred_ensemble.shape[0]
        if y.shape[0] != n_obs:
            raise ValueError(f"Observation vector size ({y.shape[0]}) does not match "
                             f"predicted observations size ({n_obs}).")

        # 1. 计算观测预测的均值和协方差
        y_pred_mean = y_pred_ensemble.mean(axis=1, keepdims=True) # Shape (n_obs, 1)

        # Py = C_yy + R (Covariance of observation prediction + observation error)
        Py = np.cov(y_pred_ensemble) + R # Shape (n_obs, n_obs)

        # 2. 计算状态-观测协方差
        # Pxy = C_xy
        state_anomaly = self.states - self.states.mean(axis=1, keepdims=True) # (n_states, n_ens)
        obs_anomaly = y_pred_ensemble - y_pred_mean                          # (n_obs, n_ens)
        Pxy = (1 / (self.n_ensemble - 1)) * state_anomaly @ obs_anomaly.T     # (n_states, n_obs)

        # 3. 计算卡尔曼增益 K = Pxy * Py^-1
        # Handle scalar case for n_obs=1, where Py is a 0-dim array (variance)
        if Py.ndim == 0:
            inv_Py = 1.0 / Py if Py > 1e-9 else 0.0
            K = Pxy * inv_Py
        else:
            inv_Py = np.linalg.inv(Py)
            K = Pxy @ inv_Py # Shape (n_states, n_obs)

        # 4. 更新每个集合成员的状态
        for i in range(self.n_ensemble):
            # Add random perturbation to observation vector
            if y.ndim == 1 and y.shape[0] == 1:
                # Handle scalar observation case
                innovation_noise = np.random.normal(0, np.sqrt(R) if R > 0 else 0)
            else:
                innovation_noise = np.random.multivariate_normal(np.zeros(n_obs), R)
            innovation = y + innovation_noise

            # Residual for this ensemble member
            residual = innovation - y_pred_ensemble[:, i] # Shape (n_obs,)

            # Update state vector
            # K is (n_states, n_obs), residual is (n_obs,). Result is (n_states,)
            self.states[:, i] += K @ residual

        # 5. 更新状态协方差矩阵
        self.P = np.cov(self.states)
