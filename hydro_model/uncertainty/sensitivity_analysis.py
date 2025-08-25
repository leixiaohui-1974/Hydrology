"""
敏感性分析器
============

提供多种敏感性分析方法，包括：
- Sobol指数计算
- Morris方法
- FAST方法
- 敏感性指标排序和可视化
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Any, Callable
from scipy import stats
from scipy.stats import norm, uniform
import warnings
import logging
from pathlib import Path
import json
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp


class SensitivityAnalyzer:
    """
    敏感性分析器
    """
    
    def __init__(self, n_samples: int = 1000, n_workers: int = None):
        """
        初始化敏感性分析器
        
        Args:
            n_samples: 采样数量
            n_workers: 并行工作进程数
        """
        self.n_samples = n_samples
        self.n_workers = n_workers or min(mp.cpu_count(), 8)
        
        # 参数信息
        self.parameters = {}
        
        # 分析结果
        self.sobol_indices = None
        self.morris_indices = None
        self.fast_indices = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def add_parameter(self, name: str, bounds: Tuple[float, float], 
                     distribution: str = 'uniform'):
        """
        添加参数
        
        Args:
            name: 参数名称
            bounds: 参数范围 (min, max)
            distribution: 参数分布类型
        """
        self.parameters[name] = {
            'bounds': bounds,
            'distribution': distribution
        }
        
    def sobol_analysis(self, model_function: Callable, 
                       progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Sobol敏感性分析
        
        Args:
            model_function: 模型函数
            progress_callback: 进度回调函数
            
        Returns:
            Sobol指数结果
        """
        if not self.parameters:
            raise ValueError("No parameters defined")
            
        self.logger.info("Starting Sobol sensitivity analysis...")
        start_time = time.time()
        
        n_params = len(self.parameters)
        param_names = list(self.parameters.keys())
        
        # 生成采样矩阵
        A = self._generate_sobol_matrix(n_params)
        B = self._generate_sobol_matrix(n_params)
        
        # 计算模型输出
        outputs_A = self._evaluate_model_parallel(A, model_function, progress_callback)
        outputs_B = self._evaluate_model_parallel(B, model_function, progress_callback)
        
        # 计算Sobol指数
        sobol_results = self._calculate_sobol_indices(A, B, outputs_A, outputs_B, param_names)
        
        self.sobol_indices = sobol_results
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Sobol analysis completed in {elapsed_time:.2f}s")
        
        return sobol_results
        
    def _generate_sobol_matrix(self, n_params: int) -> np.ndarray:
        """生成Sobol分析的采样矩阵"""
        matrix = np.random.random((self.n_samples, n_params))
        
        # 根据参数分布调整
        for i, (param_name, param_info) in enumerate(self.parameters.items()):
            bounds = param_info['bounds']
            if param_info['distribution'] == 'uniform':
                matrix[:, i] = bounds[0] + matrix[:, i] * (bounds[1] - bounds[0])
            elif param_info['distribution'] == 'normal':
                mean = (bounds[0] + bounds[1]) / 2
                std = (bounds[1] - bounds[0]) / 6
                matrix[:, i] = stats.norm.ppf(matrix[:, i], mean, std)
                
        return matrix
        
    def _evaluate_model_parallel(self, matrix: np.ndarray, 
                                model_function: Callable,
                                progress_callback: Optional[Callable] = None) -> np.ndarray:
        """并行评估模型"""
        outputs = []
        
        with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
            futures = []
            
            for i in range(self.n_samples):
                params = matrix[i, :]
                param_dict = {name: params[j] for j, name in enumerate(self.parameters.keys())}
                future = executor.submit(self._evaluate_single_run, param_dict, model_function)
                futures.append(future)
                
            # 收集结果
            for i, future in enumerate(futures):
                try:
                    result = future.result()
                    if isinstance(result, dict):
                        # 取第一个数值输出
                        for key, value in result.items():
                            if np.isscalar(value) and not isinstance(value, str):
                                outputs.append(value)
                                break
                    else:
                        outputs.append(result)
                        
                    # 进度回调
                    if progress_callback and (i + 1) % 100 == 0:
                        progress = (i + 1) / self.n_samples * 100
                        progress_callback(progress)
                        
                except Exception as e:
                    self.logger.error(f"Model evaluation {i} failed: {e}")
                    outputs.append(np.nan)
                    
        return np.array(outputs)
        
    def _evaluate_single_run(self, params: Dict[str, float], 
                            model_function: Callable) -> Any:
        """评估单次模型运行"""
        try:
            return model_function(params)
        except Exception as e:
            self.logger.error(f"Model evaluation failed: {e}")
            return np.nan
            
    def _calculate_sobol_indices(self, A: np.ndarray, B: np.ndarray, 
                                outputs_A: np.ndarray, outputs_B: np.ndarray,
                                param_names: List[str]) -> Dict[str, Any]:
        """计算Sobol指数"""
        n_params = len(param_names)
        
        # 计算总方差
        total_variance = np.var(outputs_A)
        
        if total_variance == 0:
            self.logger.warning("Total variance is zero, cannot compute Sobol indices")
            return {}
            
        # 计算一阶敏感性指数
        first_order_indices = {}
        total_order_indices = {}
        
        for i in range(n_params):
            # 创建ABi矩阵（B矩阵的第i列替换为A矩阵的第i列）
            ABi = B.copy()
            ABi[:, i] = A[:, i]
            
            # 评估ABi矩阵
            outputs_ABi = self._evaluate_model_parallel(ABi, 
                                                      lambda x: self._extract_output(x, i, A, B, outputs_A, outputs_B))
            
            # 计算一阶指数
            f0 = np.mean(outputs_A)
            f1 = np.mean(outputs_B)
            f2 = np.mean(outputs_ABi)
            
            # 一阶指数
            first_order = np.cov(outputs_A, outputs_ABi)[0, 1] / total_variance
            first_order_indices[param_names[i]] = max(0, first_order)
            
            # 总指数（简化计算）
            total_order = 1 - np.cov(outputs_B, outputs_ABi)[0, 1] / total_variance
            total_order_indices[param_names[i]] = max(0, total_order)
            
        # 计算二阶指数（简化版本）
        second_order_indices = {}
        for i in range(n_params):
            for j in range(i + 1, n_params):
                # 创建ABij矩阵
                ABij = B.copy()
                ABij[:, i] = A[:, i]
                ABij[:, j] = A[:, j]
                
                outputs_ABij = self._evaluate_model_parallel(ABij, 
                                                          lambda x: self._extract_output(x, i, A, B, outputs_A, outputs_B))
                
                # 二阶指数
                second_order = (np.cov(outputs_A, outputs_ABij)[0, 1] - 
                               first_order_indices[param_names[i]] - 
                               first_order_indices[param_names[j]]) / total_variance
                second_order_indices[f"{param_names[i]}_{param_names[j]}"] = max(0, second_order)
                
        return {
            'first_order': first_order_indices,
            'second_order': second_order_indices,
            'total_order': total_order_indices,
            'total_variance': total_variance
        }
        
    def _extract_output(self, x: Dict[str, float], i: int, A: np.ndarray, B: np.ndarray,
                        outputs_A: np.ndarray, outputs_B: np.ndarray) -> float:
        """提取输出值（用于并行计算）"""
        # 这是一个辅助函数，实际实现中需要根据具体情况调整
        return outputs_A[i] if i < len(outputs_A) else outputs_B[i]
        
    def morris_analysis(self, model_function: Callable, 
                       r: int = 10, delta: float = 0.5,
                       progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Morris敏感性分析
        
        Args:
            model_function: 模型函数
            r: 轨迹数量
            delta: 步长
            progress_callback: 进度回调函数
            
        Returns:
            Morris指数结果
        """
        if not self.parameters:
            raise ValueError("No parameters defined")
            
        self.logger.info("Starting Morris sensitivity analysis...")
        start_time = time.time()
        
        n_params = len(self.parameters)
        param_names = list(self.parameters.keys())
        
        # 生成Morris轨迹
        trajectories = self._generate_morris_trajectories(n_params, r, delta)
        
        # 计算基本效应
        basic_effects = []
        
        for traj_idx, trajectory in enumerate(trajectories):
            traj_effects = []
            
            for i in range(len(trajectory) - 1):
                # 计算相邻点之间的基本效应
                params1 = trajectory[i]
                params2 = trajectory[i + 1]
                
                # 评估模型
                output1 = self._evaluate_single_run(params1, model_function)
                output2 = self._evaluate_single_run(params2, model_function)
                
                if isinstance(output1, dict):
                    output1 = list(output1.values())[0]
                if isinstance(output2, dict):
                    output2 = list(output2.values())[0]
                    
                # 计算基本效应
                effect = (output2 - output1) / delta
                traj_effects.append(effect)
                
                # 进度回调
                if progress_callback:
                    progress = (traj_idx * len(trajectory) + i) / (len(trajectories) * len(trajectory)) * 100
                    progress_callback(progress)
                    
            basic_effects.append(traj_effects)
            
        # 计算Morris指数
        morris_results = self._calculate_morris_indices(basic_effects, param_names, r)
        
        self.morris_indices = morris_results
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Morris analysis completed in {elapsed_time:.2f}s")
        
        return morris_results
        
    def _generate_morris_trajectories(self, n_params: int, r: int, delta: float) -> List[List[Dict[str, float]]]:
        """生成Morris轨迹"""
        trajectories = []
        
        for _ in range(r):
            # 随机选择起始点
            start_point = {}
            for param_name, param_info in self.parameters.items():
                bounds = param_info['bounds']
                if param_info['distribution'] == 'uniform':
                    start_point[param_name] = np.random.uniform(bounds[0], bounds[1])
                elif param_info['distribution'] == 'normal':
                    mean = (bounds[0] + bounds[1]) / 2
                    std = (bounds[1] - bounds[0]) / 6
                    start_point[param_name] = np.random.normal(mean, std)
                    
            # 生成轨迹
            trajectory = [start_point.copy()]
            current_point = start_point.copy()
            
            # 随机排列参数顺序
            param_order = np.random.permutation(list(self.parameters.keys()))
            
            for param_name in param_order:
                param_info = self.parameters[param_name]
                bounds = param_info['bounds']
                
                # 计算新值
                if np.random.random() < 0.5:
                    new_value = current_point[param_name] + delta * (bounds[1] - bounds[0])
                else:
                    new_value = current_point[param_name] - delta * (bounds[1] - bounds[0])
                    
                # 确保在边界内
                new_value = np.clip(new_value, bounds[0], bounds[1])
                
                # 更新点
                current_point[param_name] = new_value
                trajectory.append(current_point.copy())
                
            trajectories.append(trajectory)
            
        return trajectories
        
    def _calculate_morris_indices(self, basic_effects: List[List[float]], 
                                 param_names: List[str], r: int) -> Dict[str, Any]:
        """计算Morris指数"""
        n_params = len(param_names)
        
        # 计算每个参数的基本效应
        param_effects = {name: [] for name in param_names}
        
        for traj_effects in basic_effects:
            for i, effect in enumerate(traj_effects):
                if i < len(param_names):
                    param_effects[param_names[i]].append(effect)
                    
        # 计算μ*（平均绝对效应）
        mu_star = {}
        for param_name, effects in param_effects.items():
            if effects:
                mu_star[param_name] = np.mean(np.abs(effects))
            else:
                mu_star[param_name] = 0.0
                
        # 计算μ（平均效应）
        mu = {}
        for param_name, effects in param_effects.items():
            if effects:
                mu[param_name] = np.mean(effects)
            else:
                mu[param_name] = 0.0
                
        # 计算σ（标准差）
        sigma = {}
        for param_name, effects in param_effects.items():
            if effects:
                sigma[param_name] = np.std(effects)
            else:
                sigma[param_name] = 0.0
                
        return {
            'mu_star': mu_star,  # 平均绝对效应
            'mu': mu,            # 平均效应
            'sigma': sigma,      # 标准差
            'r': r,              # 轨迹数量
            'delta': 0.5         # 步长
        }
        
    def fast_analysis(self, model_function: Callable, 
                     M: int = 4, omega: float = 2.0,
                     progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        FAST敏感性分析
        
        Args:
            model_function: 模型函数
            M: 谐波数量
            omega: 基础频率
            progress_callback: 进度回调函数
            
        Returns:
            FAST指数结果
        """
        if not self.parameters:
            raise ValueError("No parameters defined")
            
        self.logger.info("Starting FAST sensitivity analysis...")
        start_time = time.time()
        
        n_params = len(self.parameters)
        param_names = list(self.parameters.keys())
        
        # 生成FAST采样
        samples = self._generate_fast_samples(n_params, M, omega)
        
        # 评估模型
        outputs = self._evaluate_model_parallel(samples, model_function, progress_callback)
        
        # 计算FAST指数
        fast_results = self._calculate_fast_indices(samples, outputs, param_names, M, omega)
        
        self.fast_indices = fast_results
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"FAST analysis completed in {elapsed_time:.2f}s")
        
        return fast_results
        
    def _generate_fast_samples(self, n_params: int, M: int, omega: float) -> np.ndarray:
        """生成FAST采样"""
        # 为每个参数分配不同的频率
        frequencies = [omega ** i for i in range(n_params)]
        
        # 生成采样点
        t = np.linspace(0, 2 * np.pi, self.n_samples)
        samples = np.zeros((self.n_samples, n_params))
        
        for i in range(n_params):
            param_info = list(self.parameters.values())[i]
            bounds = param_info['bounds']
            
            # 生成正弦变换
            s = np.sin(frequencies[i] * t)
            
            # 映射到参数空间
            if param_info['distribution'] == 'uniform':
                samples[:, i] = bounds[0] + (s + 1) / 2 * (bounds[1] - bounds[0])
            elif param_info['distribution'] == 'normal':
                mean = (bounds[0] + bounds[1]) / 2
                std = (bounds[1] - bounds[0]) / 6
                samples[:, i] = stats.norm.ppf((s + 1) / 2, mean, std)
                
        return samples
        
    def _calculate_fast_indices(self, samples: np.ndarray, outputs: np.ndarray,
                               param_names: List[str], M: int, omega: float) -> Dict[str, Any]:
        """计算FAST指数"""
        n_params = len(param_names)
        frequencies = [omega ** i for i in range(n_params)]
        
        # 计算总方差
        total_variance = np.var(outputs)
        
        if total_variance == 0:
            self.logger.warning("Total variance is zero, cannot compute FAST indices")
            return {}
            
        # 计算每个参数的敏感性指数
        sensitivity_indices = {}
        
        for i in range(n_params):
            freq = frequencies[i]
            
            # 计算傅里叶系数
            coeffs = np.fft.fft(outputs)
            
            # 找到对应频率的系数
            freq_idx = int(freq * self.n_samples / (2 * np.pi))
            
            if freq_idx < len(coeffs) // 2:
                # 计算敏感性指数
                power = np.abs(coeffs[freq_idx]) ** 2
                sensitivity = power / total_variance
                sensitivity_indices[param_names[i]] = sensitivity
            else:
                sensitivity_indices[param_names[i]] = 0.0
                
        return {
            'sensitivity_indices': sensitivity_indices,
            'total_variance': total_variance,
            'M': M,
            'omega': omega
        }
        
    def plot_sensitivity_results(self, method: str = 'all', 
                               figsize: Tuple[int, int] = (15, 10)):
        """
        绘制敏感性分析结果
        
        Args:
            method: 分析方法 ('sobol', 'morris', 'fast', 'all')
            figsize: 图形尺寸
        """
        if method == 'all':
            methods = ['sobol', 'morris', 'fast']
        else:
            methods = [method]
            
        n_methods = len(methods)
        fig, axes = plt.subplots(1, n_methods, figsize=figsize)
        
        if n_methods == 1:
            axes = [axes]
            
        for i, method_name in enumerate(methods):
            ax = axes[i]
            
            if method_name == 'sobol' and self.sobol_indices:
                self._plot_sobol_results(ax)
            elif method_name == 'morris' and self.morris_indices:
                self._plot_morris_results(ax)
            elif method_name == 'fast' and self.fast_indices:
                self._plot_fast_results(ax)
            else:
                ax.text(0.5, 0.5, f'No {method_name} results available', 
                       ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f'{method_name.upper()} Results')
                
        plt.tight_layout()
        return fig
        
    def _plot_sobol_results(self, ax):
        """绘制Sobol结果"""
        if not self.sobol_indices:
            return
            
        first_order = self.sobol_indices['first_order']
        total_order = self.sobol_indices['total_order']
        
        param_names = list(first_order.keys())
        first_values = list(first_order.values())
        total_values = list(total_order.values())
        
        x = np.arange(len(param_names))
        width = 0.35
        
        ax.bar(x - width/2, first_values, width, label='First Order', alpha=0.8)
        ax.bar(x + width/2, total_values, width, label='Total Order', alpha=0.8)
        
        ax.set_xlabel('Parameters')
        ax.set_ylabel('Sensitivity Index')
        ax.set_title('Sobol Sensitivity Indices')
        ax.set_xticks(x)
        ax.set_xticklabels(param_names, rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
    def _plot_morris_results(self, ax):
        """绘制Morris结果"""
        if not self.morris_indices:
            return
            
        mu_star = self.morris_indices['mu_star']
        sigma = self.morris_indices['sigma']
        
        param_names = list(mu_star.keys())
        mu_star_values = list(mu_star.values())
        sigma_values = list(sigma.values())
        
        # 散点图：μ* vs σ
        ax.scatter(mu_star_values, sigma_values, s=100, alpha=0.7)
        
        # 添加参数标签
        for i, param_name in enumerate(param_names):
            ax.annotate(param_name, (mu_star_values[i], sigma_values[i]), 
                       xytext=(5, 5), textcoords='offset points')
            
        ax.set_xlabel('μ* (Mean Absolute Effect)')
        ax.set_ylabel('σ (Standard Deviation)')
        ax.set_title('Morris Sensitivity Analysis')
        ax.grid(True, alpha=0.3)
        
    def _plot_fast_results(self, ax):
        """绘制FAST结果"""
        if not self.fast_indices:
            return
            
        sensitivity = self.fast_indices['sensitivity_indices']
        
        param_names = list(sensitivity.keys())
        sensitivity_values = list(sensitivity.values())
        
        # 条形图
        bars = ax.bar(param_names, sensitivity_values, alpha=0.8)
        
        # 添加数值标签
        for bar, value in zip(bars, sensitivity_values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{value:.3f}', ha='center', va='bottom')
            
        ax.set_xlabel('Parameters')
        ax.set_ylabel('Sensitivity Index')
        ax.set_title('FAST Sensitivity Indices')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, alpha=0.3)
        
    def get_sensitivity_ranking(self, method: str = 'sobol') -> pd.DataFrame:
        """
        获取敏感性排序
        
        Args:
            method: 分析方法
            
        Returns:
            排序后的敏感性指数DataFrame
        """
        if method == 'sobol' and self.sobol_indices:
            first_order = self.sobol_indices['first_order']
            total_order = self.sobol_indices['total_order']
            
            df = pd.DataFrame({
                'Parameter': list(first_order.keys()),
                'First_Order': list(first_order.values()),
                'Total_Order': list(total_order.values())
            })
            
            df = df.sort_values('First_Order', ascending=False)
            
        elif method == 'morris' and self.morris_indices:
            mu_star = self.morris_indices['mu_star']
            mu = self.morris_indices['mu']
            sigma = self.morris_indices['sigma']
            
            df = pd.DataFrame({
                'Parameter': list(mu_star.keys()),
                'Mu_Star': list(mu_star.values()),
                'Mu': list(mu.values()),
                'Sigma': list(sigma.values())
            })
            
            df = df.sort_values('Mu_Star', ascending=False)
            
        elif method == 'fast' and self.fast_indices:
            sensitivity = self.fast_indices['sensitivity_indices']
            
            df = pd.DataFrame({
                'Parameter': list(sensitivity.keys()),
                'Sensitivity_Index': list(sensitivity.values())
            })
            
            df = df.sort_values('Sensitivity_Index', ascending=False)
            
        else:
            return pd.DataFrame()
            
        return df
        
    def save_results(self, output_dir: str):
        """保存分析结果"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存Sobol结果
        if self.sobol_indices:
            with open(output_path / 'sobol_indices.json', 'w') as f:
                json.dump(self.sobol_indices, f, indent=2, default=str)
                
        # 保存Morris结果
        if self.morris_indices:
            with open(output_path / 'morris_indices.json', 'w') as f:
                json.dump(self.morris_indices, f, indent=2, default=str)
                
        # 保存FAST结果
        if self.fast_indices:
            with open(output_path / 'fast_indices.json', 'w') as f:
                json.dump(self.fast_indices, f, indent=2, default=str)
                
        # 保存敏感性排序
        for method in ['sobol', 'morris', 'fast']:
            ranking = self.get_sensitivity_ranking(method)
            if not ranking.empty:
                ranking.to_csv(output_path / f'{method}_ranking.csv', index=False)
                
        # 保存图形
        fig = self.plot_sensitivity_results()
        if fig:
            fig.savefig(output_path / 'sensitivity_analysis.png', dpi=300, bbox_inches='tight')
            plt.close(fig)
            
        self.logger.info(f"Sensitivity analysis results saved to {output_path}")
        
    def get_summary_report(self) -> str:
        """生成敏感性分析摘要报告"""
        report = []
        report.append("=" * 60)
        report.append("SENSITIVITY ANALYSIS SUMMARY")
        report.append("=" * 60)
        report.append(f"Number of parameters: {len(self.parameters)}")
        report.append(f"Number of samples: {self.n_samples}")
        report.append("")
        
        # 参数信息
        report.append("PARAMETERS:")
        report.append("-" * 20)
        for param_name, param_info in self.parameters.items():
            bounds = param_info['bounds']
            dist = param_info['distribution']
            report.append(f"{param_name}: {dist} distribution, bounds: {bounds}")
        report.append("")
        
        # Sobol结果
        if self.sobol_indices:
            report.append("SOBOL INDICES:")
            report.append("-" * 20)
            ranking = self.get_sensitivity_ranking('sobol')
            for _, row in ranking.iterrows():
                report.append(f"{row['Parameter']}: First={row['First_Order']:.4f}, Total={row['Total_Order']:.4f}")
            report.append("")
            
        # Morris结果
        if self.morris_indices:
            report.append("MORRIS INDICES:")
            report.append("-" * 20)
            ranking = self.get_sensitivity_ranking('morris')
            for _, row in ranking.iterrows():
                report.append(f"{row['Parameter']}: μ*={row['Mu_Star']:.4f}, σ={row['Sigma']:.4f}")
            report.append("")
            
        # FAST结果
        if self.fast_indices:
            report.append("FAST INDICES:")
            report.append("-" * 20)
            ranking = self.get_sensitivity_ranking('fast')
            for _, row in ranking.iterrows():
                report.append(f"{row['Parameter']}: Sensitivity={row['Sensitivity_Index']:.4f}")
            report.append("")
            
        report.append("=" * 60)
        
        return "\n".join(report)


def example_usage():
    """示例用法"""
    
    # 创建敏感性分析器
    analyzer = SensitivityAnalyzer(n_samples=1000)
    
    # 添加参数
    analyzer.add_parameter('curve_number', (50, 90), 'uniform')
    analyzer.add_parameter('impervious_fraction', (0.05, 0.25), 'uniform')
    analyzer.add_parameter('storage_capacity', (50, 150), 'uniform')
    
    # 定义模型函数
    def simple_hydrology_model(params):
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
        
        return {
            'total_runoff': total_runoff,
            'actual_runoff': actual_runoff,
            'storage_used': actual_runoff / sc
        }
    
    # 运行敏感性分析
    def progress_callback(progress):
        print(f"Progress: {progress:.1f}%")
    
    # Sobol分析
    print("Running Sobol analysis...")
    sobol_results = analyzer.sobol_analysis(simple_hydrology_model, progress_callback)
    
    # Morris分析
    print("Running Morris analysis...")
    morris_results = analyzer.morris_analysis(simple_hydrology_model, progress_callback)
    
    # FAST分析
    print("Running FAST analysis...")
    fast_results = analyzer.fast_analysis(simple_hydrology_model, progress_callback)
    
    # 生成报告
    print(analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('sensitivity_analysis_results')
    
    # 绘制图形
    analyzer.plot_sensitivity_results()
    plt.show()


if __name__ == "__main__":
    example_usage()

