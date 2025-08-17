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

        return np.array(forecast_observations)

    def analysis(self, observation, forecast_observations, R):
        """
        分析步骤：使用观测值更新状态集合。
        :param observation: 当前时间步的实际观测值 (一个标量或向量)。
        :param forecast_observations: 来自预测步骤的观测预测集合 (n_ensemble,)
        :param R: 观测误差协方差矩阵 (n_obs, n_obs)。
        """
        y = observation
        # Reshape to (n_obs, n_ensemble). Here n_obs=1.
        y_pred_ensemble = forecast_observations.reshape(1, -1)

        # 计算观测预测的均值和协方差
        y_pred_mean = y_pred_ensemble.mean()
        # Py = C_yy + R
        Py = np.cov(y_pred_ensemble) + R
        # Ensure Py is a 2D array for matrix operations
        Py = np.atleast_2d(Py)

        # 计算状态-观测协方差
        # Pxy = C_xy
        state_anomaly = self.states - self.states.mean(axis=1, keepdims=True)
        obs_anomaly = y_pred_ensemble - y_pred_mean
        Pxy = (1 / (self.n_ensemble - 1)) * state_anomaly @ obs_anomaly.T

        # 计算卡尔曼增益 K = Pxy * Py^-1
        K = Pxy @ np.linalg.inv(Py)

        # 更新每个集合成员的状态
        for i in range(self.n_ensemble):
            # Add random perturbation to observation
            innovation = y + np.random.normal(0, np.sqrt(R))
            self.states[:, i] += K.flatten() * (innovation - y_pred_ensemble[0, i])

        # 更新状态协方差矩阵
        self.P = np.cov(self.states)
