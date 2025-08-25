"""
模型性能评估模块
================

本模块提供水文模型的性能评估功能，包括：
- 模型性能评估器
- 性能指标计算
- 模型比较
- 性能报告生成
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple, Optional, Union, Any
import logging
import json
from datetime import datetime
import os
import scipy.stats as stats # Added missing import for scipy.stats

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class PerformanceMetrics:
    """性能指标计算器"""
    
    def __init__(self):
        self.metrics = {}
        logger.info("PerformanceMetrics initialized")
    
    def calculate_all_metrics(self, observed: np.ndarray, simulated: np.ndarray,
                             time_index: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """计算所有性能指标"""
        logger.info("开始计算性能指标")
        
        try:
            # 数据预处理
            observed, simulated = self._preprocess_data(observed, simulated)
            
            # 基础统计指标
            basic_stats = self._calculate_basic_statistics(observed, simulated)
            
            # 效率指标
            efficiency_metrics = self._calculate_efficiency_metrics(observed, simulated)
            
            # 误差指标
            error_metrics = self._calculate_error_metrics(observed, simulated)
            
            # 时间相关指标
            temporal_metrics = self._calculate_temporal_metrics(observed, simulated, time_index)
            
            # 分布指标
            distribution_metrics = self._calculate_distribution_metrics(observed, simulated)
            
            # 组合所有指标
            all_metrics = {
                'basic_statistics': basic_stats,
                'efficiency_metrics': efficiency_metrics,
                'error_metrics': error_metrics,
                'temporal_metrics': temporal_metrics,
                'distribution_metrics': distribution_metrics,
                'overall_score': 0.0
            }
            
            # 计算综合评分
            all_metrics['overall_score'] = self._calculate_overall_score(all_metrics)
            
            self.metrics = all_metrics
            logger.info("性能指标计算完成")
            
            return all_metrics
            
        except Exception as e:
            logger.error(f"计算性能指标失败: {e}")
            return {}
    
    def _preprocess_data(self, observed: np.ndarray, simulated: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """数据预处理"""
        # 确保数据类型
        observed = np.array(observed, dtype=float)
        simulated = np.array(simulated, dtype=float)
        
        # 检查数据长度
        if len(observed) != len(simulated):
            raise ValueError("观测数据和模拟数据长度不一致")
        
        # 检查数据有效性
        if len(observed) == 0:
            raise ValueError("数据为空")
        
        return observed, simulated
    
    def _calculate_basic_statistics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算基础统计指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        stats_dict = {
            'observed_mean': np.mean(obs),
            'observed_std': np.std(obs),
            'observed_min': np.min(obs),
            'observed_max': np.max(obs),
            'observed_median': np.median(obs),
            'simulated_mean': np.mean(sim),
            'simulated_std': np.std(sim),
            'simulated_min': np.min(sim),
            'simulated_max': np.max(sim),
            'simulated_median': np.median(sim),
            'correlation': np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else np.nan,
            'data_points': len(obs)
        }
        
        return stats_dict
    
    def _calculate_efficiency_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算效率指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # Nash-Sutcliffe效率系数
        numerator = np.sum((obs - sim) ** 2)
        denominator = np.sum((obs - np.mean(obs)) ** 2)
        nse = 1 - (numerator / denominator) if denominator != 0 else np.nan
        
        # Kling-Gupta效率系数
        r = np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else 0
        alpha = (np.std(sim) / np.mean(sim)) / (np.std(obs) / np.mean(obs)) if np.mean(obs) != 0 and np.std(obs) != 0 else 1
        beta = np.mean(sim) / np.mean(obs) if np.mean(obs) != 0 else 1
        kge = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
        
        # 修正的Nash-Sutcliffe效率系数
        log_obs = np.log(obs + 1e-10)
        log_sim = np.log(sim + 1e-10)
        log_numerator = np.sum((log_obs - log_sim) ** 2)
        log_denominator = np.sum((log_obs - np.mean(log_obs)) ** 2)
        log_nse = 1 - (log_numerator / log_denominator) if log_denominator != 0 else np.nan
        
        # 指数效率系数
        exp_numerator = np.sum(np.abs(obs - sim))
        exp_denominator = np.sum(np.abs(obs - np.mean(obs)))
        exp_efficiency = 1 - (exp_numerator / exp_denominator) if exp_denominator != 0 else np.nan
        
        return {
            'nash_sutcliffe': nse,
            'kling_gupta': kge,
            'log_nash_sutcliffe': log_nse,
            'exponential_efficiency': exp_efficiency,
            'correlation': r,
            'alpha': alpha,
            'beta': beta
        }
    
    def _calculate_error_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算误差指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 绝对误差
        absolute_errors = np.abs(sim - obs)
        mae = np.mean(absolute_errors)
        mse = np.mean((sim - obs) ** 2)
        rmse = np.sqrt(mse)
        
        # 相对误差
        relative_errors = (sim - obs) / obs
        relative_errors = relative_errors[np.isfinite(relative_errors)]
        mre = np.mean(relative_errors) if len(relative_errors) > 0 else np.nan
        mape = np.mean(np.abs(relative_errors)) * 100 if len(relative_errors) > 0 else np.nan
        
        # 标准化误差
        normalized_errors = (sim - obs) / np.std(obs) if np.std(obs) != 0 else np.nan
        nrmse = rmse / np.mean(obs) if np.mean(obs) != 0 else np.nan
        
        # 偏差
        bias = np.mean(sim - obs)
        relative_bias = np.mean((sim - obs) / obs) * 100 if np.any(obs != 0) else np.nan
        
        return {
            'mae': mae,
            'mse': mse,
            'rmse': rmse,
            'mre': mre,
            'mape': mape,
            'nrmse': nrmse,
            'bias': bias,
            'relative_bias': relative_bias
        }
    
    def _calculate_temporal_metrics(self, observed: np.ndarray, simulated: np.ndarray,
                                   time_index: Optional[np.ndarray]) -> Dict[str, Any]:
        """计算时间相关指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 峰值指标
        obs_peak_idx = np.argmax(obs)
        sim_peak_idx = np.argmax(sim)
        peak_time_error = sim_peak_idx - obs_peak_idx
        peak_value_error = sim[sim_peak_idx] - obs[obs_peak_idx]
        
        # 时间偏移
        if time_index is not None:
            time_mask = time_index[mask]
            if len(time_mask) > 0:
                obs_peak_time = time_mask[obs_peak_idx]
                sim_peak_time = time_mask[sim_peak_idx]
                peak_time_offset = sim_peak_time - obs_peak_time
            else:
                peak_time_offset = np.nan
        else:
            peak_time_offset = peak_time_error
        
        # 变化率指标
        if len(obs) > 1:
            obs_change_rate = np.diff(obs)
            sim_change_rate = np.diff(sim)
            change_rate_correlation = np.corrcoef(obs_change_rate, sim_change_rate)[0, 1] if len(obs_change_rate) > 1 else np.nan
            change_rate_rmse = np.sqrt(np.mean((sim_change_rate - obs_change_rate) ** 2))
        else:
            change_rate_correlation = np.nan
            change_rate_rmse = np.nan
        
        return {
            'peak_time_error': peak_time_error,
            'peak_value_error': peak_value_error,
            'peak_time_offset': peak_time_offset,
            'change_rate_correlation': change_rate_correlation,
            'change_rate_rmse': change_rate_rmse
        }
    
    def _calculate_distribution_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算分布指标"""
        # 移除NaN值
        mask = ~(np.isnan(observed) | np.isnan(simulated))
        obs = observed[mask]
        sim = simulated[mask]
        
        if len(obs) == 0:
            return {}
        
        # 分布相似性指标
        from scipy.stats import ks_2samp, wasserstein_distance
        
        try:
            ks_statistic, ks_pvalue = ks_2samp(obs, sim)
            wasserstein_dist = wasserstein_distance(obs, sim)
        except:
            ks_statistic, ks_pvalue = np.nan, np.nan
            wasserstein_dist = np.nan
        
        # 分位数误差
        quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]
        obs_quantiles = np.quantile(obs, quantiles)
        sim_quantiles = np.quantile(sim, quantiles)
        quantile_errors = np.abs(sim_quantiles - obs_quantiles)
        mean_quantile_error = np.mean(quantile_errors)
        
        # 偏度和峰度
        obs_skew = stats.skew(obs) if len(obs) > 2 else np.nan
        obs_kurtosis = stats.kurtosis(obs) if len(obs) > 2 else np.nan
        sim_skew = stats.skew(sim) if len(sim) > 2 else np.nan
        sim_kurtosis = stats.kurtosis(sim) if len(sim) > 2 else np.nan
        
        skew_error = abs(sim_skew - obs_skew) if not (np.isnan(sim_skew) or np.isnan(obs_skew)) else np.nan
        kurtosis_error = abs(sim_kurtosis - obs_kurtosis) if not (np.isnan(sim_kurtosis) or np.isnan(obs_kurtosis)) else np.nan
        
        return {
            'ks_statistic': ks_statistic,
            'ks_pvalue': ks_pvalue,
            'wasserstein_distance': wasserstein_dist,
            'mean_quantile_error': mean_quantile_error,
            'skew_error': skew_error,
            'kurtosis_error': kurtosis_error,
            'observed_skew': obs_skew,
            'observed_kurtosis': obs_kurtosis,
            'simulated_skew': sim_skew,
            'simulated_kurtosis': sim_kurtosis
        }
    
    def _calculate_overall_score(self, metrics: Dict[str, Any]) -> float:
        """计算综合评分"""
        score = 0.0
        total_weight = 0.0
        
        # 效率指标权重 (40%)
        if 'efficiency_metrics' in metrics:
            eff_metrics = metrics['efficiency_metrics']
            
            # NSE评分 (权重20%)
            nse = eff_metrics.get('nash_sutcliffe', np.nan)
            if not np.isnan(nse):
                if nse >= 0.8:
                    score += 20
                elif nse >= 0.6:
                    score += 15
                elif nse >= 0.4:
                    score += 10
                elif nse >= 0.2:
                    score += 5
                total_weight += 20
            
            # KGE评分 (权重20%)
            kge = eff_metrics.get('kling_gupta', np.nan)
            if not np.isnan(kge):
                if kge >= 0.8:
                    score += 20
                elif kge >= 0.6:
                    score += 15
                elif kge >= 0.4:
                    score += 10
                elif kge >= 0.2:
                    score += 5
                total_weight += 20
        
        # 误差指标权重 (30%)
        if 'error_metrics' in metrics:
            error_metrics = metrics['error_metrics']
            
            # RMSE评分 (权重15%)
            rmse = error_metrics.get('rmse', np.nan)
            if not np.isnan(rmse):
                rmse_score = max(0, 15 - rmse * 2)  # 根据RMSE大小评分
                score += rmse_score
                total_weight += 15
            
            # 偏差评分 (权重15%)
            relative_bias = error_metrics.get('relative_bias', np.nan)
            if not np.isnan(relative_bias):
                bias_score = max(0, 15 - abs(relative_bias) * 0.5)  # 根据相对偏差大小评分
                score += bias_score
                total_weight += 15
        
        # 时间指标权重 (20%)
        if 'temporal_metrics' in metrics:
            temp_metrics = metrics['temporal_metrics']
            
            # 峰值时间误差评分 (权重10%)
            peak_time_error = temp_metrics.get('peak_time_error', np.nan)
            if not np.isnan(peak_time_error):
                peak_score = max(0, 10 - abs(peak_time_error) * 0.5)
                score += peak_score
                total_weight += 10
            
            # 变化率相关性评分 (权重10%)
            change_rate_corr = temp_metrics.get('change_rate_correlation', np.nan)
            if not np.isnan(change_rate_corr):
                corr_score = max(0, 10 * (change_rate_corr + 1) / 2)
                score += corr_score
                total_weight += 10
        
        # 分布指标权重 (10%)
        if 'distribution_metrics' in metrics:
            dist_metrics = metrics['distribution_metrics']
            
            # KS检验p值评分 (权重10%)
            ks_pvalue = dist_metrics.get('ks_pvalue', np.nan)
            if not np.isnan(ks_pvalue):
                ks_score = max(0, 10 * ks_pvalue)
                score += ks_score
                total_weight += 10
        
        # 计算加权平均分
        if total_weight > 0:
            overall_score = score / total_weight * 100
        else:
            overall_score = 0.0
        
        return min(100.0, max(0.0, overall_score))

class ModelPerformanceEvaluator:
    """模型性能评估器"""
    
    def __init__(self):
        self.evaluator = PerformanceMetrics()
        self.evaluation_results = {}
        logger.info("ModelPerformanceEvaluator initialized")
    
    def evaluate_model(self, model_name: str, observed: np.ndarray, simulated: np.ndarray,
                       time_index: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """评估单个模型性能"""
        logger.info(f"开始评估模型: {model_name}")
        
        try:
            # 计算性能指标
            metrics = self.evaluator.calculate_all_metrics(observed, simulated, time_index)
            
            # 存储评估结果
            self.evaluation_results[model_name] = {
                'metrics': metrics,
                'observed': observed,
                'simulated': simulated,
                'time_index': time_index,
                'evaluation_time': datetime.now().isoformat()
            }
            
            logger.info(f"模型 {model_name} 评估完成")
            return metrics
            
        except Exception as e:
            logger.error(f"评估模型 {model_name} 失败: {e}")
            return {}
    
    def evaluate_multiple_models(self, model_data: Dict[str, Dict[str, np.ndarray]]) -> Dict[str, Any]:
        """评估多个模型性能"""
        logger.info("开始评估多个模型")
        
        evaluation_results = {}
        
        for model_name, data in model_data.items():
            if 'observed' in data and 'simulated' in data:
                observed = data['observed']
                simulated = data['simulated']
                time_index = data.get('time_index', None)
                
                metrics = self.evaluate_model(model_name, observed, simulated, time_index)
                evaluation_results[model_name] = metrics
        
        logger.info("多模型评估完成")
        return evaluation_results
    
    def get_model_ranking(self) -> List[Tuple[str, float]]:
        """获取模型排名"""
        if not self.evaluation_results:
            return []
        
        rankings = []
        for model_name, result in self.evaluation_results.items():
            if 'metrics' in result and 'overall_score' in result['metrics']:
                score = result['metrics']['overall_score']
                rankings.append((model_name, score))
        
        # 按分数降序排序
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings
    
    def export_evaluation_results(self, filepath: str):
        """导出评估结果"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.evaluation_results, f, indent=2, default=str)
            logger.info(f"评估结果已导出到 {filepath}")
        except Exception as e:
            logger.error(f"导出评估结果失败: {e}")

