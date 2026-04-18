"""
可视化验证模块
==============

本模块提供水文模型的可视化验证功能，包括：
- 时间序列对比
- 空间分布验证
- 验证图表绘制
- 对比分析器
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Tuple, Optional, Union, Any
import logging
import seaborn as sns
from datetime import datetime, timedelta
import json

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class TimeSeriesValidator:
    """时间序列验证器"""
    
    def __init__(self):
        self.validation_data = {}
        logger.info("TimeSeriesValidator initialized")
    
    def validate_time_series(self, observed: np.ndarray, simulated: np.ndarray,
                            time_index: Optional[np.ndarray] = None,
                            title: str = "时间序列验证") -> Dict[str, Any]:
        """验证时间序列数据"""
        logger.info("开始时间序列验证")
        
        try:
            # 数据预处理
            observed, simulated, time_index = self._preprocess_data(observed, simulated, time_index)
            
            # 计算验证指标
            validation_metrics = self._calculate_validation_metrics(observed, simulated)
            
            # 存储验证数据
            self.validation_data = {
                'observed': observed,
                'simulated': simulated,
                'time_index': time_index,
                'metrics': validation_metrics,
                'title': title
            }
            
            logger.info("时间序列验证完成")
            return validation_metrics
            
        except Exception as e:
            logger.error(f"时间序列验证失败: {e}")
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
    
    def _calculate_validation_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算验证指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 计算相关系数
        correlation = np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else np.nan
        
        # 计算偏差
        bias = np.mean(sim - obs)
        
        # 计算相对偏差
        relative_bias = np.mean((sim - obs) / obs) * 100 if np.any(obs != 0) else np.nan
        
        # 计算均方根误差
        rmse = np.sqrt(np.mean((sim - obs) ** 2))
        
        return {
            'correlation': correlation,
            'bias': bias,
            'relative_bias': relative_bias,
            'rmse': rmse
        }
    
    def plot_time_series_comparison(self, save_path: Optional[str] = None,
                                   figsize: Tuple[int, int] = (12, 8)) -> plt.Figure:
        """绘制时间序列对比图"""
        if not self.validation_data:
            raise ValueError("请先运行时间序列验证")
        
        try:
            observed = self.validation_data['observed']
            simulated = self.validation_data['simulated']
            time_index = self.validation_data['time_index']
            title = self.validation_data['title']
            metrics = self.validation_data['metrics']
            
            # 创建图形
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize)
            
            # 时间序列对比图
            ax1.plot(time_index, observed, 'b-', label='观测值', linewidth=2, alpha=0.8)
            ax1.plot(time_index, simulated, 'r--', label='模拟值', linewidth=2, alpha=0.8)
            ax1.set_xlabel('时间')
            ax1.set_ylabel('数值')
            ax1.set_title(f'{title} - 时间序列对比')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 残差图
            residuals = simulated - observed
            ax2.plot(time_index, residuals, 'g-', linewidth=1, alpha=0.7)
            ax2.axhline(y=0, color='k', linestyle='--', alpha=0.5)
            ax2.set_xlabel('时间')
            ax2.set_ylabel('残差 (模拟值 - 观测值)')
            ax2.set_title('残差分析')
            ax2.grid(True, alpha=0.3)
            
            # 添加验证指标
            if metrics:
                metrics_text = f"相关系数: {metrics.get('correlation', np.nan):.4f}\n"
                metrics_text += f"偏差: {metrics.get('bias', np.nan):.4f}\n"
                metrics_text += f"相对偏差: {metrics.get('relative_bias', np.nan):.2f}%\n"
                metrics_text += f"RMSE: {metrics.get('rmse', np.nan):.4f}"
                
                ax1.text(0.02, 0.98, metrics_text, transform=ax1.transAxes,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"时间序列对比图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制时间序列对比图失败: {e}")
            raise
    
    def plot_scatter_comparison(self, save_path: Optional[str] = None,
                               figsize: Tuple[int, int] = (10, 8)) -> plt.Figure:
        """绘制散点对比图"""
        if not self.validation_data:
            raise ValueError("请先运行时间序列验证")
        
        try:
            observed = self.validation_data['observed']
            simulated = self.validation_data['simulated']
            metrics = self.validation_data['metrics']
            
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            # 创建图形
            fig, ax = plt.subplots(figsize=figsize)
            
            # 散点图
            ax.scatter(obs, sim, alpha=0.6, s=30)
            
            # 添加1:1线
            min_val = min(np.min(obs), np.min(sim))
            max_val = max(np.max(obs), np.max(sim))
            ax.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2, label='1:1线')
            
            # 添加回归线
            if len(obs) > 1:
                z = np.polyfit(obs, sim, 1)
                p = np.poly1d(z)
                ax.plot(obs, p(obs), 'g-', linewidth=2, label=f'回归线 (y={z[0]:.3f}x+{z[1]:.3f})')
            
            ax.set_xlabel('观测值')
            ax.set_ylabel('模拟值')
            ax.set_title('观测值 vs 模拟值 散点图')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # 添加验证指标
            if metrics:
                metrics_text = f"相关系数: {metrics.get('correlation', np.nan):.4f}\n"
                metrics_text += f"R²: {metrics.get('correlation', np.nan)**2:.4f}\n"
                metrics_text += f"RMSE: {metrics.get('rmse', np.nan):.4f}"
                
                ax.text(0.02, 0.98, metrics_text, transform=ax.transAxes,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"散点对比图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制散点对比图失败: {e}")
            raise

class SpatialValidator:
    """空间分布验证器"""
    
    def __init__(self):
        self.spatial_data = {}
        logger.info("SpatialValidator initialized")
    
    def validate_spatial_distribution(self, observed: np.ndarray, simulated: np.ndarray,
                                    coordinates: Optional[np.ndarray] = None,
                                    title: str = "空间分布验证") -> Dict[str, Any]:
        """验证空间分布数据"""
        logger.info("开始空间分布验证")
        
        try:
            # 数据预处理
            observed, simulated, coordinates = self._preprocess_spatial_data(observed, simulated, coordinates)
            
            # 计算空间验证指标
            spatial_metrics = self._calculate_spatial_metrics(observed, simulated)
            
            # 存储空间数据
            self.spatial_data = {
                'observed': observed,
                'simulated': simulated,
                'coordinates': coordinates,
                'metrics': spatial_metrics,
                'title': title
            }
            
            logger.info("空间分布验证完成")
            return spatial_metrics
            
        except Exception as e:
            logger.error(f"空间分布验证失败: {e}")
            return {}
    
    def _preprocess_spatial_data(self, observed: np.ndarray, simulated: np.ndarray,
                                coordinates: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """空间数据预处理"""
        # 确保数据是2D数组
        if observed.ndim == 1:
            observed = observed.reshape(-1, 1)
        if simulated.ndim == 1:
            simulated = simulated.reshape(-1, 1)
        
        # 检查数据形状
        if observed.shape != simulated.shape:
            raise ValueError("观测数据和模拟数据形状不一致")
        
        # 生成默认坐标（如果没有提供）
        if coordinates is None:
            rows, cols = observed.shape
            y, x = np.meshgrid(np.arange(cols), np.arange(rows))
            coordinates = np.stack([x.flatten(), y.flatten()], axis=1)
        
        return observed, simulated, coordinates
    
    def _calculate_spatial_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算空间验证指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 空间相关系数
        spatial_correlation = np.corrcoef(obs.flatten(), sim.flatten())[0, 1] if len(obs) > 1 else np.nan
        
        # 空间偏差
        spatial_bias = np.mean(sim - obs)
        
        # 空间RMSE
        spatial_rmse = np.sqrt(np.mean((sim - obs) ** 2))
        
        # 空间一致性指数
        spatial_consistency = 1 - np.sum(np.abs(sim - obs)) / np.sum(np.abs(obs))
        
        return {
            'spatial_correlation': spatial_correlation,
            'spatial_bias': spatial_bias,
            'spatial_rmse': spatial_rmse,
            'spatial_consistency': spatial_consistency
        }
    
    def plot_spatial_comparison(self, save_path: Optional[str] = None,
                               figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制空间分布对比图"""
        if not self.spatial_data:
            raise ValueError("请先运行空间分布验证")
        
        try:
            observed = self.spatial_data['observed']
            simulated = self.spatial_data['simulated']
            title = self.spatial_data['title']
            metrics = self.spatial_data['metrics']
            
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 观测值空间分布
            im1 = ax1.imshow(observed, cmap='Blues', aspect='auto')
            ax1.set_title('观测值空间分布')
            ax1.set_xlabel('列')
            ax1.set_ylabel('行')
            plt.colorbar(im1, ax=ax1)
            
            # 模拟值空间分布
            im2 = ax2.imshow(simulated, cmap='Reds', aspect='auto')
            ax2.set_title('模拟值空间分布')
            ax2.set_xlabel('列')
            ax2.set_ylabel('行')
            plt.colorbar(im2, ax=ax2)
            
            # 误差分布
            error = simulated - observed
            im3 = ax3.imshow(error, cmap='RdBu_r', aspect='auto', center=0)
            ax3.set_title('误差分布 (模拟值 - 观测值)')
            ax3.set_xlabel('列')
            ax3.set_ylabel('行')
            plt.colorbar(im3, ax=ax3)
            
            # 散点对比
            obs_flat = observed.flatten()
            sim_flat = simulated.flatten()
            mask = ~(np.isnan(obs_flat) | np.isnan(sim_flat))
            obs_valid = obs_flat[mask]
            sim_valid = sim_flat[mask]
            
            ax4.scatter(obs_valid, sim_valid, alpha=0.6, s=20)
            
            # 添加1:1线
            min_val = min(np.min(obs_valid), np.min(sim_valid))
            max_val = max(np.max(obs_valid), np.max(sim_valid))
            ax4.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=2, label='1:1线')
            
            ax4.set_xlabel('观测值')
            ax4.set_ylabel('模拟值')
            ax4.set_title('空间数据散点对比')
            ax4.legend()
            ax4.grid(True, alpha=0.3)
            
            # 添加验证指标
            if metrics:
                metrics_text = f"空间相关系数: {metrics.get('spatial_correlation', np.nan):.4f}\n"
                metrics_text += f"空间偏差: {metrics.get('spatial_bias', np.nan):.4f}\n"
                metrics_text += f"空间RMSE: {metrics.get('spatial_rmse', np.nan):.4f}\n"
                metrics_text += f"空间一致性: {metrics.get('spatial_consistency', np.nan):.4f}"
                
                ax1.text(0.02, 0.98, metrics_text, transform=ax1.transAxes,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
            
            plt.suptitle(title, fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"空间分布对比图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制空间分布对比图失败: {e}")
            raise

class ValidationPlotter:
    """验证图表绘制器"""
    
    def __init__(self):
        self.plotters = {}
        logger.info("ValidationPlotter initialized")
    
    def add_time_series_validator(self, name: str, validator: TimeSeriesValidator):
        """添加时间序列验证器"""
        self.plotters[name] = validator
        logger.info(f"添加时间序列验证器: {name}")
    
    def add_spatial_validator(self, name: str, validator: SpatialValidator):
        """添加空间验证器"""
        self.plotters[name] = validator
        logger.info(f"添加空间验证器: {name}")
    
    def create_comprehensive_report(self, save_dir: str, figsize: Tuple[int, int] = (15, 10)):
        """创建综合验证报告"""
        logger.info("开始创建综合验证报告")
        
        try:
            import os
            os.makedirs(save_dir, exist_ok=True)
            
            for name, plotter in self.plotters.items():
                if isinstance(plotter, TimeSeriesValidator):
                    # 时间序列图
                    time_series_fig = plotter.plot_time_series_comparison(
                        save_path=os.path.join(save_dir, f"{name}_time_series.png"),
                        figsize=figsize
                    )
                    
                    # 散点图
                    scatter_fig = plotter.plot_scatter_comparison(
                        save_path=os.path.join(save_dir, f"{name}_scatter.png"),
                        figsize=figsize
                    )
                    
                    plt.close(time_series_fig)
                    plt.close(scatter_fig)
                    
                elif isinstance(plotter, SpatialValidator):
                    # 空间分布图
                    spatial_fig = plotter.plot_spatial_comparison(
                        save_path=os.path.join(save_dir, f"{name}_spatial.png"),
                        figsize=figsize
                    )
                    plt.close(spatial_fig)
            
            logger.info(f"综合验证报告已保存到 {save_dir}")
            
        except Exception as e:
            logger.error(f"创建综合验证报告失败: {e}")
            raise

class ComparisonAnalyzer:
    """对比分析器"""
    
    def __init__(self):
        self.comparison_results = {}
        logger.info("ComparisonAnalyzer initialized")
    
    def compare_multiple_models(self, model_results: Dict[str, Dict[str, np.ndarray]],
                               observed: np.ndarray,
                               time_index: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """比较多个模型结果"""
        logger.info("开始多模型对比分析")
        
        try:
            comparison_results = {}
            
            for model_name, model_data in model_results.items():
                if 'simulated' in model_data:
                    simulated = model_data['simulated']
                    
                    # 计算验证指标
                    validator = TimeSeriesValidator()
                    metrics = validator.validate_time_series(observed, simulated, time_index, f"{model_name}验证")
                    
                    comparison_results[model_name] = {
                        'metrics': metrics,
                        'validator': validator
                    }
            
            self.comparison_results = comparison_results
            logger.info("多模型对比分析完成")
            
            return comparison_results
            
        except Exception as e:
            logger.error(f"多模型对比分析失败: {e}")
            return {}
    
    def plot_model_comparison(self, save_path: Optional[str] = None,
                             figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制模型对比图"""
        if not self.comparison_results:
            raise ValueError("请先运行多模型对比分析")
        
        try:
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 收集所有模型名称和指标
            model_names = list(self.comparison_results.keys())
            correlations = []
            rmses = []
            biases = []
            
            for model_name in model_names:
                metrics = self.comparison_results[model_name]['metrics']
                correlations.append(metrics.get('correlation', np.nan))
                rmses.append(metrics.get('rmse', np.nan))
                biases.append(metrics.get('bias', np.nan))
            
            # 相关系数对比
            ax1.bar(model_names, correlations, color='skyblue', alpha=0.7)
            ax1.set_title('模型相关系数对比')
            ax1.set_ylabel('相关系数')
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(True, alpha=0.3)
            
            # RMSE对比
            ax2.bar(model_names, rmses, color='lightcoral', alpha=0.7)
            ax2.set_title('模型RMSE对比')
            ax2.set_ylabel('RMSE')
            ax2.tick_params(axis='x', rotation=45)
            ax2.grid(True, alpha=0.3)
            
            # 偏差对比
            ax3.bar(model_names, biases, color='lightgreen', alpha=0.7)
            ax3.set_title('模型偏差对比')
            ax3.set_ylabel('偏差')
            ax3.tick_params(axis='x', rotation=45)
            ax3.grid(True, alpha=0.3)
            
            # 综合评分
            scores = []
            for i, model_name in enumerate(model_names):
                # 综合评分：相关系数权重0.4，RMSE权重0.4，偏差权重0.2
                corr_score = (correlations[i] + 1) / 2 * 100 if not np.isnan(correlations[i]) else 0
                rmse_score = max(0, 100 - rmses[i] * 10) if not np.isnan(rmses[i]) else 0
                bias_score = max(0, 100 - abs(biases[i]) * 10) if not np.isnan(biases[i]) else 0
                
                total_score = corr_score * 0.4 + rmse_score * 0.4 + bias_score * 0.2
                scores.append(total_score)
            
            ax4.bar(model_names, scores, color='gold', alpha=0.7)
            ax4.set_title('模型综合评分对比')
            ax4.set_ylabel('综合评分')
            ax4.tick_params(axis='x', rotation=45)
            ax4.grid(True, alpha=0.3)
            
            plt.suptitle('多模型性能对比分析', fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"模型对比图已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制模型对比图失败: {e}")
            raise
    
    def export_comparison_results(self, filepath: str):
        """导出对比分析结果"""
        try:
            # 准备导出数据
            export_data = {}
            for model_name, result in self.comparison_results.items():
                export_data[model_name] = {
                    'metrics': result['metrics'],
                    'summary': {
                        'correlation': result['metrics'].get('correlation', np.nan),
                        'rmse': result['metrics'].get('rmse', np.nan),
                        'bias': result['metrics'].get('bias', np.nan),
                        'relative_bias': result['metrics'].get('relative_bias', np.nan)
                    }
                }
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"对比分析结果已导出到 {filepath}")
            
        except Exception as e:
            logger.error(f"导出对比分析结果失败: {e}")

