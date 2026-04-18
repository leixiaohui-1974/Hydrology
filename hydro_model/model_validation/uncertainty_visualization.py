"""
不确定性可视化模块
==================

本模块提供水文模型的不确定性可视化功能，包括：
- 置信区间显示
- 不确定性带显示
- 概率分布图
- 敏感性分析图
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Union, Any
import logging
from scipy import stats
import json

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class ConfidenceIntervalVisualizer:
    """置信区间可视化器"""
    
    def __init__(self):
        self.visualization_data = {}
        logger.info("ConfidenceIntervalVisualizer initialized")
    
    def visualize_confidence_intervals(self, observed: np.ndarray, simulated: np.ndarray,
                                     confidence_level: float = 0.95,
                                     time_index: Optional[np.ndarray] = None,
                                     title: str = "置信区间可视化") -> Dict[str, Any]:
        """可视化置信区间"""
        logger.info("开始置信区间可视化")
        
        try:
            # 数据预处理
            observed, simulated, time_index = self._preprocess_data(observed, simulated, time_index)
            
            # 计算置信区间
            confidence_intervals = self._calculate_confidence_intervals(observed, simulated, confidence_level)
            
            # 存储可视化数据
            self.visualization_data = {
                'observed': observed,
                'simulated': simulated,
                'time_index': time_index,
                'confidence_intervals': confidence_intervals,
                'confidence_level': confidence_level,
                'title': title
            }
            
            logger.info("置信区间可视化完成")
            return confidence_intervals
            
        except Exception as e:
            logger.error(f"置信区间可视化失败: {e}")
            return {}
    
    def _preprocess_data(self, observed: np.ndarray, simulated: np.ndarray,
                         time_index: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """数据预处理"""
        # 确保数据类型
        observed = np.array(observed, dtype=float)
        simulated = np.array(simulated, dtype=float)
        
        # 检查数据长度
        if len(observed) != len(simulated):
            raise ValueError("观测数据和模拟数据长度不一致")
        
        # 生成时间索引（如果没有提供）
        if time_index is None:
            time_index = np.arange(len(observed))
        else:
            time_index = np.array(time_index)
        
        return observed, simulated, time_index
    
    def _calculate_confidence_intervals(self, observed: np.ndarray, simulated: np.ndarray,
                                       confidence_level: float) -> Dict[str, np.ndarray]:
        """计算置信区间"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 计算残差
        residuals = sim - obs
        
        # 计算残差的均值和标准差
        residual_mean = np.mean(residuals)
        residual_std = np.std(residuals)
        
        # 计算置信区间
        alpha = 1 - confidence_level
        z_score = stats.norm.ppf(1 - alpha / 2)
        
        # 预测区间
        prediction_interval_lower = sim - z_score * residual_std
        prediction_interval_upper = sim + z_score * residual_std
        
        # 置信区间（均值）
        confidence_interval_lower = sim - z_score * residual_std / np.sqrt(len(obs))
        confidence_interval_upper = sim + z_score * residual_std / np.sqrt(len(obs))
        
        return {
            'prediction_interval_lower': prediction_interval_lower,
            'prediction_interval_upper': prediction_interval_upper,
            'confidence_interval_lower': confidence_interval_lower,
            'confidence_interval_upper': confidence_interval_upper,
            'residual_mean': residual_mean,
            'residual_std': residual_std,
            'z_score': z_score
        }
    
    def plot_confidence_intervals(self, save_path: Optional[str] = None,
                                 figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制置信区间图"""
        if not self.visualization_data:
            raise ValueError("请先运行置信区间可视化")
        
        try:
            observed = self.visualization_data['observed']
            simulated = self.visualization_data['simulated']
            time_index = self.visualization_data['time_index']
            confidence_intervals = self.visualization_data['confidence_intervals']
            confidence_level = self.visualization_data['confidence_level']
            title = self.visualization_data['title']
            
            # 创建图形
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)
            
            # 主图：观测值、模拟值和置信区间
            ax1.plot(time_index, observed, 'b-', label='观测值', linewidth=2, alpha=0.8)
            ax1.plot(time_index, simulated, 'r--', label='模拟值', linewidth=2, alpha=0.8)
            
            # 绘制预测区间
            if 'prediction_interval_lower' in confidence_intervals:
                ax1.fill_between(time_index, 
                                confidence_intervals['prediction_interval_lower'],
                                confidence_intervals['prediction_interval_upper'],
                                alpha=0.3, color='red', label=f'{confidence_level*100:.0f}%预测区间')
            
            # 绘制置信区间
            if 'confidence_interval_lower' in confidence_intervals:
                ax1.fill_between(time_index,
                                confidence_intervals['confidence_interval_lower'],
                                confidence_intervals['confidence_interval_upper'],
                                alpha=0.2, color='green', label=f'{confidence_level*100:.0f}%置信区间')
            
            ax1.set_xlabel('时间')
            ax1.set_ylabel('数值')
            ax1.set_title(f'{title} - 置信区间分析')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 残差图
            residuals = simulated - observed
            ax2.plot(time_index, residuals, 'g-', linewidth=1, alpha=0.7, label='残差')
            ax2.axhline(y=0, color='k', linestyle='--', alpha=0.5)
            
            # 添加残差置信区间
            if 'residual_std' in confidence_intervals:
                residual_std = confidence_intervals['residual_std']
                z_score = confidence_intervals['z_score']
                
                ax2.fill_between(time_index,
                                -z_score * residual_std,
                                z_score * residual_std,
                                alpha=0.3, color='green', label=f'{confidence_level*100:.0f}%残差区间')
            
            ax2.set_xlabel('时间')
            ax2.set_ylabel('残差 (模拟值 - 观测值)')
            ax2.set_title('残差分析')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # 添加统计信息
            if confidence_intervals:
                stats_text = f"残差均值: {confidence_intervals.get('residual_mean', np.nan):.4f}\n"
                stats_text += f"残差标准差: {confidence_intervals.get('residual_std', np.nan):.4f}\n"
                stats_text += f"置信水平: {confidence_level*100:.0f}%\n"
                stats_text += f"Z分数: {confidence_intervals.get('z_score', np.nan):.2f}"
                
                ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"置信区间图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制置信区间图失败: {e}")
            raise

class UncertaintyBandVisualizer:
    """不确定性带可视化器"""
    
    def __init__(self):
        self.uncertainty_data = {}
        logger.info("UncertaintyBandVisualizer initialized")
    
    def visualize_uncertainty_bands(self, observed: np.ndarray, simulated: np.ndarray,
                                   uncertainty_ranges: Optional[np.ndarray] = None,
                                   time_index: Optional[np.ndarray] = None,
                                   title: str = "不确定性带可视化") -> Dict[str, Any]:
        """可视化不确定性带"""
        logger.info("开始不确定性带可视化")
        
        try:
            # 数据预处理
            observed, simulated, time_index = self._preprocess_data(observed, simulated, time_index)
            
            # 计算不确定性带（如果没有提供）
            if uncertainty_ranges is None:
                uncertainty_ranges = self._calculate_uncertainty_ranges(observed, simulated)
            
            # 存储不确定性数据
            self.uncertainty_data = {
                'observed': observed,
                'simulated': simulated,
                'time_index': time_index,
                'uncertainty_ranges': uncertainty_ranges,
                'title': title
            }
            
            logger.info("不确定性带可视化完成")
            return uncertainty_ranges
            
        except Exception as e:
            logger.error(f"不确定性带可视化失败: {e}")
            return {}
    
    def _preprocess_data(self, observed: np.ndarray, simulated: np.ndarray,
                         time_index: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """数据预处理"""
        # 确保数据类型
        observed = np.array(observed, dtype=float)
        simulated = np.array(simulated, dtype=float)
        
        # 检查数据长度
        if len(observed) != len(simulated):
            raise ValueError("观测数据和模拟数据长度不一致")
        
        # 生成时间索引（如果没有提供）
        if time_index is None:
            time_index = np.arange(len(observed))
        else:
            time_index = np.array(time_index)
        
        return observed, simulated, time_index
    
    def _calculate_uncertainty_ranges(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, np.ndarray]:
        """计算不确定性范围"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 计算残差
        residuals = sim - obs
        
        # 计算残差的标准差
        residual_std = np.std(residuals)
        
        # 计算不确定性带
        uncertainty_band_1sigma = residual_std
        uncertainty_band_2sigma = 2 * residual_std
        uncertainty_band_3sigma = 3 * residual_std
        
        return {
            'uncertainty_band_1sigma': uncertainty_band_1sigma,
            'uncertainty_band_2sigma': uncertainty_band_2sigma,
            'uncertainty_band_3sigma': uncertainty_band_3sigma,
            'residual_std': residual_std
        }
    
    def plot_uncertainty_bands(self, save_path: Optional[str] = None,
                              figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制不确定性带图"""
        if not self.uncertainty_data:
            raise ValueError("请先运行不确定性带可视化")
        
        try:
            observed = self.uncertainty_data['observed']
            simulated = self.uncertainty_data['simulated']
            time_index = self.uncertainty_data['time_index']
            uncertainty_ranges = self.uncertainty_data['uncertainty_ranges']
            title = self.uncertainty_data['title']
            
            # 创建图形
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)
            
            # 主图：观测值、模拟值和不确定性带
            ax1.plot(time_index, observed, 'b-', label='观测值', linewidth=2, alpha=0.8)
            ax1.plot(time_index, simulated, 'r--', label='模拟值', linewidth=2, alpha=0.8)
            
            # 绘制不确定性带
            if 'residual_std' in uncertainty_ranges:
                residual_std = uncertainty_ranges['residual_std']
                
                # 1σ不确定性带
                ax1.fill_between(time_index,
                                simulated - residual_std,
                                simulated + residual_std,
                                alpha=0.3, color='yellow', label='±1σ不确定性带')
                
                # 2σ不确定性带
                ax1.fill_between(time_index,
                                simulated - 2 * residual_std,
                                simulated + 2 * residual_std,
                                alpha=0.2, color='orange', label='±2σ不确定性带')
                
                # 3σ不确定性带
                ax1.fill_between(time_index,
                                simulated - 3 * residual_std,
                                simulated + 3 * residual_std,
                                alpha=0.1, color='red', label='±3σ不确定性带')
            
            ax1.set_xlabel('时间')
            ax1.set_ylabel('数值')
            ax1.set_title(f'{title} - 不确定性带分析')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 不确定性量化图
            if 'residual_std' in uncertainty_ranges:
                residual_std = uncertainty_ranges['residual_std']
                
                # 计算每个时间点的观测值是否在不确定性带内
                within_1sigma = np.abs(simulated - observed) <= residual_std
                within_2sigma = np.abs(simulated - observed) <= 2 * residual_std
                within_3sigma = np.abs(simulated - observed) <= 3 * residual_std
                
                # 计算覆盖率
                coverage_1sigma = np.mean(within_1sigma) * 100
                coverage_2sigma = np.mean(within_2sigma) * 100
                coverage_3sigma = np.mean(within_3sigma) * 100
                
                # 绘制覆盖率
                sigma_levels = ['1σ', '2σ', '3σ']
                coverages = [coverage_1sigma, coverage_2sigma, coverage_3sigma]
                
                bars = ax2.bar(sigma_levels, coverages, color=['yellow', 'orange', 'red'], alpha=0.7)
                ax2.set_ylabel('覆盖率 (%)')
                ax2.set_title('不确定性带覆盖率')
                ax2.grid(True, alpha=0.3)
                
                # 添加覆盖率标签
                for bar, coverage in zip(bars, coverages):
                    height = bar.get_height()
                    ax2.text(bar.get_x() + bar.get_width()/2., height + 1,
                             f'{coverage:.1f}%', ha='center', va='bottom')
                
                # 添加理论覆盖率
                theoretical_coverage = [68.27, 95.45, 99.73]
                ax2.plot(sigma_levels, theoretical_coverage, 'k--', marker='o', 
                         label='理论覆盖率', linewidth=2)
                ax2.legend()
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"不确定性带图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制不确定性带图失败: {e}")
            raise

class ProbabilityDistributionPlotter:
    """概率分布图绘制器"""
    
    def __init__(self):
        self.distribution_data = {}
        logger.info("ProbabilityDistributionPlotter initialized")
    
    def plot_probability_distributions(self, observed: np.ndarray, simulated: np.ndarray,
                                     title: str = "概率分布分析",
                                     save_path: Optional[str] = None,
                                     figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制概率分布图"""
        logger.info("开始概率分布分析")
        
        try:
            # 数据预处理
            observed = np.array(observed, dtype=float)
            simulated = np.array(simulated, dtype=float)
            
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                raise ValueError("没有有效数据进行概率分布分析")
            
            # 存储分布数据
            self.distribution_data = {
                'observed': obs,
                'simulated': sim,
                'title': title
            }
            
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 1. 直方图对比
            ax1.hist(obs, bins=30, alpha=0.7, label='观测值', color='blue', density=True)
            ax1.hist(sim, bins=30, alpha=0.7, label='模拟值', color='red', density=True)
            ax1.set_xlabel('数值')
            ax1.set_ylabel('概率密度')
            ax1.set_title('概率密度分布对比')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 2. 累积分布函数对比
            obs_sorted = np.sort(obs)
            sim_sorted = np.sort(sim)
            obs_cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
            sim_cdf = np.arange(1, len(sim_sorted) + 1) / len(sim_sorted)
            
            ax2.plot(obs_sorted, obs_cdf, 'b-', label='观测值', linewidth=2)
            ax2.plot(sim_sorted, sim_cdf, 'r--', label='模拟值', linewidth=2)
            ax2.set_xlabel('数值')
            ax2.set_ylabel('累积概率')
            ax2.set_title('累积分布函数对比')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # 3. Q-Q图
            from scipy.stats import probplot
            probplot(obs, dist="norm", plot=ax3)
            ax3.set_title('观测值Q-Q图 (正态分布)')
            ax3.grid(True, alpha=0.3)
            
            probplot(sim, dist="norm", plot=ax4)
            ax4.set_title('模拟值Q-Q图 (正态分布)')
            ax4.grid(True, alpha=0.3)
            
            plt.suptitle(title, fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"概率分布图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制概率分布图失败: {e}")
            raise
    
    def plot_residual_distribution(self, observed: np.ndarray, simulated: np.ndarray,
                                  title: str = "残差分布分析",
                                  save_path: Optional[str] = None,
                                  figsize: Tuple[int, int] = (12, 8)) -> plt.Figure:
        """绘制残差分布图"""
        logger.info("开始残差分布分析")
        
        try:
            # 数据预处理
            observed = np.array(observed, dtype=float)
            simulated = np.array(simulated, dtype=float)
            
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                raise ValueError("没有有效数据进行残差分布分析")
            
            # 计算残差
            residuals = sim - obs
            
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 1. 残差直方图
            ax1.hist(residuals, bins=30, alpha=0.7, color='green', density=True)
            ax1.set_xlabel('残差')
            ax1.set_ylabel('概率密度')
            ax1.set_title('残差分布直方图')
            ax1.grid(True, alpha=0.3)
            
            # 2. 残差Q-Q图
            from scipy.stats import probplot
            probplot(residuals, dist="norm", plot=ax2)
            ax2.set_title('残差Q-Q图 (正态分布)')
            ax2.grid(True, alpha=0.3)
            
            # 3. 残差箱线图
            ax3.boxplot(residuals, patch_artist=True, boxprops=dict(facecolor='lightgreen'))
            ax3.set_title('残差箱线图')
            ax3.set_ylabel('残差')
            ax3.grid(True, alpha=0.3)
            
            # 4. 残差时间序列
            time_index = np.arange(len(residuals))
            ax4.plot(time_index, residuals, 'g-', linewidth=1, alpha=0.7)
            ax4.axhline(y=0, color='k', linestyle='--', alpha=0.5)
            ax4.set_xlabel('时间')
            ax4.set_ylabel('残差')
            ax4.set_title('残差时间序列')
            ax4.grid(True, alpha=0.3)
            
            plt.suptitle(title, fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"残差分布图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制残差分布图失败: {e}")
            raise

class SensitivityVisualizer:
    """敏感性分析可视化器"""
    
    def __init__(self):
        self.sensitivity_data = {}
        logger.info("SensitivityVisualizer initialized")
    
    def visualize_sensitivity_analysis(self, parameter_names: List[str],
                                     sensitivity_indices: Dict[str, float],
                                     title: str = "敏感性分析",
                                     save_path: Optional[str] = None,
                                     figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """可视化敏感性分析结果"""
        logger.info("开始敏感性分析可视化")
        
        try:
            # 存储敏感性数据
            self.sensitivity_data = {
                'parameter_names': parameter_names,
                'sensitivity_indices': sensitivity_indices,
                'title': title
            }
            
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 1. 敏感性指数条形图
            param_names = list(sensitivity_indices.keys())
            sens_values = list(sensitivity_indices.values())
            
            bars = ax1.bar(param_names, sens_values, color='skyblue', alpha=0.7)
            ax1.set_xlabel('参数名称')
            ax1.set_ylabel('敏感性指数')
            ax1.set_title('参数敏感性指数')
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(True, alpha=0.3)
            
            # 添加数值标签
            for bar, value in zip(bars, sens_values):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                         f'{value:.3f}', ha='center', va='bottom')
            
            # 2. 敏感性指数排序
            sorted_params = sorted(sensitivity_indices.items(), key=lambda x: abs(x[1]), reverse=True)
            sorted_names = [param[0] for param in sorted_params]
            sorted_values = [param[1] for param in sorted_params]
            
            bars = ax2.bar(range(len(sorted_names)), sorted_values, color='lightcoral', alpha=0.7)
            ax2.set_xlabel('参数排名')
            ax2.set_ylabel('敏感性指数')
            ax2.set_title('参数敏感性排序')
            ax2.set_xticks(range(len(sorted_names)))
            ax2.set_xticklabels(sorted_names, rotation=45)
            ax2.grid(True, alpha=0.3)
            
            # 3. 敏感性指数饼图
            # 只显示前5个最重要的参数
            top_n = min(5, len(sorted_params))
            top_params = sorted_params[:top_n]
            top_names = [param[0] for param in top_params]
            top_values = [abs(param[1]) for param in top_params]
            
            # 归一化
            total_sensitivity = sum(top_values)
            top_percentages = [val/total_sensitivity*100 for val in top_values]
            
            wedges, texts, autotexts = ax3.pie(top_percentages, labels=top_names, autopct='%1.1f%%',
                                               startangle=90, colors=plt.cm.Set3(np.linspace(0, 1, len(top_names))))
            ax3.set_title('前5个参数敏感性贡献')
            
            # 4. 敏感性指数热力图
            # 创建敏感性矩阵（这里简化为1D，实际可以是2D）
            sensitivity_matrix = np.array(sorted_values).reshape(1, -1)
            im = ax4.imshow(sensitivity_matrix, cmap='Reds', aspect='auto')
            ax4.set_xticks(range(len(sorted_names)))
            ax4.set_xticklabels(sorted_names, rotation=45)
            ax4.set_yticks([])
            ax4.set_title('敏感性指数热力图')
            
            # 添加颜色条
            plt.colorbar(im, ax=ax4)
            
            plt.suptitle(title, fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"敏感性分析图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制敏感性分析图失败: {e}")
            raise
    
    def plot_parameter_interaction(self, parameter_names: List[str],
                                  interaction_matrix: np.ndarray,
                                  title: str = "参数交互作用分析",
                                  save_path: Optional[str] = None,
                                  figsize: Tuple[int, int] = (12, 10)) -> plt.Figure:
        """绘制参数交互作用图"""
        logger.info("开始参数交互作用分析")
        
        try:
            # 创建图形
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
            
            # 1. 交互作用热力图
            im1 = ax1.imshow(interaction_matrix, cmap='RdBu_r', aspect='auto', center=0)
            ax1.set_xticks(range(len(parameter_names)))
            ax1.set_xticklabels(parameter_names, rotation=45)
            ax1.set_yticks(range(len(parameter_names)))
            ax1.set_yticklabels(parameter_names)
            ax1.set_title('参数交互作用矩阵')
            ax1.set_xlabel('参数')
            ax1.set_ylabel('参数')
            
            # 添加数值标签
            for i in range(len(parameter_names)):
                for j in range(len(parameter_names)):
                    text = ax1.text(j, i, f'{interaction_matrix[i, j]:.3f}',
                                   ha="center", va="center", color="black", fontsize=8)
            
            plt.colorbar(im1, ax=ax1)
            
            # 2. 交互作用强度条形图
            # 计算每个参数的总交互强度
            total_interaction = np.sum(np.abs(interaction_matrix), axis=1)
            
            bars = ax2.bar(parameter_names, total_interaction, color='lightgreen', alpha=0.7)
            ax2.set_xlabel('参数名称')
            ax2.set_ylabel('总交互强度')
            ax2.set_title('参数总交互强度')
            ax2.tick_params(axis='x', rotation=45)
            ax2.grid(True, alpha=0.3)
            
            # 添加数值标签
            for bar, value in zip(bars, total_interaction):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                         f'{value:.3f}', ha='center', va='bottom')
            
            plt.suptitle(title, fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"参数交互作用图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制参数交互作用图失败: {e}")
            raise
    
    def export_sensitivity_results(self, filepath: str):
        """导出敏感性分析结果"""
        try:
            if not self.sensitivity_data:
                logger.warning("没有敏感性分析数据可导出")
                return
            
            export_data = {
                'parameter_names': self.sensitivity_data['parameter_names'],
                'sensitivity_indices': self.sensitivity_data['sensitivity_indices'],
                'analysis_summary': {
                    'total_parameters': len(self.sensitivity_data['parameter_names']),
                    'max_sensitivity': max(self.sensitivity_data['sensitivity_indices'].values()) if self.sensitivity_data['sensitivity_indices'] else 0,
                    'min_sensitivity': min(self.sensitivity_data['sensitivity_indices'].values()) if self.sensitivity_data['sensitivity_indices'] else 0,
                    'mean_sensitivity': np.mean(list(self.sensitivity_data['sensitivity_indices'].values())) if self.sensitivity_data['sensitivity_indices'] else 0
                }
            }
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"敏感性分析结果已导出到 {filepath}")
            
        except Exception as e:
            logger.error(f"导出敏感性分析结果失败: {e}")