class ModelComparison:
    """模型比较器"""
    
    def __init__(self):
        self.comparison_results = {}
        logger.info("ModelComparison initialized")
    
    def compare_models(self, evaluation_results: Dict[str, Any]) -> Dict[str, Any]:
        """比较多个模型"""
        logger.info("开始模型比较")
        
        try:
            comparison_results = {
                'model_rankings': {},
                'performance_summary': {},
                'statistical_tests': {},
                'recommendations': []
            }
            
            # 模型排名
            model_scores = []
            for model_name, result in evaluation_results.items():
                if 'overall_score' in result:
                    score = result['overall_score']
                    model_scores.append((model_name, score))
            
            # 按分数排序
            model_scores.sort(key=lambda x: x[1], reverse=True)
            comparison_results['model_rankings'] = {
                'ranked_models': model_scores,
                'best_model': model_scores[0][0] if model_scores else None,
                'worst_model': model_scores[-1][0] if model_scores else None
            }
            
            # 性能摘要
            if model_scores:
                scores = [score for _, score in model_scores]
                comparison_results['performance_summary'] = {
                    'mean_score': np.mean(scores),
                    'std_score': np.std(scores),
                    'min_score': np.min(scores),
                    'max_score': np.max(scores),
                    'score_range': np.max(scores) - np.min(scores)
                }
            
            # 生成建议
            comparison_results['recommendations'] = self._generate_recommendations(comparison_results)
            
            self.comparison_results = comparison_results
            logger.info("模型比较完成")
            
            return comparison_results
            
        except Exception as e:
            logger.error(f"模型比较失败: {e}")
            return {}
    
    def _generate_recommendations(self, comparison_results: Dict[str, Any]) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于排名的建议
        if 'model_rankings' in comparison_results:
            rankings = comparison_results['model_rankings']
            best_model = rankings.get('best_model')
            worst_model = rankings.get('worst_model')
            
            if best_model:
                recommendations.append(f"推荐使用模型: {best_model}")
            
            if worst_model and best_model:
                recommendations.append(f"避免使用模型: {worst_model}")
        
        # 基于性能差异的建议
        if 'performance_summary' in comparison_results:
            summary = comparison_results['performance_summary']
            score_range = summary.get('score_range', 0)
            mean_score = summary.get('mean_score', 0)
            
            if score_range > 20:
                recommendations.append("模型间性能差异较大，建议进行参数调优")
            
            if mean_score < 60:
                recommendations.append("整体模型性能较低，建议检查模型结构或数据质量")
            elif mean_score > 80:
                recommendations.append("整体模型性能良好，可以考虑集成多个模型")
        
        return recommendations
    
    def plot_comparison_charts(self, evaluation_results: Dict[str, Any],
                              save_path: Optional[str] = None,
                              figsize: Tuple[int, int] = (15, 10)) -> plt.Figure:
        """绘制模型比较图表"""
        logger.info("开始绘制模型比较图表")
        
        try:
            # 收集数据
            model_names = list(evaluation_results.keys())
            metrics_data = {}
            
            # 收集各种指标
            for model_name in model_names:
                if 'metrics' in evaluation_results[model_name]:
                    metrics = evaluation_results[model_name]['metrics']
                    metrics_data[model_name] = {
                        'nse': metrics.get('efficiency_metrics', {}).get('nash_sutcliffe', np.nan),
                        'kge': metrics.get('efficiency_metrics', {}).get('kling_gupta', np.nan),
                        'rmse': metrics.get('error_metrics', {}).get('rmse', np.nan),
                        'mape': metrics.get('error_metrics', {}).get('mape', np.nan),
                        'overall_score': metrics.get('overall_score', np.nan)
                    }
            
            # 创建图形
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=figsize)
            
            # 1. 综合评分对比
            scores = [metrics_data[name]['overall_score'] for name in model_names]
            bars = ax1.bar(model_names, scores, color='skyblue', alpha=0.7)
            ax1.set_ylabel('综合评分')
            ax1.set_title('模型综合评分对比')
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(True, alpha=0.3)
            
            # 添加数值标签
            for bar, score in zip(bars, scores):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height + 1,
                         f'{score:.1f}', ha='center', va='bottom')
            
            # 2. 效率指标对比
            nse_values = [metrics_data[name]['nse'] for name in model_names]
            kge_values = [metrics_data[name]['kge'] for name in model_names]
            
            x = np.arange(len(model_names))
            width = 0.35
            
            ax2.bar(x - width/2, nse_values, width, label='NSE', color='lightcoral', alpha=0.7)
            ax2.bar(x + width/2, kge_values, width, label='KGE', color='lightgreen', alpha=0.7)
            ax2.set_xlabel('模型')
            ax2.set_ylabel('效率系数')
            ax2.set_title('模型效率指标对比')
            ax2.set_xticks(x)
            ax2.set_xticklabels(model_names, rotation=45)
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            # 3. 误差指标对比
            rmse_values = [metrics_data[name]['rmse'] for name in model_names]
            mape_values = [metrics_data[name]['mape'] for name in model_names]
            
            ax3.bar(x - width/2, rmse_values, width, label='RMSE', color='lightblue', alpha=0.7)
            ax3.bar(x + width/2, mape_values, width, label='MAPE', color='lightyellow', alpha=0.7)
            ax3.set_xlabel('模型')
            ax3.set_ylabel('误差值')
            ax3.set_title('模型误差指标对比')
            ax3.set_xticks(x)
            ax3.set_xticklabels(model_names, rotation=45)
            ax3.legend()
            ax3.grid(True, alpha=0.3)
            
            # 4. 雷达图
            # 选择前4个模型进行雷达图比较
            top_models = model_names[:4] if len(model_names) >= 4 else model_names
            
            if len(top_models) >= 2:
                # 准备雷达图数据
                categories = ['NSE', 'KGE', 'Overall Score', 'RMSE (norm)', 'MAPE (norm)']
                
                # 标准化数据用于雷达图
                radar_data = {}
                for model_name in top_models:
                    metrics = metrics_data[model_name]
                    nse_norm = max(0, min(1, metrics['nse'])) if not np.isnan(metrics['nse']) else 0
                    kge_norm = max(0, min(1, metrics['kge'])) if not np.isnan(metrics['kge']) else 0
                    score_norm = metrics['overall_score'] / 100 if not np.isnan(metrics['overall_score']) else 0
                    rmse_norm = max(0, 1 - metrics['rmse'] / max(rmse_values)) if not np.isnan(metrics['rmse']) else 0
                    mape_norm = max(0, 1 - metrics['mape'] / max(mape_values)) if not np.isnan(metrics['mape']) else 0
                    
                    radar_data[model_name] = [nse_norm, kge_norm, score_norm, rmse_norm, mape_norm]
                
                # 绘制雷达图
                angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
                angles += angles[:1]  # 闭合图形
                
                ax4.set_theta_offset(np.pi / 2)
                ax4.set_theta_direction(-1)
                ax4.set_thetagrids(np.degrees(angles[:-1]), categories)
                
                colors = ['red', 'blue', 'green', 'orange']
                for i, (model_name, values) in enumerate(radar_data.items()):
                    values += values[:1]  # 闭合图形
                    ax4.plot(angles, values, 'o-', linewidth=2, label=model_name, color=colors[i % len(colors)])
                    ax4.fill(angles, values, alpha=0.25, color=colors[i % len(colors)])
                
                ax4.set_title('模型性能雷达图')
                ax4.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
                ax4.set_ylim(0, 1)
            
            plt.suptitle('模型性能综合比较', fontsize=16)
            plt.tight_layout()
            
            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"模型比较图表已保存到 {save_path}")
            
            return fig
            
        except Exception as e:
            logger.error(f"绘制模型比较图表失败: {e}")
            raise

