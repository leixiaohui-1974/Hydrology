"""
统计验证指标模块
================

本模块提供水文模型的统计验证指标，包括：
- 流量验证指标
- 水位验证指标
- 统计验证器
- 验证报告生成
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional, Union, Any
from scipy import stats
import json
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FlowValidationMetrics:
    """流量验证指标计算器"""
    
    def __init__(self):
        self.metrics = {}
        logger.info("FlowValidationMetrics initialized")
    
    def calculate_nash_sutcliffe(self, observed: np.ndarray, simulated: np.ndarray) -> float:
        """计算Nash-Sutcliffe效率系数"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return np.nan
            
            # 计算NSE
            numerator = np.sum((obs - sim) ** 2)
            denominator = np.sum((obs - np.mean(obs)) ** 2)
            
            if denominator == 0:
                return np.nan
            
            nse = 1 - (numerator / denominator)
            return nse
            
        except Exception as e:
            logger.error(f"计算Nash-Sutcliffe效率系数失败: {e}")
            return np.nan
    
    def calculate_kling_gupta(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算Kling-Gupta效率系数"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return {'kge': np.nan, 'r': np.nan, 'alpha': np.nan, 'beta': np.nan}
            
            # 计算相关系数
            r = np.corrcoef(obs, sim)[0, 1]
            if np.isnan(r):
                r = 0.0
            
            # 计算变差系数比
            alpha = (np.std(sim) / np.mean(sim)) / (np.std(obs) / np.mean(obs))
            if np.isnan(alpha) or alpha == 0:
                alpha = 1.0
            
            # 计算均值比
            beta = np.mean(sim) / np.mean(obs)
            if np.isnan(beta) or beta == 0:
                beta = 1.0
            
            # 计算KGE
            kge = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
            
            return {
                'kge': kge,
                'r': r,
                'alpha': alpha,
                'beta': beta
            }
            
        except Exception as e:
            logger.error(f"计算Kling-Gupta效率系数失败: {e}")
            return {'kge': np.nan, 'r': np.nan, 'alpha': np.nan, 'beta': np.nan}
    
    def calculate_relative_error(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算相对误差指标"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return {'mre': np.nan, 'mape': np.nan, 'rmse': np.nan}
            
            # 计算相对误差
            relative_errors = (sim - obs) / obs
            relative_errors = relative_errors[np.isfinite(relative_errors)]
            
            if len(relative_errors) == 0:
                return {'mre': np.nan, 'mape': np.nan, 'rmse': np.nan}
            
            # 平均相对误差
            mre = np.mean(relative_errors)
            
            # 平均绝对百分比误差
            mape = np.mean(np.abs(relative_errors)) * 100
            
            # 均方根误差
            rmse = np.sqrt(np.mean((sim - obs) ** 2))
            
            return {
                'mre': mre,
                'mape': mape,
                'rmse': rmse
            }
            
        except Exception as e:
            logger.error(f"计算相对误差指标失败: {e}")
            return {'mre': np.nan, 'mape': np.nan, 'rmse': np.nan}
    
    def calculate_absolute_error(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算绝对误差指标"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return {'mae': np.nan, 'mse': np.nan, 'rmse': np.nan}
            
            # 计算绝对误差
            absolute_errors = np.abs(sim - obs)
            
            # 平均绝对误差
            mae = np.mean(absolute_errors)
            
            # 均方误差
            mse = np.mean((sim - obs) ** 2)
            
            # 均方根误差
            rmse = np.sqrt(mse)
            
            return {
                'mae': mae,
                'mse': mse,
                'rmse': rmse
            }
            
        except Exception as e:
            logger.error(f"计算绝对误差指标失败: {e}")
            return {'mae': np.nan, 'mse': np.nan, 'rmse': np.nan}
    
    def calculate_all_metrics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, Any]:
        """计算所有流量验证指标"""
        logger.info("计算流量验证指标")
        
        # 基础统计量
        basic_stats = self._calculate_basic_statistics(observed, simulated)
        
        # 效率系数
        nse = self.calculate_nash_sutcliffe(observed, simulated)
        kge_metrics = self.calculate_kling_gupta(observed, simulated)
        
        # 误差指标
        relative_errors = self.calculate_relative_error(observed, simulated)
        absolute_errors = self.calculate_absolute_error(observed, simulated)
        
        # 组合所有指标
        all_metrics = {
            'basic_statistics': basic_stats,
            'nash_sutcliffe': nse,
            'kling_gupta': kge_metrics,
            'relative_errors': relative_errors,
            'absolute_errors': absolute_errors
        }
        
        self.metrics = all_metrics
        logger.info("流量验证指标计算完成")
        
        return all_metrics
    
    def _calculate_basic_statistics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算基础统计量"""
        try:
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
                'simulated_mean': np.mean(sim),
                'simulated_std': np.std(sim),
                'simulated_min': np.min(sim),
                'simulated_max': np.max(sim),
                'correlation': np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else np.nan
            }
            
            return stats_dict
            
        except Exception as e:
            logger.error(f"计算基础统计量失败: {e}")
            return {}

class WaterLevelValidationMetrics:
    """水位验证指标计算器"""
    
    def __init__(self):
        self.metrics = {}
        logger.info("WaterLevelValidationMetrics initialized")
    
    def calculate_water_level_bias(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算水位偏差分析"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return {'mean_bias': np.nan, 'bias_std': np.nan, 'relative_bias': np.nan}
            
            # 计算偏差
            bias = sim - obs
            
            # 平均偏差
            mean_bias = np.mean(bias)
            
            # 偏差标准差
            bias_std = np.std(bias)
            
            # 相对偏差
            relative_bias = np.mean(bias / obs) * 100
            
            return {
                'mean_bias': mean_bias,
                'bias_std': bias_std,
                'relative_bias': relative_bias
            }
            
        except Exception as e:
            logger.error(f"计算水位偏差分析失败: {e}")
            return {'mean_bias': np.nan, 'bias_std': np.nan, 'relative_bias': np.nan}
    
    def calculate_peak_time_error(self, observed: np.ndarray, simulated: np.ndarray, 
                                 time_index: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """计算峰值时间误差"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) == 0:
                return {'peak_time_error': np.nan, 'peak_value_error': np.nan}
            
            # 找到峰值位置
            obs_peak_idx = np.argmax(obs)
            sim_peak_idx = np.argmax(sim)
            
            # 峰值时间误差（如果有时间索引）
            if time_index is not None:
                time_mask = time_index[mask]
                if len(time_mask) > 0:
                    obs_peak_time = time_mask[obs_peak_idx]
                    sim_peak_time = time_mask[sim_peak_idx]
                    peak_time_error = sim_peak_time - obs_peak_time
                else:
                    peak_time_error = np.nan
            else:
                peak_time_error = sim_peak_idx - obs_peak_idx
            
            # 峰值大小误差
            peak_value_error = sim[sim_peak_idx] - obs[obs_peak_idx]
            
            return {
                'peak_time_error': peak_time_error,
                'peak_value_error': peak_value_error,
                'observed_peak_idx': obs_peak_idx,
                'simulated_peak_idx': sim_peak_idx
            }
            
        except Exception as e:
            logger.error(f"计算峰值时间误差失败: {e}")
            return {'peak_time_error': np.nan, 'peak_value_error': np.nan}
    
    def calculate_water_level_change_rate_error(self, observed: np.ndarray, simulated: np.ndarray,
                                              time_step: float = 1.0) -> Dict[str, float]:
        """计算水位变化率误差"""
        try:
            # 移除NaN值
            mask = ~(np.isnan(observed) | np.isnan(simulated))
            obs = observed[mask]
            sim = simulated[mask]
            
            if len(obs) < 2:
                return {'change_rate_error': np.nan, 'change_rate_correlation': np.nan}
            
            # 计算变化率
            obs_change_rate = np.diff(obs) / time_step
            sim_change_rate = np.diff(sim) / time_step
            
            # 变化率误差
            change_rate_error = np.mean(np.abs(sim_change_rate - obs_change_rate))
            
            # 变化率相关性
            if len(obs_change_rate) > 1:
                change_rate_correlation = np.corrcoef(obs_change_rate, sim_change_rate)[0, 1]
            else:
                change_rate_correlation = np.nan
            
            return {
                'change_rate_error': change_rate_error,
                'change_rate_correlation': change_rate_correlation
            }
            
        except Exception as e:
            logger.error(f"计算水位变化率误差失败: {e}")
            return {'change_rate_error': np.nan, 'change_rate_correlation': np.nan}
    
    def calculate_all_metrics(self, observed: np.ndarray, simulated: np.ndarray,
                             time_index: Optional[np.ndarray] = None,
                             time_step: float = 1.0) -> Dict[str, Any]:
        """计算所有水位验证指标"""
        logger.info("计算水位验证指标")
        
        # 基础统计量
        basic_stats = self._calculate_basic_statistics(observed, simulated)
        
        # 水位偏差
        bias_metrics = self.calculate_water_level_bias(observed, simulated)
        
        # 峰值时间误差
        peak_metrics = self.calculate_peak_time_error(observed, simulated, time_index)
        
        # 变化率误差
        change_rate_metrics = self.calculate_water_level_change_rate_error(observed, simulated, time_step)
        
        # 组合所有指标
        all_metrics = {
            'basic_statistics': basic_stats,
            'bias_analysis': bias_metrics,
            'peak_analysis': peak_metrics,
            'change_rate_analysis': change_rate_metrics
        }
        
        self.metrics = all_metrics
        logger.info("水位验证指标计算完成")
        
        return all_metrics
    
    def _calculate_basic_statistics(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, float]:
        """计算基础统计量"""
        try:
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
                'simulated_mean': np.mean(sim),
                'simulated_std': np.std(sim),
                'simulated_min': np.min(sim),
                'simulated_max': np.max(sim),
                'correlation': np.corrcoef(obs, sim)[0, 1] if len(obs) > 1 else np.nan
            }
            
            return stats_dict
            
        except Exception as e:
            logger.error(f"计算基础统计量失败: {e}")
            return {}

class StatisticalValidator:
    """统计验证器"""
    
    def __init__(self):
        self.flow_validator = FlowValidationMetrics()
        self.water_level_validator = WaterLevelValidationMetrics()
        self.validation_results = {}
        
        logger.info("StatisticalValidator initialized")
    
    def validate_flow(self, observed: np.ndarray, simulated: np.ndarray) -> Dict[str, Any]:
        """验证流量数据"""
        logger.info("开始流量数据验证")
        
        try:
            # 数据预处理
            observed, simulated = self._preprocess_data(observed, simulated)
            
            # 计算流量验证指标
            flow_metrics = self.flow_validator.calculate_all_metrics(observed, simulated)
            
            # 存储结果
            self.validation_results['flow'] = flow_metrics
            
            logger.info("流量数据验证完成")
            return flow_metrics
            
        except Exception as e:
            logger.error(f"流量数据验证失败: {e}")
            return {}
    
    def validate_water_level(self, observed: np.ndarray, simulated: np.ndarray,
                            time_index: Optional[np.ndarray] = None,
                            time_step: float = 1.0) -> Dict[str, Any]:
        """验证水位数据"""
        logger.info("开始水位数据验证")
        
        try:
            # 数据预处理
            observed, simulated = self._preprocess_data(observed, simulated)
            
            # 计算水位验证指标
            water_level_metrics = self.water_level_validator.calculate_all_metrics(
                observed, simulated, time_index, time_step
            )
            
            # 存储结果
            self.validation_results['water_level'] = water_level_metrics
            
            logger.info("水位数据验证完成")
            return water_level_metrics
            
        except Exception as e:
            logger.error(f"水位数据验证失败: {e}")
            return {}
    
    def validate_all(self, flow_data: Optional[Tuple[np.ndarray, np.ndarray]] = None,
                     water_level_data: Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]] = None) -> Dict[str, Any]:
        """验证所有数据"""
        logger.info("开始全面数据验证")
        
        all_results = {}
        
        # 验证流量数据
        if flow_data is not None:
            observed, simulated = flow_data
            flow_results = self.validate_flow(observed, simulated)
            all_results['flow'] = flow_results
        
        # 验证水位数据
        if water_level_data is not None:
            observed, simulated, time_index, time_step = water_level_data
            water_level_results = self.validate_water_level(observed, simulated, time_index, time_step)
            all_results['water_level'] = water_level_results
        
        # 生成综合评估
        if all_results:
            all_results['overall_assessment'] = self._generate_overall_assessment(all_results)
        
        logger.info("全面数据验证完成")
        return all_results
    
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
    
    def _generate_overall_assessment(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """生成综合评估"""
        assessment = {
            'validation_quality': 'unknown',
            'recommendations': [],
            'overall_score': 0.0
        }
        
        scores = []
        
        # 评估流量验证结果
        if 'flow' in results:
            flow_metrics = results['flow']
            
            # NSE评分
            if 'nash_sutcliffe' in flow_metrics:
                nse = flow_metrics['nash_sutcliffe']
                if not np.isnan(nse):
                    if nse >= 0.8:
                        scores.append(90)
                        assessment['recommendations'].append("流量模拟效果优秀")
                    elif nse >= 0.6:
                        scores.append(70)
                        assessment['recommendations'].append("流量模拟效果良好")
                    elif nse >= 0.4:
                        scores.append(50)
                        assessment['recommendations'].append("流量模拟效果一般")
                    else:
                        scores.append(30)
                        assessment['recommendations'].append("流量模拟效果较差，需要改进")
            
            # KGE评分
            if 'kling_gupta' in flow_metrics:
                kge = flow_metrics['kling_gupta'].get('kge', np.nan)
                if not np.isnan(kge):
                    if kge >= 0.8:
                        scores.append(85)
                    elif kge >= 0.6:
                        scores.append(65)
                    elif kge >= 0.4:
                        scores.append(45)
                    else:
                        scores.append(25)
        
        # 评估水位验证结果
        if 'water_level' in results:
            water_level_metrics = results['water_level']
            
            # 偏差评分
            if 'bias_analysis' in water_level_metrics:
                bias = water_level_metrics['bias_analysis']
                relative_bias = bias.get('relative_bias', np.nan)
                if not np.isnan(relative_bias):
                    if abs(relative_bias) <= 5:
                        scores.append(85)
                        assessment['recommendations'].append("水位模拟偏差很小")
                    elif abs(relative_bias) <= 10:
                        scores.append(70)
                        assessment['recommendations'].append("水位模拟偏差较小")
                    elif abs(relative_bias) <= 20:
                        scores.append(55)
                        assessment['recommendations'].append("水位模拟偏差中等")
                    else:
                        scores.append(35)
                        assessment['recommendations'].append("水位模拟偏差较大，需要改进")
        
        # 计算综合评分
        if scores:
            assessment['overall_score'] = np.mean(scores)
            
            if assessment['overall_score'] >= 80:
                assessment['validation_quality'] = 'excellent'
            elif assessment['overall_score'] >= 60:
                assessment['validation_quality'] = 'good'
            elif assessment['overall_score'] >= 40:
                assessment['validation_quality'] = 'fair'
            else:
                assessment['validation_quality'] = 'poor'
        
        return assessment
    
    def export_results(self, filepath: str):
        """导出验证结果"""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.validation_results, f, indent=2, default=str)
            logger.info(f"验证结果已导出到 {filepath}")
        except Exception as e:
            logger.error(f"导出验证结果失败: {e}")

