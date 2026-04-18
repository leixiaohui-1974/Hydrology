"""
Monte Carlo不确定性分析器
========================

提供基于Monte Carlo方法的参数不确定性分析功能，包括：
- 参数空间采样
- 并行化Monte Carlo计算
- 结果统计分析
- 不确定性可视化
"""

import json
import logging
import multiprocessing as mp
import pickle
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from scipy import stats
from scipy.stats import lognorm, norm, triang, uniform


class MonteCarloAnalyzer:
    """
    Monte Carlo不确定性分析器
    """
    
    def __init__(self, n_samples: int = 1000, n_workers: int = None, 
                 random_seed: int = None):
        """
        初始化Monte Carlo分析器
        
        Args:
            n_samples: Monte Carlo采样数量
            n_workers: 并行工作进程数
            random_seed: 随机种子
        """
        self.n_samples = n_samples
        self.n_workers = n_workers or min(mp.cpu_count(), 8)
        self.random_seed = random_seed
        
        # 设置随机种子
        if random_seed is not None:
            np.random.seed(random_seed)
            
        # 参数分布定义
        self.parameter_distributions = {}
        
        # 采样结果
        self.samples = None
        self.model_outputs = None
        self.statistics = None
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
    def add_parameter_distribution(self, param_name: str, 
                                  distribution_type: str, **kwargs):
        """
        添加参数分布定义
        
        Args:
            param_name: 参数名称
            distribution_type: 分布类型 ('normal', 'lognormal', 'uniform', 'triangular')
            **kwargs: 分布参数
        """
        if distribution_type == 'normal':
            self.parameter_distributions[param_name] = {
                'type': 'normal',
                'mean': kwargs.get('mean', 0.0),
                'std': kwargs.get('std', 1.0)
            }
        elif distribution_type == 'lognormal':
            self.parameter_distributions[param_name] = {
                'type': 'lognormal',
                'mean': kwargs.get('mean', 1.0),
                'std': kwargs.get('std', 0.5)
            }
        elif distribution_type == 'uniform':
            self.parameter_distributions[param_name] = {
                'type': 'uniform',
                'low': kwargs.get('low', 0.0),
                'high': kwargs.get('high', 1.0)
            }
        elif distribution_type == 'triangular':
            self.parameter_distributions[param_name] = {
                'type': 'triangular',
                'low': kwargs.get('low', 0.0),
                'high': kwargs.get('high', 1.0),
                'mode': kwargs.get('mode', 0.5)
            }
        else:
            raise ValueError(f"Unsupported distribution type: {distribution_type}")
            
        self.logger.info(f"Added parameter distribution: {param_name} ~ {distribution_type}")
        
    def generate_samples(self) -> pd.DataFrame:
        """
        生成参数样本
        
        Returns:
            参数样本DataFrame
        """
        if not self.parameter_distributions:
            raise ValueError("No parameter distributions defined")
            
        samples = {}
        
        for param_name, dist_config in self.parameter_distributions.items():
            if dist_config['type'] == 'normal':
                samples[param_name] = np.random.normal(
                    dist_config['mean'], dist_config['std'], self.n_samples
                )
            elif dist_config['type'] == 'lognormal':
                samples[param_name] = np.random.lognormal(
                    dist_config['mean'], dist_config['std'], self.n_samples
                )
            elif dist_config['type'] == 'uniform':
                samples[param_name] = np.random.uniform(
                    dist_config['low'], dist_config['high'], self.n_samples
                )
            elif dist_config['type'] == 'triangular':
                samples[param_name] = np.random.triangular(
                    dist_config['low'], dist_config['mode'], dist_config['high'], 
                    self.n_samples
                )
                
        self.samples = pd.DataFrame(samples)
        self.logger.info(f"Generated {self.n_samples} parameter samples")
        
        return self.samples
        
    def run_monte_carlo(self, model_function: Callable, 
                        progress_callback: Optional[Callable] = None) -> pd.DataFrame:
        """
        运行Monte Carlo模拟
        
        Args:
            model_function: 模型函数，接受参数字典，返回输出
            progress_callback: 进度回调函数
            
        Returns:
            模型输出结果DataFrame
        """
        if self.samples is None:
            self.generate_samples()
            
        self.logger.info("Starting Monte Carlo simulation...")
        start_time = time.time()
        
        # 并行执行模型
        outputs = []

        executor_cls = self._get_executor(model_function)
        with executor_cls(max_workers=self.n_workers) as executor:
            # 提交任务
            future_to_index = {
                executor.submit(self._run_single_simulation, row, model_function): i
                for i, row in self.samples.iterrows()
            }

            # 收集结果
            for i, future in enumerate(future_to_index):
                try:
                    result = future.result()
                    outputs.append(result)
                    
                    # 进度回调
                    if progress_callback and (i + 1) % 100 == 0:
                        progress = (i + 1) / self.n_samples * 100
                        progress_callback(progress)
                        
                except Exception as e:
                    self.logger.error(f"Simulation {i} failed: {e}")
                    outputs.append({'error': str(e)})

        # 整理输出结果
        self.model_outputs = pd.DataFrame(outputs)
        if 'error' not in self.model_outputs.columns:
            self.model_outputs['error'] = np.nan
        
        # 计算统计信息
        self._calculate_statistics()
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"Monte Carlo simulation completed in {elapsed_time:.2f}s")
        
        return self.model_outputs
        
    def _get_executor(self, model_function: Callable) -> Any:
        """根据模型函数的可序列化程度选择执行器"""
        if self.n_workers <= 1:
            return ThreadPoolExecutor

        if self._is_picklable(model_function):
            return ProcessPoolExecutor

        self.logger.warning(
            "Model function is not picklable; falling back to ThreadPoolExecutor."
        )
        return ThreadPoolExecutor

    @staticmethod
    def _is_picklable(obj: Callable) -> bool:
        try:
            pickle.dumps(obj)
            return True
        except Exception:
            return False

    def _run_single_simulation(self, parameters: pd.Series,
                              model_function: Callable) -> Dict[str, Any]:
        """
        运行单次模拟
        
        Args:
            parameters: 参数字典
            model_function: 模型函数
            
        Returns:
            模拟结果
        """
        try:
            # 转换参数为字典
            param_dict = parameters.to_dict()
            
            # 运行模型
            result = model_function(param_dict)
            
            # 如果结果是标量，转换为字典
            if np.isscalar(result):
                return {'output': result}
            elif isinstance(result, dict):
                return result
            else:
                return {'output': result}
                
        except Exception as e:
            return {'error': str(e)}
            
    def _calculate_statistics(self):
        """计算统计信息"""
        if self.model_outputs is None:
            return

        # 如果有错误列，则移除错误结果；否则，使用所有输出
        if 'error' in self.model_outputs.columns:
            valid_outputs = self.model_outputs[self.model_outputs['error'].isna()].copy()
        else:
            valid_outputs = self.model_outputs.copy()
        
        if valid_outputs.empty:
            self.logger.warning("No valid outputs for statistics calculation")
            return
            
        # 计算基本统计量
        self.statistics = {}
        
        for col in valid_outputs.columns:
            if col == 'error':
                continue
                
            # 确保列是数值类型
            if pd.api.types.is_numeric_dtype(valid_outputs[col]):
                self.statistics[col] = {
                    'mean': valid_outputs[col].mean(),
                    'std': valid_outputs[col].std(),
                    'min': valid_outputs[col].min(),
                    'max': valid_outputs[col].max(),
                    'median': valid_outputs[col].median(),
                    'q25': valid_outputs[col].quantile(0.25),
                    'q75': valid_outputs[col].quantile(0.75),
                    'skewness': valid_outputs[col].skew(),
                    'kurtosis': valid_outputs[col].kurtosis()
                }
                
        self.logger.info("Statistics calculated successfully")
        
    def get_confidence_intervals(self, confidence_level: float = 0.95) -> Dict[str, Dict]:
        """
        计算置信区间
        
        Args:
            confidence_level: 置信水平
            
        Returns:
            置信区间字典
        """
        if self.statistics is None:
            self._calculate_statistics()
            
        if self.statistics is None:
            return {}
            
        alpha = 1 - confidence_level
        z_score = stats.norm.ppf(1 - alpha / 2)
        
        confidence_intervals = {}
        
        for output_name, stats_dict in self.statistics.items():
            mean = stats_dict['mean']
            std = stats_dict['std']
            
            margin_of_error = z_score * std / np.sqrt(self.n_samples)
            
            confidence_intervals[output_name] = {
                'lower': mean - margin_of_error,
                'upper': mean + margin_of_error,
                'confidence_level': confidence_level
            }
            
        return confidence_intervals
        
    def plot_parameter_distributions(self, figsize: Tuple[int, int] = (12, 8)):
        """
        绘制参数分布图
        
        Args:
            figsize: 图形尺寸
        """
        if self.samples is None:
            self.logger.warning("No samples available for plotting")
            return
            
        n_params = len(self.parameter_distributions)
        n_cols = min(3, n_params)
        n_rows = (n_params + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
        if n_params == 1:
            axes = [axes]
        elif n_rows == 1:
            axes = axes.reshape(1, -1)
        else:
            axes = axes.flatten()
            
        for i, (param_name, dist_config) in enumerate(self.parameter_distributions.items()):
            ax = axes[i]
            
            # 绘制直方图
            ax.hist(self.samples[param_name], bins=30, alpha=0.7, density=True)
            
            # 绘制理论分布
            x = np.linspace(self.samples[param_name].min(), 
                           self.samples[param_name].max(), 100)
            
            if dist_config['type'] == 'normal':
                y = norm.pdf(x, dist_config['mean'], dist_config['std'])
            elif dist_config['type'] == 'lognormal':
                y = lognorm.pdf(x, dist_config['std'], scale=np.exp(dist_config['mean']))
            elif dist_config['type'] == 'uniform':
                y = uniform.pdf(x, dist_config['low'], 
                               dist_config['high'] - dist_config['low'])
            elif dist_config['type'] == 'triangular':
                y = triang.pdf(x, (dist_config['mode'] - dist_config['low']) / 
                              (dist_config['high'] - dist_config['low']), 
                              dist_config['low'], dist_config['high'] - dist_config['low'])
                
            ax.plot(x, y, 'r-', linewidth=2, label='Theoretical')
            
            ax.set_title(f'{param_name} Distribution')
            ax.set_xlabel('Parameter Value')
            ax.set_ylabel('Density')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
        # 隐藏多余的子图
        for i in range(n_params, len(axes)):
            axes[i].set_visible(False)
            
        plt.tight_layout()
        return fig
        
    def plot_output_distributions(self, figsize: Tuple[int, int] = (12, 8)):
        """
        绘制输出分布图
        
        Args:
            figsize: 图形尺寸
        """
        if self.model_outputs is None:
            self.logger.warning("No model outputs available for plotting")
            return
            
        # 移除错误结果
        if 'error' in self.model_outputs.columns:
            valid_outputs = self.model_outputs[self.model_outputs['error'].isna()]
        else:
            valid_outputs = self.model_outputs.copy()

        if valid_outputs.empty:
            self.logger.warning("No valid outputs for plotting")
            return
            
        output_cols = [col for col in valid_outputs.columns if col != 'error']
        n_outputs = len(output_cols)
        
        if n_outputs == 0:
            return
            
        n_cols = min(3, n_outputs)
        n_rows = (n_outputs + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
        axes = np.atleast_1d(axes).ravel()

        for i, col in enumerate(output_cols):
            ax = axes[i]
            
            # 绘制直方图
            ax.hist(valid_outputs[col], bins=30, alpha=0.7, density=True)
            
            # 添加统计信息
            mean_val = valid_outputs[col].mean()
            std_val = valid_outputs[col].std()
            
            ax.axvline(mean_val, color='red', linestyle='--', 
                      label=f'Mean: {mean_val:.3f}')
            ax.axvline(mean_val + std_val, color='orange', linestyle=':', 
                      label=f'+1σ: {mean_val + std_val:.3f}')
            ax.axvline(mean_val - std_val, color='orange', linestyle=':', 
                      label=f'-1σ: {mean_val - std_val:.3f}')
            
            ax.set_title(f'{col} Distribution')
            ax.set_xlabel('Output Value')
            ax.set_ylabel('Density')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
        # 隐藏多余的子图
        for i in range(n_outputs, len(axes)):
            axes[i].set_visible(False)
            
        plt.tight_layout()
        return fig
        
    def plot_scatter_matrix(self, figsize: Tuple[int, int] = (15, 15)):
        """
        绘制参数-输出散点图矩阵
        
        Args:
            figsize: 图形尺寸
        """
        if self.samples is None or self.model_outputs is None:
            self.logger.warning("Samples and outputs required for scatter matrix")
            return
            
        # 合并参数和输出
        combined_data = pd.concat([self.samples, self.model_outputs], axis=1)
        
        # 移除错误列
        if 'error' in combined_data.columns:
            combined_data = combined_data.drop('error', axis=1)
            
        # 创建散点图矩阵
        fig = sns.pairplot(combined_data, diag_kind='kde')
        fig.fig.set_size_inches(figsize)
        
        return fig
        
    def save_results(self, output_dir: str):
        """
        保存分析结果
        
        Args:
            output_dir: 输出目录
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存参数样本
        if self.samples is not None:
            self.samples.to_csv(output_path / 'parameter_samples.csv', index=False)
            
        # 保存模型输出
        if self.model_outputs is not None:
            self.model_outputs.to_csv(output_path / 'model_outputs.csv', index=False)
            
        # 保存统计信息
        if self.statistics is not None:
            with open(output_path / 'statistics.json', 'w') as f:
                json.dump(self.statistics, f, indent=2, default=str)
                
        # 保存置信区间
        confidence_intervals = self.get_confidence_intervals()
        if confidence_intervals:
            with open(output_path / 'confidence_intervals.json', 'w') as f:
                json.dump(confidence_intervals, f, indent=2, default=str)
                
        # 保存分布图
        if self.samples is not None:
            fig = self.plot_parameter_distributions()
            if fig is not None:
                fig.savefig(output_path / 'parameter_distributions.png', dpi=300, bbox_inches='tight')
                plt.close(fig)

        if self.model_outputs is not None:
            fig = self.plot_output_distributions()
            if fig is not None:
                fig.savefig(output_path / 'output_distributions.png', dpi=300, bbox_inches='tight')
                plt.close(fig)
            
        self.logger.info(f"Results saved to {output_path}")
        
    def get_summary_report(self) -> str:
        """
        生成分析摘要报告
        
        Returns:
            摘要报告字符串
        """
        if self.statistics is None:
            return "No analysis results available"
            
        report = []
        report.append("=" * 60)
        report.append("MONTE CARLO UNCERTAINTY ANALYSIS SUMMARY")
        report.append("=" * 60)
        report.append(f"Number of samples: {self.n_samples}")
        report.append(f"Number of parameters: {len(self.parameter_distributions)}")
        report.append(f"Number of outputs: {len(self.statistics)}")
        report.append("")
        
        # 参数信息
        report.append("PARAMETER DISTRIBUTIONS:")
        report.append("-" * 30)
        for param_name, dist_config in self.parameter_distributions.items():
            report.append(f"{param_name}: {dist_config['type']}")
            for key, value in dist_config.items():
                if key != 'type':
                    report.append(f"  {key}: {value}")
        report.append("")
        
        # 输出统计
        report.append("OUTPUT STATISTICS:")
        report.append("-" * 20)
        for output_name, stats_dict in self.statistics.items():
            report.append(f"\n{output_name}:")
            for stat_name, value in stats_dict.items():
                report.append(f"  {stat_name}: {value:.6f}")
                
        # 置信区间
        confidence_intervals = self.get_confidence_intervals()
        if confidence_intervals:
            report.append("\nCONFIDENCE INTERVALS (95%):")
            report.append("-" * 30)
            for output_name, interval in confidence_intervals.items():
                report.append(f"{output_name}: [{interval['lower']:.6f}, {interval['upper']:.6f}]")
                
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


def example_usage():
    """示例用法"""
    
    # 创建分析器
    analyzer = MonteCarloAnalyzer(n_samples=1000, random_seed=42)
    
    # 添加参数分布
    analyzer.add_parameter_distribution('curve_number', 'normal', mean=70, std=10)
    analyzer.add_parameter_distribution('impervious_fraction', 'uniform', low=0.05, high=0.25)
    analyzer.add_parameter_distribution('storage_capacity', 'lognormal', mean=100, std=0.3)
    
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
    
    # 运行Monte Carlo分析
    def progress_callback(progress):
        print(f"Progress: {progress:.1f}%")
    
    results = analyzer.run_monte_carlo(simple_hydrology_model, progress_callback)
    
    # 生成报告
    print(analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('monte_carlo_results')
    
    # 绘制图形
    analyzer.plot_parameter_distributions()
    analyzer.plot_output_distributions()
    analyzer.plot_scatter_matrix()
    plt.show()


if __name__ == "__main__":
    example_usage()