class PerformanceReport:
    """性能报告生成器"""
    
    def __init__(self, evaluator: ModelPerformanceEvaluator, comparator: ModelComparison):
        self.evaluator = evaluator
        self.comparator = comparator
        logger.info("PerformanceReport initialized")
    
    def generate_comprehensive_report(self, title: str = "水文模型性能评估报告") -> str:
        """生成综合性能报告"""
        logger.info("开始生成综合性能报告")
        
        try:
            report = []
            report.append(f"# {title}")
            report.append("=" * 60)
            report.append("")
            
            # 报告摘要
            if self.evaluator.evaluation_results:
                report.append("## 报告摘要")
                report.append("")
                
                # 模型数量
                total_models = len(self.evaluator.evaluation_results)
                report.append(f"**评估模型数量**: {total_models}")
                
                # 模型排名
                rankings = self.evaluator.get_model_ranking()
                if rankings:
                    best_model = rankings[0][0]
                    best_score = rankings[0][1]
                    report.append(f"**最佳模型**: {best_model} (评分: {best_score:.1f}/100)")
                    report.append(f"**最差模型**: {rankings[-1][0]} (评分: {rankings[-1][1]:.1f}/100)")
                
                report.append("")
                
                # 性能统计
                if rankings:
                    scores = [score for _, score in rankings]
                    report.append("**性能统计**:")
                    report.append(f"- 平均评分: {np.mean(scores):.1f}")
                    report.append(f"- 评分标准差: {np.std(scores):.1f}")
                    report.append(f"- 评分范围: {np.max(scores) - np.min(scores):.1f}")
                    report.append("")
                
                # 详细评估结果
                report.append("## 详细评估结果")
                report.append("")
                
                for i, (model_name, score) in enumerate(rankings, 1):
                    report.append(f"### {i}. {model_name}")
                    report.append(f"**综合评分**: {score:.1f}/100")
                    
                    if model_name in self.evaluator.evaluation_results:
                        metrics = self.evaluator.evaluation_results[model_name]['metrics']
                        
                        # 效率指标
                        if 'efficiency_metrics' in metrics:
                            eff = metrics['efficiency_metrics']
                            report.append(f"**效率指标**:")
                            report.append(f"- Nash-Sutcliffe: {eff.get('nash_sutcliffe', np.nan):.4f}")
                            report.append(f"- Kling-Gupta: {eff.get('kling_gupta', np.nan):.4f}")
                        
                        # 误差指标
                        if 'error_metrics' in metrics:
                            err = metrics['error_metrics']
                            report.append(f"**误差指标**:")
                            report.append(f"- RMSE: {err.get('rmse', np.nan):.4f}")
                            report.append(f"- MAPE: {err.get('mape', np.nan):.2f}%")
                            report.append(f"- 偏差: {err.get('bias', np.nan):.4f}")
                        
                        report.append("")
                
                # 模型比较结果
                if len(rankings) > 1:
                    comparison_results = self.comparator.compare_models(
                        {name: self.evaluator.evaluation_results[name]['metrics'] 
                         for name in self.evaluator.evaluation_results.keys()}
                    )
                    
                    report.append("## 模型比较分析")
                    report.append("")
                    
                    if 'recommendations' in comparison_results:
                        report.append("**主要建议**:")
                        for rec in comparison_results['recommendations']:
                            report.append(f"- {rec}")
                        report.append("")
                
                # 技术说明
                report.append("## 技术说明")
                report.append("")
                report.append("本报告基于以下性能指标生成：")
                report.append("- **效率指标**: Nash-Sutcliffe效率系数、Kling-Gupta效率系数")
                report.append("- **误差指标**: RMSE、MAPE、偏差等")
                report.append("- **时间指标**: 峰值时间误差、变化率相关性等")
                report.append("- **分布指标**: KS检验、分位数误差等")
                report.append("")
                report.append("**综合评分算法**: 加权平均法，考虑各指标的重要性和性能水平")
                report.append("")
                
                report.append("**报告生成时间**: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
            else:
                report.append("**注意**: 暂无评估结果，请先运行模型评估程序。")
            
            report_text = "\n".join(report)
            logger.info("综合性能报告生成完成")
            
            return report_text
            
        except Exception as e:
            logger.error(f"生成综合性能报告失败: {e}")
            return f"报告生成失败: {e}"
    
    def save_report(self, filepath: str, title: str = "水文模型性能评估报告"):
        """保存性能报告到文件"""
        try:
            report_content = self.generate_comprehensive_report(title)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            logger.info(f"性能报告已保存到 {filepath}")
            
        except Exception as e:
            logger.error(f"保存性能报告失败: {e}")

