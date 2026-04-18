"""
深度学习模型增强模块
==================

本模块提供水文模型的深度学习增强功能，包括：
- Transformer架构（时间序列、时空）
- 图神经网络（动态图、时空图、注意力）
- 强化学习（Q-learning、策略梯度、Actor-Critic）
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import logging
from typing import Optional, Tuple, List, Dict, Any

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TimeSeriesTransformer(nn.Module):
    """时间序列Transformer模型"""
    
    def __init__(self, input_dim: int, d_model: int = 512, nhead: int = 8, 
                 num_layers: int = 6, dropout: float = 0.1):
        super().__init__()
        self.input_dim = input_dim
        self.d_model = d_model
        
        # 输入投影层
        self.input_projection = nn.Linear(input_dim, d_model)
        
        # Transformer编码器
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dropout=dropout, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # 输出层
        self.output_layer = nn.Linear(d_model, 1)
        
        # 初始化权重
        self._init_weights()
    
    def _init_weights(self):
        """初始化模型权重"""
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """前向传播"""
        # 输入投影
        x = self.input_projection(x)
        
        # Transformer编码
        x = self.transformer_encoder(x)
        
        # 输出投影
        output = self.output_layer(x)
        
        return output

class SpatioTemporalTransformer(nn.Module):
    """时空Transformer模型"""
    
    def __init__(self, spatial_dim: int, temporal_dim: int, d_model: int = 512,
                 nhead: int = 8, num_layers: int = 6, dropout: float = 0.1):
        super().__init__()
        self.spatial_dim = spatial_dim
        self.temporal_dim = temporal_dim
        self.d_model = d_model
        
        # 空间编码器
        self.spatial_encoder = nn.Linear(spatial_dim, d_model)
        
        # 时间编码器
        self.temporal_encoder = nn.Linear(temporal_dim, d_model)
        
        # 多头注意力
        self.spatial_attention = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        self.temporal_attention = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        
        # 前馈网络
        self.feed_forward = nn.Sequential(
            nn.Linear(d_model, d_model * 4),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_model * 4, d_model)
        )
        
        # 输出层
        self.output_layer = nn.Linear(d_model, 1)
        
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, spatial_data: torch.Tensor, temporal_data: torch.Tensor) -> torch.Tensor:
        """前向传播"""
        # 编码
        spatial_encoded = self.spatial_encoder(spatial_data)
        temporal_encoded = self.temporal_encoder(temporal_data)
        
        # 空间注意力
        spatial_attended, _ = self.spatial_attention(
            spatial_encoded, spatial_encoded, spatial_encoded
        )
        
        # 时间注意力
        temporal_attended, _ = self.temporal_attention(
            temporal_encoded, temporal_encoded, temporal_encoded
        )
        
        # 融合
        fused = spatial_attended + temporal_attended.unsqueeze(1).expand_as(spatial_attended)
        
        # 前馈网络
        output = self.feed_forward(fused)
        
        # 输出
        return self.output_layer(output)

class DynamicGraphNeuralNetwork(nn.Module):
    """动态图神经网络"""
    
    def __init__(self, node_features: int, hidden_dim: int = 64, num_layers: int = 3,
                 dropout: float = 0.1):
        super().__init__()
        self.node_features = node_features
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # 图卷积层
        self.conv_layers = nn.ModuleList()
        self.conv_layers.append(nn.Linear(node_features, hidden_dim))
        for _ in range(num_layers - 1):
            self.conv_layers.append(nn.Linear(hidden_dim, hidden_dim))
        
        # 输出层
        self.output_layer = nn.Linear(hidden_dim, 1)
        
        # Dropout
        self.dropout = nn.Dropout(dropout)
    
    def forward(self, x: torch.Tensor, adj_matrix: torch.Tensor) -> torch.Tensor:
        """前向传播"""
        # 图卷积层
        for i, conv in enumerate(self.conv_layers):
            x = conv(x)
            if i < len(self.conv_layers) - 1:
                x = F.relu(x)
                x = self.dropout(x)
            # 简单的图卷积操作
            x = torch.mm(adj_matrix, x)
        
        # 输出
        return self.output_layer(x)

class QLearningAgent:
    """Q-learning强化学习智能体"""
    
    def __init__(self, state_size: int, action_size: int, learning_rate: float = 0.1,
                 discount_factor: float = 0.95, epsilon: float = 0.1):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        
        # Q表
        self.q_table = np.zeros((state_size, action_size))
        
        logger.info(f"Q-learning agent initialized: {state_size} states, {action_size} actions")
    
    def get_action(self, state: int) -> int:
        """选择动作（ε-贪婪策略）"""
        if np.random.random() < self.epsilon:
            return np.random.randint(self.action_size)
        else:
            return np.argmax(self.q_table[state])
    
    def update_q_value(self, state: int, action: int, reward: float, next_state: int):
        """更新Q值"""
        old_value = self.q_table[state, action]
        next_max = np.max(self.q_table[next_state])
        new_value = (1 - self.learning_rate) * old_value + \
                   self.learning_rate * (reward + self.discount_factor * next_max)
        self.q_table[state, action] = new_value

class PolicyGradientAgent:
    """策略梯度强化学习智能体"""
    
    def __init__(self, state_size: int, action_size: int, hidden_dim: int = 64,
                 learning_rate: float = 0.001):
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        
        # 策略网络
        self.policy_network = nn.Sequential(
            nn.Linear(state_size, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_size),
            nn.Softmax(dim=-1)
        )
        
        # 优化器
        self.optimizer = torch.optim.Adam(self.policy_network.parameters(), lr=learning_rate)
        
        # 经验存储
        self.episode_rewards = []
        self.episode_actions = []
        self.episode_states = []
        
        logger.info(f"Policy gradient agent initialized: {state_size} states, {action_size} actions")
    
    def get_action(self, state: np.ndarray) -> int:
        """选择动作"""
        state_tensor = torch.FloatTensor(state)
        action_probs = self.policy_network(state_tensor)
        action_dist = torch.distributions.Categorical(action_probs)
        action = action_dist.sample()
        return action.item()
    
    def store_transition(self, state: np.ndarray, action: int, reward: float):
        """存储转换"""
        self.episode_states.append(state)
        self.episode_actions.append(action)
        self.episode_rewards.append(reward)
    
    def update_policy(self):
        """更新策略"""
        if len(self.episode_rewards) == 0:
            return
        
        # 计算折扣奖励
        discounted_rewards = []
        running_reward = 0
        for reward in reversed(self.episode_rewards):
            running_reward = reward + 0.95 * running_reward
            discounted_rewards.insert(0, running_reward)
        
        # 标准化奖励
        discounted_rewards = torch.FloatTensor(discounted_rewards)
        discounted_rewards = (discounted_rewards - discounted_rewards.mean()) / \
                           (discounted_rewards.std() + 1e-9)
        
        # 计算损失
        loss = 0
        for state, action, reward in zip(self.episode_states, self.episode_actions, discounted_rewards):
            state_tensor = torch.FloatTensor(state)
            action_probs = self.policy_network(state_tensor)
            action_dist = torch.distributions.Categorical(action_probs)
            log_prob = action_dist.log_prob(torch.tensor(action))
            loss -= log_prob * reward
        
        # 更新网络
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        # 清空经验
        self.episode_rewards = []
        self.episode_actions = []
        self.episode_states = []

class MultiAgentRL:
    """多智能体强化学习系统"""
    
    def __init__(self, num_agents: int, state_size: int, action_size: int,
                 agent_type: str = "q_learning"):
        self.num_agents = num_agents
        self.state_size = state_size
        self.action_size = action_size
        
        # 创建智能体
        self.agents = []
        for i in range(num_agents):
            if agent_type == "q_learning":
                agent = QLearningAgent(state_size, action_size)
            elif agent_type == "policy_gradient":
                agent = PolicyGradientAgent(state_size, action_size)
            else:
                raise ValueError(f"Unknown agent type: {agent_type}")
            
            self.agents.append(agent)
        
        logger.info(f"Multi-agent RL system initialized with {num_agents} {agent_type} agents")
    
    def get_actions(self, states: List[np.ndarray]) -> List[int]:
        """获取所有智能体的动作"""
        if len(states) != self.num_agents:
            raise ValueError("Number of states must match number of agents")
        
        actions = []
        for i, (agent, state) in enumerate(zip(self.agents, states)):
            action = agent.get_action(state)
            actions.append(action)
        
        return actions
    
    def update_agents(self, experiences: List[Tuple]):
        """更新所有智能体"""
        if len(experiences) != self.num_agents:
            raise ValueError("Number of experiences must match number of agents")
        
        for i, (agent, experience) in enumerate(zip(self.agents, experiences)):
            if hasattr(agent, 'update_q_value'):
                # Q-learning agent
                state, action, reward, next_state = experience
                agent.update_q_value(state, action, reward, next_state)
            elif hasattr(agent, 'update_policy'):
                # Policy gradient agent
                agent.update_policy()
