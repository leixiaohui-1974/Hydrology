"""
贝叶斯不确定性分析器
====================

提供贝叶斯不确定性量化功能，包括：
- MCMC采样器（Metropolis-Hastings, HMC等）
- 后验分布估计
- 置信区间计算
- 不确定性传播分析
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Any, Callable
from scipy import stats
from scipy.stats import norm, lognorm, uniform, gamma, beta
import warnings
import logging
from pathlib import Path
import json
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import emcee
import corner


class BayesianUncertaintyAnalyzer:
    """
    贝叶斯不确定性分析器
    """
    
    def __init__(self, n_walkers: int = 32, n_steps: int = 1000, 
                 n_burn: int = 200, n_workers: int = None):
        """
        初始化贝叶斯分析器
        
        Args:
            n_walkers: MCMC行走者数量
            n_steps: MCMC步数
            n_burn: 预热步数
            n_workers: 并行工作进程数
        """
        self.n_walkers = n_walkers
        self.n_steps = n_steps
        self.n_burn = n_burn
        self.n_workers = n_workers or min(mp.cpu_count(), 8)
        
        # 参数信息
        self.parameters = {}
        
        # 先验分布
        self.priors = {}
        
        # 观测数据
        self.observations = None
        self.observation_times = None
        
        # 模型函数
        self.model_function = None
        
        # MCMC结果
        self.samples = None
        self.lnprob = None
        self.acceptance_fraction = None
        
        # 后验统计
        self.posterior_stats = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def add_parameter(self, name: str, prior_type: str, **kwargs):
        """
        添加参数及其先验分布
        
        Args:
            name: 参数名称
            prior_type: 先验分布类型
            **kwargs: 先验分布参数
        """
        if prior_type == 'normal':
            self.priors[name] = {
                'type': 'normal',
                'mean': kwargs.get('mean', 0.0),
                'std': kwargs.get('std', 1.0)
            }
        elif prior_type == 'lognormal':
            self.priors[name] = {
                'type': 'lognormal',
                'mean': kwargs.get('mean', 1.0),
                'std': kwargs.get('std', 0.5)
            }
        elif prior_type == 'uniform':
            self.priors[name] = {
                'type': 'uniform',
                'low': kwargs.get('low', 0.0),
                'high': kwargs.get('high', 1.0)
            }
        elif prior_type == 'gamma':
            self.priors[name] = {
                'type': 'gamma',
                'shape': kwargs.get('shape', 1.0),
                'scale': kwargs.get('scale', 1.0)
            }
        elif prior_type == 'beta':
            self.priors[name] = {
                'type': 'beta',
                'alpha': kwargs.get('alpha', 1.0),
                'beta': kwargs.get('beta', 1.0)
            }
        else:
            raise ValueError(f"Unsupported prior type: {prior_type}")
            
        self.parameters[name] = {
            'bounds': self._get_parameter_bounds(name),
            'prior': self.priors[name]
        }
        
        self.logger.info(f"Added parameter: {name} with {prior_type} prior")
        
    def _get_parameter_bounds(self, param_name: str) -> Tuple[float, float]:
        """获取参数边界"""
        prior = self.priors[param_name]
        
        if prior['type'] == 'normal':
            # 使用3σ规则
            mean = prior['mean']
            std = prior['std']
            return (mean - 3*std, mean + 3*std)
        elif prior['type'] == 'lognormal':
            # 对数正态分布的边界
            mean = prior['mean']
            std = prior['std']
            return (0.01, mean + 3*std)
        elif prior['type'] == 'uniform':
            return (prior['low'], prior['high'])
        elif prior['type'] == 'gamma':
            # Gamma分布通常从0开始
            return (0.01, prior['shape'] * prior['scale'] * 3)
        elif prior['type'] == 'beta':
            return (0.01, 0.99)
        else:
            return (-np.inf, np.inf)
            
    def set_observations(self, observations: np.ndarray, 
                         observation_times: Optional[np.ndarray] = None):
        """
        设置观测数据
        
        Args:
            observations: 观测值数组
            observation_times: 观测时间数组（可选）
        """
        self.observations = np.array(observations)
        if observation_times is not None:
            self.observation_times = np.array(observation_times)
        else:
            self.observation_times = np.arange(len(observations))
            
        self.logger.info(f"Set {len(observations)} observations")
        
    def set_model_function(self, model_function: Callable):
        """
        设置模型函数
        
        Args:
            model_function: 模型函数，接受参数字典和时间，返回模拟值
        """
        self.model_function = model_function
        self.logger.info("Model function set")
        
    def _log_prior(self, params: np.ndarray) -> float:
        """计算先验对数概率"""
        log_prior = 0.0
        param_names = list(self.parameters.keys())
        
        for i, param_name in enumerate(param_names):
            prior = self.priors[param_name]
            value = params[i]
            
            if prior['type'] == 'normal':
                log_prior += norm.logpdf(value, prior['mean'], prior['std'])
            elif prior['type'] == 'lognormal':
                log_prior += lognorm.logpdf(value, prior['std'], scale=np.exp(prior['mean']))
            elif prior['type'] == 'uniform':
                if prior['low'] <= value <= prior['high']:
                    log_prior += uniform.logpdf(value, prior['low'], prior['high'] - prior['low'])
                else:
                    return -np.inf
            elif prior['type'] == 'gamma':
                log_prior += gamma.logpdf(value, prior['shape'], scale=prior['scale'])
            elif prior['type'] == 'beta':
                log_prior += beta.logpdf(value, prior['alpha'], prior['beta'])
                
        return log_prior
        
    def _log_likelihood(self, params: np.ndarray) -> float:
        """计算似然对数概率"""
        if self.model_function is None or self.observations is None:
            return -np.inf
            
        try:
            # 构建参数字典
            param_names = list(self.parameters.keys())
            param_dict = {name: params[i] for i, name in enumerate(param_names)}
            
            # 从参数中分离出误差标准差
            # 假设误差参数名为 'sigma' 或 'error_std'
            if 'sigma' in param_dict:
                error_std = param_dict.pop('sigma')
            elif 'error_std' in param_dict:
                error_std = param_dict.pop('error_std')
            else:
                # 如果没有提供误差参数，则退回到简化模型，但发出警告
                warnings.warn("No error parameter ('sigma' or 'error_std') found. "
                              "Using a simplified, fixed error model.", UserWarning)
                error_std = np.std(self.observations) * 0.1

            # 运行模型
            if self.observation_times is not None:
                simulated = self.model_function(param_dict, self.observation_times)
            else:
                simulated = self.model_function(param_dict)
                
            # 确保输出是数组
            if isinstance(simulated, dict):
                # 取第一个数值输出
                for key, value in simulated.items():
                    if np.isscalar(value) and not isinstance(value, str):
                        simulated = np.full_like(self.observations, value)
                        break
                else:
                    return -np.inf

            # 确保模拟输出和观测值形状匹配
            if simulated.shape != self.observations.shape:
                # 尝试广播，如果失败则返回-inf
                try:
                    simulated = np.broadcast_to(simulated, self.observations.shape)
                except ValueError:
                    self.logger.warning(f"Simulated shape {simulated.shape} does not match "
                                      f"observation shape {self.observations.shape}.")
                    return -np.inf
                    
            # 计算似然（假设正态分布误差）
            log_likelihood = np.sum(norm.logpdf(self.observations, loc=simulated, scale=error_std))
            
            return log_likelihood
            
        except Exception as e:
            self.logger.warning(f"Model evaluation failed: {e}")
            return -np.inf
            
    def _log_probability(self, params: np.ndarray) -> float:
        """计算总对数概率（先验 + 似然）"""
        log_prior = self._log_prior(params)
        
        if not np.isfinite(log_prior):
            return -np.inf
            
        log_likelihood = self._log_likelihood(params)
        
        if not np.isfinite(log_likelihood):
            return -np.inf
            
        return log_prior + log_likelihood
        
    def run_mcmc(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        运行MCMC采样
        
        Args:
            progress_callback: 进度回调函数
            
        Returns:
            MCMC结果字典
        """
        if not self.parameters:
            raise ValueError("No parameters defined")
            
        if self.model_function is None:
            raise ValueError("Model function not set")
            
        if self.observations is None:
            raise ValueError("Observations not set")
            
        self.logger.info("Starting MCMC sampling...")
        start_time = time.time()
        
        n_params = len(self.parameters)
        param_names = list(self.parameters.keys())
        
        # 初始化行走者位置
        initial_positions = self._initialize_walkers(n_params)
        
        # 创建MCMC采样器
        with ProcessPoolExecutor(max_workers=self.n_workers) as pool:
            sampler = emcee.EnsembleSampler(
                self.n_walkers, n_params, self._log_probability,
                pool=pool
            )
            
            # 运行MCMC
            if progress_callback:
                progress_callback(0)

            # 预热阶段
            self.logger.info("Running burn-in phase...")
            pos, prob, state = sampler.run_mcmc(initial_positions, self.n_burn, progress=False)
            
            if progress_callback:
                progress_callback(50)

            # 重置采样器
            sampler.reset()

            # 主采样阶段
            self.logger.info("Running main sampling phase...")
            sampler.run_mcmc(pos, self.n_steps, progress=False)

            if progress_callback:
                progress_callback(100)
            
        # 收集结果
        self.samples = sampler.get_chain(discard=self.n_burn, thin=15, flat=True)
        self.lnprob = sampler.get_log_prob(discard=self.n_burn, thin=15, flat=True)
        self.acceptance_fraction = sampler.acceptance_fraction
        
        # 计算后验统计
        self._calculate_posterior_statistics()
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"MCMC sampling completed in {elapsed_time:.2f}s")
        
        return {
            'samples': self.samples,
            'lnprob': self.lnprob,
            'acceptance_fraction': self.acceptance_fraction,
            'posterior_stats': self.posterior_stats
        }
        
    def _initialize_walkers(self, n_params: int) -> np.ndarray:
        """初始化MCMC行走者位置"""
        initial_positions = np.zeros((self.n_walkers, n_params))
        
        for i in range(self.n_walkers):
            for j, (param_name, param_info) in enumerate(self.parameters.items()):
                bounds = param_info['bounds']
                prior = param_info['prior']
                
                # 根据先验分布生成初始位置
                if prior['type'] == 'normal':
                    initial_positions[i, j] = np.random.normal(prior['mean'], prior['std'])
                elif prior['type'] == 'lognormal':
                    initial_positions[i, j] = np.random.lognormal(prior['mean'], prior['std'])
                elif prior['type'] == 'uniform':
                    initial_positions[i, j] = np.random.uniform(bounds[0], bounds[1])
                elif prior['type'] == 'gamma':
                    initial_positions[i, j] = np.random.gamma(prior['shape'], prior['scale'])
                elif prior['type'] == 'beta':
                    initial_positions[i, j] = np.random.beta(prior['alpha'], prior['beta'])
                    
                # 确保在边界内
                initial_positions[i, j] = np.clip(initial_positions[i, j], bounds[0], bounds[1])
                
        return initial_positions
        
    def _calculate_posterior_statistics(self):
        """计算后验统计信息"""
        if self.samples is None:
            return
            
        param_names = list(self.parameters.keys())
        self.posterior_stats = {}
        
        for i, param_name in enumerate(param_names):
            param_samples = self.samples[:, i]
            
            # 移除无效样本
            valid_samples = param_samples[np.isfinite(param_samples)]
            
            if len(valid_samples) > 0:
                self.posterior_stats[param_name] = {
                    'mean': np.mean(valid_samples),
                    'std': np.std(valid_samples),
                    'median': np.median(valid_samples),
                    'q25': np.percentile(valid_samples, 25),
                    'q75': np.percentile(valid_samples, 75),
                    'q2_5': np.percentile(valid_samples, 2.5),
                    'q97_5': np.percentile(valid_samples, 97.5),
                    'min': np.min(valid_samples),
                    'max': np.max(valid_samples)
                }
            else:
                self.posterior_stats[param_name] = {
                    'mean': np.nan, 'std': np.nan, 'median': np.nan,
                    'q25': np.nan, 'q75': np.nan, 'q2_5': np.nan,
                    'q97_5': np.nan, 'min': np.nan, 'max': np.nan
                }
                
        self.logger.info("Posterior statistics calculated")
        
    def get_credible_intervals(self, confidence_level: float = 0.95) -> Dict[str, Dict]:
        """
        计算可信区间
        
        Args:
            confidence_level: 可信水平
            
        Returns:
            可信区间字典
        """
        if self.posterior_stats is None:
            return {}
            
        alpha = 1 - confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100
        
        credible_intervals = {}
        
        for param_name, stats_dict in self.posterior_stats.items():
            if np.isfinite(stats_dict['q2_5']) and np.isfinite(stats_dict['q97_5']):
                credible_intervals[param_name] = {
                    'lower': stats_dict['q2_5'],
                    'upper': stats_dict['q97_5'],
                    'confidence_level': confidence_level
                }
                
        return credible_intervals
        
    def plot_posterior_distributions(self, figsize: Tuple[int, int] = (15, 10)):
        """
        绘制后验分布图
        
        Args:
            figsize: 图形尺寸
        """
        if self.samples is None:
            self.logger.warning("No MCMC samples available for plotting")
            return
            
        param_names = list(self.parameters.keys())
        n_params = len(param_names)
        
        # 使用corner库绘制后验分布
        fig = corner.corner(
            self.samples,
            labels=param_names,
            quantiles=[0.16, 0.5, 0.84],
            show_titles=True,
            title_kwargs={"fontsize": 12},
            figsize=figsize
        )
        
        return fig
        
    def plot_parameter_traces(self, figsize: Tuple[int, int] = (15, 10)):
        """
        绘制参数轨迹图
        
        Args:
            figsize: 图形尺寸
        """
        if self.samples is None:
            self.logger.warning("No MCMC samples available for plotting")
            return
            
        param_names = list(self.parameters.keys())
        n_params = len(param_names)
        
        n_cols = min(3, n_params)
        n_rows = (n_params + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
        if n_params == 1:
            axes = [axes]
        elif n_rows == 1:
            axes = axes.reshape(1, -1)
        else:
            axes = axes.flatten()
            
        for i, param_name in enumerate(param_names):
            ax = axes[i]
            
            # 绘制每个行走者的轨迹
            for walker in range(min(self.n_walkers, 10)):  # 只显示前10个行走者
                start_idx = walker * self.n_steps
                end_idx = start_idx + self.n_steps
                trace = self.samples[start_idx:end_idx, i]
                ax.plot(trace, alpha=0.5, linewidth=0.5)
                
            ax.set_title(f'{param_name} Trace')
            ax.set_xlabel('MCMC Step')
            ax.set_ylabel('Parameter Value')
            ax.grid(True, alpha=0.3)
            
        # 隐藏多余的子图
        for i in range(n_params, len(axes)):
            axes[i].set_visible(False)
            
        plt.tight_layout()
        return fig
        
    def plot_model_fit(self, figsize: Tuple[int, int] = (12, 8)):
        """
        绘制模型拟合图
        
        Args:
            figsize: 图形尺寸
        """
        if self.samples is None or self.observations is None:
            self.logger.warning("No samples or observations available for plotting")
            return
            
        fig, ax = plt.subplots(figsize=figsize)
        
        # 绘制观测数据
        if self.observation_times is not None:
            ax.scatter(self.observation_times, self.observations, 
                      color='black', s=50, label='Observations', zorder=5)
        else:
            ax.scatter(range(len(self.observations)), self.observations, 
                      color='black', s=50, label='Observations', zorder=5)
            
        # 绘制模型预测区间
        if self.posterior_stats:
            param_names = list(self.parameters.keys())
            
            # 使用后验均值进行预测
            mean_params = {}
            for param_name in param_names:
                if np.isfinite(self.posterior_stats[param_name]['mean']):
                    mean_params[param_name] = self.posterior_stats[param_name]['mean']
                    
            if mean_params:
                try:
                    if self.observation_times is not None:
                        mean_prediction = self.model_function(mean_params, self.observation_times)
                    else:
                        mean_prediction = self.model_function(mean_params)
                        
                    if isinstance(mean_prediction, dict):
                        # 取第一个数值输出
                        for key, value in mean_prediction.items():
                            if np.isscalar(value) and not isinstance(value, str):
                                mean_prediction = np.full_like(self.observations, value)
                                break
                                
                    if self.observation_times is not None:
                        ax.plot(self.observation_times, mean_prediction, 
                               'r-', linewidth=2, label='Model (Posterior Mean)')
                    else:
                        ax.plot(range(len(mean_prediction)), mean_prediction, 
                               'r-', linewidth=2, label='Model (Posterior Mean)')
                        
                except Exception as e:
                    self.logger.warning(f"Failed to plot model fit: {e}")
                    
        ax.set_xlabel('Time' if self.observation_times is not None else 'Index')
        ax.set_ylabel('Value')
        ax.set_title('Model Fit with Observations')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        return fig
        
    def plot_autocorrelation(self, max_lag: int = 100, figsize: Tuple[int, int] = (15, 10)):
        """
        绘制自相关图
        
        Args:
            max_lag: 最大滞后
            figsize: 图形尺寸
        """
        if self.samples is None:
            self.logger.warning("No MCMC samples available for plotting")
            return
            
        param_names = list(self.parameters.keys())
        n_params = len(param_names)
        
        n_cols = min(3, n_params)
        n_rows = (n_params + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
        if n_params == 1:
            axes = [axes]
        elif n_rows == 1:
            axes = axes.reshape(1, -1)
        else:
            axes = axes.flatten()
            
        for i, param_name in enumerate(param_names):
            ax = axes[i]
            
            # 计算自相关
            param_samples = self.samples[:, i]
            valid_samples = param_samples[np.isfinite(param_samples)]
            
            if len(valid_samples) > 0:
                # 使用第一个行走者的样本计算自相关
                walker_samples = valid_samples[:self.n_steps]
                autocorr = np.correlate(walker_samples, walker_samples, mode='full')
                autocorr = autocorr[len(walker_samples)-1:len(walker_samples)-1+max_lag]
                autocorr = autocorr / autocorr[0]  # 归一化
                
                lags = np.arange(max_lag)
                ax.plot(lags, autocorr, 'b-', linewidth=1)
                ax.axhline(y=0, color='k', linestyle='--', alpha=0.5)
                ax.axhline(y=0.1, color='r', linestyle=':', alpha=0.5, label='0.1 threshold')
                ax.axhline(y=-0.1, color='r', linestyle=':', alpha=0.5)
                
            ax.set_title(f'{param_name} Autocorrelation')
            ax.set_xlabel('Lag')
            ax.set_ylabel('Autocorrelation')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
        # 隐藏多余的子图
        for i in range(n_params, len(axes)):
            axes[i].set_visible(False)
            
        plt.tight_layout()
        return fig
        
    def get_effective_sample_size(self) -> Dict[str, int]:
        """
        计算有效样本大小
        
        Returns:
            每个参数的有效样本大小
        """
        if self.samples is None:
            return {}
            
        param_names = list(self.parameters.keys())
        effective_sizes = {}
        
        for i, param_name in enumerate(param_names):
            param_samples = self.samples[:, i]
            valid_samples = param_samples[np.isfinite(param_samples)]
            
            if len(valid_samples) > 0:
                # 计算自相关时间
                autocorr = np.correlate(valid_samples, valid_samples, mode='full')
                autocorr = autocorr[len(valid_samples)-1:]
                autocorr = autocorr / autocorr[0]
                
                # 找到第一个过零点
                zero_crossings = np.where(np.diff(np.sign(autocorr)))[0]
                if len(zero_crossings) > 0:
                    tau = zero_crossings[0]
                else:
                    tau = 1
                    
                # 有效样本大小
                effective_size = len(valid_samples) / (2 * tau + 1)
                effective_sizes[param_name] = int(effective_size)
            else:
                effective_sizes[param_name] = 0
                
        return effective_sizes
        
    def save_results(self, output_dir: str):
        """保存分析结果"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存MCMC样本
        if self.samples is not None:
            param_names = list(self.parameters.keys())
            df = pd.DataFrame(self.samples, columns=param_names)
            df.to_csv(output_path / 'mcmc_samples.csv', index=False)
            
        # 保存后验统计
        if self.posterior_stats:
            with open(output_path / 'posterior_statistics.json', 'w') as f:
                json.dump(self.posterior_stats, f, indent=2, default=str)
                
        # 保存可信区间
        credible_intervals = self.get_credible_intervals()
        if credible_intervals:
            with open(output_path / 'credible_intervals.json', 'w') as f:
                json.dump(credible_intervals, f, indent=2, default=str)
                
        # 保存有效样本大小
        effective_sizes = self.get_effective_sample_size()
        if effective_sizes:
            with open(output_path / 'effective_sample_sizes.json', 'w') as f:
                json.dump(effective_sizes, f, indent=2, default=str)
                
        # 保存图形
        if self.samples is not None:
            # 后验分布图
            fig = self.plot_posterior_distributions()
            if fig:
                fig.savefig(output_path / 'posterior_distributions.png', dpi=300, bbox_inches='tight')
                plt.close(fig)
                
            # 参数轨迹图
            fig = self.plot_parameter_traces()
            if fig:
                fig.savefig(output_path / 'parameter_traces.png', dpi=300, bbox_inches='tight')
                plt.close(fig)
                
            # 自相关图
            fig = self.plot_autocorrelation()
            if fig:
                fig.savefig(output_path / 'autocorrelation.png', dpi=300, bbox_inches='tight')
                plt.close(fig)
                
        # 模型拟合图
        if self.observations is not None:
            fig = self.plot_model_fit()
            if fig:
                fig.savefig(output_path / 'model_fit.png', dpi=300, bbox_inches='tight')
                plt.close(fig)
                
        self.logger.info(f"Bayesian analysis results saved to {output_path}")
        
    def get_summary_report(self) -> str:
        """生成贝叶斯分析摘要报告"""
        report = []
        report.append("=" * 60)
        report.append("BAYESIAN UNCERTAINTY ANALYSIS SUMMARY")
        report.append("=" * 60)
        report.append(f"Number of parameters: {len(self.parameters)}")
        report.append(f"Number of walkers: {self.n_walkers}")
        report.append(f"Number of steps: {self.n_steps}")
        report.append(f"Burn-in steps: {self.n_burn}")
        report.append("")
        
        # 参数和先验信息
        report.append("PARAMETERS AND PRIORS:")
        report.append("-" * 30)
        for param_name, param_info in self.parameters.items():
            prior = param_info['prior']
            bounds = param_info['bounds']
            report.append(f"{param_name}:")
            report.append(f"  Prior: {prior['type']}")
            for key, value in prior.items():
                if key != 'type':
                    report.append(f"    {key}: {value}")
            report.append(f"  Bounds: {bounds}")
        report.append("")
        
        # 后验统计
        if self.posterior_stats:
            report.append("POSTERIOR STATISTICS:")
            report.append("-" * 25)
            for param_name, stats_dict in self.posterior_stats.items():
                report.append(f"\n{param_name}:")
                for stat_name, value in stats_dict.items():
                    if np.isfinite(value):
                        report.append(f"  {stat_name}: {value:.6f}")
                    else:
                        report.append(f"  {stat_name}: NaN")
                        
        # 可信区间
        credible_intervals = self.get_credible_intervals()
        if credible_intervals:
            report.append("\nCREDIBLE INTERVALS (95%):")
            report.append("-" * 30)
            for param_name, interval in credible_intervals.items():
                report.append(f"{param_name}: [{interval['lower']:.6f}, {interval['upper']:.6f}]")
                
        # 有效样本大小
        effective_sizes = self.get_effective_sample_size()
        if effective_sizes:
            report.append("\nEFFECTIVE SAMPLE SIZES:")
            report.append("-" * 25)
            for param_name, size in effective_sizes.items():
                report.append(f"{param_name}: {size}")
                
        # MCMC诊断
        if self.acceptance_fraction is not None:
            report.append(f"\nMCMC DIAGNOSTICS:")
            report.append("-" * 20)
            report.append(f"Acceptance fraction: {np.mean(self.acceptance_fraction):.3f}")
            
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


def example_usage():
    """示例用法"""
    
    # 创建贝叶斯分析器
    analyzer = BayesianUncertaintyAnalyzer(n_walkers=16, n_steps=500, n_burn=100)
    
    # 添加参数和先验
    analyzer.add_parameter('curve_number', 'normal', mean=70, std=10)
    analyzer.add_parameter('impervious_fraction', 'uniform', low=0.05, high=0.25)
    analyzer.add_parameter('storage_capacity', 'gamma', shape=2.0, scale=50.0)
    
    # 添加误差参数
    analyzer.add_parameter('sigma', 'uniform', low=0.1, high=10.0)

    # 设置观测数据
    observations = np.array([45.2, 52.1, 38.9, 61.3, 49.8, 55.2, 42.1, 58.9])
    observation_times = np.array([0, 1, 2, 3, 4, 5, 6, 7])
    
    analyzer.set_observations(observations, observation_times)
    
    # 定义模型函数
    def simple_hydrology_model(params, times):
        """简单的集总式水文模型"""
        cn = params['curve_number']
        imp = params['impervious_fraction']
        sc = params['storage_capacity']
        
        # 模拟降雨-径流过程
        rainfall = 50  # mm
        s = 254 * (100 / cn - 1)  # 潜在最大滞留量
        q = (rainfall - 0.2 * s) ** 2 / (rainfall + 0.8 * s)  # SCS曲线数方法
        
        # 考虑不透水面积
        total_runoff = q * (1 - imp) + rainfall * imp
        
        # 考虑蓄水容量
        actual_runoff = min(total_runoff, sc)
        
        # 添加时间变化（简化）
        time_factor = 1.0 + 0.1 * np.sin(times * np.pi / 4)
        return actual_runoff * time_factor
        
    analyzer.set_model_function(simple_hydrology_model)
    
    # 运行MCMC分析
    def progress_callback(progress):
        print(f"Progress: {progress:.1f}%")
    
    results = analyzer.run_mcmc(progress_callback)
    
    # 生成报告
    print(analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('bayesian_analysis_results')
    
    # 绘制图形
    analyzer.plot_posterior_distributions()
    analyzer.plot_parameter_traces()
    analyzer.plot_model_fit()
    analyzer.plot_autocorrelation()
    plt.show()


if __name__ == "__main__":
    example_usage()