class ValidationReport:
    """验证报告生成器"""
    
    def __init__(self, validator: StatisticalValidator):
        self.validator = validator
        logger.info("ValidationReport initialized")
    
    def generate_report(self, title: str = "水文模型验证报告") -> str:
        """生成验证报告"""
        logger.info("开始生成验证报告")
        
        try:
            report = []
            report.append(f"# {title}")
            report.append("=" * 50)
            report.append("")
            
            # 报告摘要
            if hasattr(self.validator, 'validation_results') and self.validator.validation_results:
                report.append("## 报告摘要")
                report.append("")
                
                overall_assessment = self.validator.validation_results.get('overall_assessment', {})
                if overall_assessment:
                    quality = overall_assessment.get('validation_quality', 'unknown')
                    score = overall_assessment.get('overall_score', 0.0)
                    
                    report.append(f"**验证质量**: {quality}")
                    report.append(f"**综合评分**: {score:.1f}/100")
                    report.append("")
                    
                    recommendations = overall_assessment.get('recommendations', [])
                    if recommendations:
                        report.append("**主要建议**:")
                        for rec in recommendations:
                            report.append(f"- {rec}")
                        report.append("")
                
                # 流量验证结果
                if 'flow' in self.validator.validation_results:
                    report.append("## 流量验证结果")
                    report.append("")
                    report.extend(self._format_flow_results(self.validator.validation_results['flow']))
                    report.append("")
                
                # 水位验证结果
                if 'water_level' in self.validator.validation_results:
                    report.append("## 水位验证结果")
                    report.append("")
                    report.extend(self._format_water_level_results(self.validator.validation_results['water_level']))
                    report.append("")
                
                # 技术说明
                report.append("## 技术说明")
                report.append("")
                report.append("本报告基于以下统计指标生成：")
                report.append("- Nash-Sutcliffe效率系数 (NSE)")
                report.append("- Kling-Gupta效率系数 (KGE)")
                report.append("- 相对误差和绝对误差")
                report.append("- 水位偏差分析")
                report.append("- 峰值时间误差分析")
                report.append("")
                
                report.append("**报告生成时间**: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
                
            else:
                report.append("**注意**: 暂无验证结果，请先运行验证程序。")
            
            report_text = "\n".join(report)
            logger.info("验证报告生成完成")
            
            return report_text
            
        except Exception as e:
            logger.error(f"生成验证报告失败: {e}")
            return f"报告生成失败: {e}"
    
    def _format_flow_results(self, flow_results: Dict[str, Any]) -> List[str]:
        """格式化流量验证结果"""
        lines = []
        
        # NSE
        if 'nash_sutcliffe' in flow_results:
            nse = flow_results['nash_sutcliffe']
            if not np.isnan(nse):
                lines.append(f"**Nash-Sutcliffe效率系数**: {nse:.4f}")
                
                if nse >= 0.8:
                    lines.append("  - 评价: 优秀 (≥0.8)")
                elif nse >= 0.6:
                    lines.append("  - 评价: 良好 (0.6-0.8)")
                elif nse >= 0.4:
                    lines.append("  - 评价: 一般 (0.4-0.6)")
                else:
                    lines.append("  - 评价: 较差 (<0.4)")
        
        # KGE
        if 'kling_gupta' in flow_results:
            kge_metrics = flow_results['kling_gupta']
            kge = kge_metrics.get('kge', np.nan)
            if not np.isnan(kge):
                lines.append(f"**Kling-Gupta效率系数**: {kge:.4f}")
                lines.append(f"  - 相关系数: {kge_metrics.get('r', np.nan):.4f}")
                lines.append(f"  - 变差系数比: {kge_metrics.get('alpha', np.nan):.4f}")
                lines.append(f"  - 均值比: {kge_metrics.get('beta', np.nan):.4f}")
        
        # 误差指标
        if 'relative_errors' in flow_results:
            rel_errors = flow_results['relative_errors']
            lines.append(f"**相对误差指标**:")
            lines.append(f"  - 平均相对误差: {rel_errors.get('mre', np.nan):.4f}")
            lines.append(f"  - 平均绝对百分比误差: {rel_errors.get('mape', np.nan):.2f}%")
            lines.append(f"  - 均方根误差: {rel_errors.get('rmse', np.nan):.4f}")
        
        return lines
    
    def _format_water_level_results(self, water_level_results: Dict[str, Any]) -> List[str]:
        """格式化水位验证结果"""
        lines = []
        
        # 偏差分析
        if 'bias_analysis' in water_level_results:
            bias = water_level_results['bias_analysis']
            lines.append(f"**水位偏差分析**:")
            lines.append(f"  - 平均偏差: {bias.get('mean_bias', np.nan):.4f}")
            lines.append(f"  - 偏差标准差: {bias.get('bias_std', np.nan):.4f}")
            lines.append(f"  - 相对偏差: {bias.get('relative_bias', np.nan):.2f}%")
        
        # 峰值分析
        if 'peak_analysis' in water_level_results:
            peak = water_level_results['peak_analysis']
            lines.append(f"**峰值分析**:")
            lines.append(f"  - 峰值时间误差: {peak.get('peak_time_error', np.nan):.4f}")
            lines.append(f"  - 峰值大小误差: {peak.get('peak_value_error', np.nan):.4f}")
        
        # 变化率分析
        if 'change_rate_analysis' in water_level_results:
            change_rate = water_level_results['change_rate_analysis']
            lines.append(f"**变化率分析**:")
            lines.append(f"  - 变化率误差: {change_rate.get('change_rate_error', np.nan):.4f}")
            lines.append(f"  - 变化率相关性: {change_rate.get('change_rate_correlation', np.nan):.4f}")
        
        return lines
    
    def save_report(self, filepath: str, title: str = "水文模型验证报告"):
        """保存验证报告到文件"""
        try:
            report_content = self.generate_report(title)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            logger.info(f"验证报告已保存到 {filepath}")
            
        except Exception as e:
            logger.error(f"保存验证报告失败: {e}")

