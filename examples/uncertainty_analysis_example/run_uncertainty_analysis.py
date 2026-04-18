#!/usr/bin/env python3
"""
不确定性分析示例
================

本示例演示如何使用Hydro-Suite的不确定性分析功能：
1. Monte Carlo不确定性分析
2. 敏感性分析（Sobol、Morris、FAST）
3. 贝叶斯不确定性量化
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)



import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# 添加父目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from hydro_model.uncertainty.monte_carlo import MonteCarloAnalyzer
from hydro_model.uncertainty.sensitivity_analysis import SensitivityAnalyzer
from hydro_model.uncertainty.bayesian_analysis import BayesianUncertaintyAnalyzer


def create_sample_data():
    """创建示例观测数据"""
    np.random.seed(42)
    
    # 时间序列
    times = np.arange(0, 100, 1)
    
    # 真实参数值
    true_params = {
        'curve_number': 75.0,
        'impervious_fraction': 0.15,
        'storage_capacity': 100.0,
        'routing_coefficient': 2.5
    }
    
    # 生成观测数据（添加噪声）
    observations = []
    for t in times:
        # 模拟降雨事件
        rainfall = 20 * np.exp(-(t - 25)**2 / 100) + 10 * np.exp(-(t - 75)**2 / 100)
        
        # 模拟径流
        runoff = simulate_hydrology_model(true_params, rainfall, t)
        
        # 添加观测噪声
        noise = np.random.normal(0, 2.0)
        observations.append(runoff + noise)
        
    return times, np.array(observations), true_params


def simulate_hydrology_model(params, rainfall, time):
    """
    模拟水文模型
    
    Args:
        params: 参数字典
        rainfall: 降雨量
        time: 时间
        
    Returns:
        径流量
    """
    cn = params['curve_number']
    imp = params['impervious_fraction']
    sc = params['storage_capacity']
    rc = params['routing_coefficient']
    
    # SCS曲线数方法
    s = 254 * (100 / cn - 1)  # 潜在最大滞留量
    
    if rainfall > 0.2 * s:
        q = (rainfall - 0.2 * s) ** 2 / (rainfall + 0.8 * s)
    else:
        q = 0
        
    # 考虑不透水面积
    total_runoff = q * (1 - imp) + rainfall * imp
    
    # 考虑蓄水容量
    actual_runoff = min(total_runoff, sc)
    
    # 简单的路由延迟
    delay_factor = np.exp(-time / (rc * 10))
    
    return actual_runoff * delay_factor


def run_monte_carlo_analysis():
    """运行Monte Carlo不确定性分析"""
    print("=" * 60)
    print("MONTE CARLO UNCERTAINTY ANALYSIS")
    print("=" * 60)
    
    # 创建分析器
    analyzer = MonteCarloAnalyzer(n_samples=500, random_seed=42)
    
    # 添加参数分布
    analyzer.add_parameter_distribution('curve_number', 'normal', mean=75, std=8)
    analyzer.add_parameter_distribution('impervious_fraction', 'uniform', low=0.05, high=0.25)
    analyzer.add_parameter_distribution('storage_capacity', 'lognormal', mean=100, std=0.3)
    analyzer.add_parameter_distribution('routing_coefficient', 'normal', mean=2.5, std=0.5)
    
    # 定义模型函数
    def model_function(params):
        times = np.arange(0, 100, 1)
        outputs = []
        
        for t in times:
            rainfall = 20 * np.exp(-(t - 25)**2 / 100) + 10 * np.exp(-(t - 75)**2 / 100)
            runoff = simulate_hydrology_model(params, rainfall, t)
            outputs.append(runoff)
            
        return {
            'peak_runoff': np.max(outputs),
            'total_runoff': np.sum(outputs),
            'mean_runoff': np.mean(outputs)
        }
    
    # 运行Monte Carlo分析
    def progress_callback(progress):
        print(f"Monte Carlo Progress: {progress:.1f}%")
    
    results = analyzer.run_monte_carlo(model_function, progress_callback)
    
    # 生成报告
    print("\n" + analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('monte_carlo_results')
    
    # 绘制图形
    fig1 = analyzer.plot_parameter_distributions()
    fig2 = analyzer.plot_output_distributions()
    fig3 = analyzer.plot_scatter_matrix()
    
    return analyzer


def run_sensitivity_analysis():
    """运行敏感性分析"""
    print("\n" + "=" * 60)
    print("SENSITIVITY ANALYSIS")
    print("=" * 60)
    
    # 创建分析器
    analyzer = SensitivityAnalyzer(n_samples=1000)
    
    # 添加参数
    analyzer.add_parameter('curve_number', (50, 90), 'uniform')
    analyzer.add_parameter('impervious_fraction', (0.05, 0.25), 'uniform')
    analyzer.add_parameter('storage_capacity', (50, 150), 'uniform')
    analyzer.add_parameter('routing_coefficient', (1.0, 4.0), 'uniform')
    
    # 定义模型函数
    def model_function(params):
        times = np.arange(0, 100, 1)
        outputs = []
        
        for t in times:
            rainfall = 20 * np.exp(-(t - 25)**2 / 100) + 10 * np.exp(-(t - 75)**2 / 100)
            runoff = simulate_hydrology_model(params, rainfall, t)
            outputs.append(runoff)
            
        return np.max(outputs)  # 返回峰值径流
    
    # 运行敏感性分析
    def progress_callback(progress):
        print(f"Sensitivity Analysis Progress: {progress:.1f}%")
    
    # Sobol分析
    print("Running Sobol analysis...")
    sobol_results = analyzer.sobol_analysis(model_function, progress_callback)
    
    # Morris分析
    print("Running Morris analysis...")
    morris_results = analyzer.morris_analysis(model_function, progress_callback)
    
    # FAST分析
    print("Running FAST analysis...")
    fast_results = analyzer.fast_analysis(model_function, progress_callback)
    
    # 生成报告
    print("\n" + analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('sensitivity_analysis_results')
    
    # 绘制图形
    fig = analyzer.plot_sensitivity_results()
    
    return analyzer


def run_bayesian_analysis(times, observations):
    """运行贝叶斯不确定性分析"""
    print("\n" + "=" * 60)
    print("BAYESIAN UNCERTAINTY ANALYSIS")
    print("=" * 60)
    
    # 创建分析器
    analyzer = BayesianUncertaintyAnalyzer(n_walkers=16, n_steps=300, n_burn=100)
    
    # 添加参数和先验
    analyzer.add_parameter('curve_number', 'normal', mean=75, std=10)
    analyzer.add_parameter('impervious_fraction', 'uniform', low=0.05, high=0.25)
    analyzer.add_parameter('storage_capacity', 'gamma', shape=2.0, scale=50.0)
    analyzer.add_parameter('routing_coefficient', 'normal', mean=2.5, std=0.5)
    
    # 设置观测数据
    analyzer.set_observations(observations, times)
    
    # 定义模型函数
    def model_function(params, times):
        outputs = []
        for t in times:
            rainfall = 20 * np.exp(-(t - 25)**2 / 100) + 10 * np.exp(-(t - 75)**2 / 100)
            runoff = simulate_hydrology_model(params, rainfall, t)
            outputs.append(runoff)
        return np.array(outputs)
    
    analyzer.set_model_function(model_function)
    
    # 运行MCMC分析
    def progress_callback(progress):
        print(f"Bayesian Analysis Progress: {progress:.1f}%")
    
    results = analyzer.run_mcmc(progress_callback)
    
    # 生成报告
    print("\n" + analyzer.get_summary_report())
    
    # 保存结果
    analyzer.save_results('bayesian_analysis_results')
    
    # 绘制图形
    fig1 = analyzer.plot_posterior_distributions()
    fig2 = analyzer.plot_parameter_traces()
    fig3 = analyzer.plot_model_fit()
    fig4 = analyzer.plot_autocorrelation()
    
    return analyzer


def create_comparison_plot(mc_analyzer, sa_analyzer, bayes_analyzer):
    """创建对比图"""
    print("\nCreating comparison plots...")
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. 参数不确定性对比
    ax1 = axes[0, 0]
    if mc_analyzer.samples is not None:
        param_names = list(mc_analyzer.parameter_distributions.keys())
        for i, param_name in enumerate(param_names):
            samples = mc_analyzer.samples[param_name]
            ax1.hist(samples, bins=30, alpha=0.7, label=f'MC: {param_name}')
    ax1.set_title('Monte Carlo Parameter Distributions')
    ax1.set_xlabel('Parameter Value')
    ax1.set_ylabel('Frequency')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 敏感性指数对比
    ax2 = axes[0, 1]
    if sa_analyzer.sobol_indices:
        param_names = list(sa_analyzer.sobol_indices['first_order'].keys())
        first_order = list(sa_analyzer.sobol_indices['first_order'].values())
        ax2.bar(param_names, first_order, alpha=0.7)
        ax2.set_title('Sobol First-Order Indices')
        ax2.set_xlabel('Parameters')
        ax2.set_ylabel('Sensitivity Index')
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)
    
    # 3. 后验分布对比
    ax3 = axes[1, 0]
    if bayes_analyzer.posterior_stats:
        param_names = list(bayes_analyzer.posterior_stats.keys())
        means = [bayes_analyzer.posterior_stats[name]['mean'] for name in param_names]
        stds = [bayes_analyzer.posterior_stats[name]['std'] for name in param_names]
        
        x_pos = np.arange(len(param_names))
        ax3.bar(x_pos, means, yerr=stds, alpha=0.7, capsize=5)
        ax3.set_title('Bayesian Posterior Means ± Std')
        ax3.set_xlabel('Parameters')
        ax3.set_ylabel('Parameter Value')
        ax3.set_xticks(x_pos)
        ax3.set_xticklabels(param_names, rotation=45)
        ax3.grid(True, alpha=0.3)
    
    # 4. 模型拟合对比
    ax4 = axes[1, 1]
    if bayes_analyzer.observations is not None:
        times = bayes_analyzer.observation_times
        observations = bayes_analyzer.observations
        
        ax4.scatter(times, observations, color='black', s=30, label='Observations', zorder=5)
        
        if bayes_analyzer.posterior_stats:
            # 使用后验均值进行预测
            mean_params = {}
            for param_name in param_names:
                if np.isfinite(bayes_analyzer.posterior_stats[param_name]['mean']):
                    mean_params[param_name] = bayes_analyzer.posterior_stats[param_name]['mean']
            
            if mean_params:
                try:
                    mean_prediction = bayes_analyzer.model_function(mean_params, times)
                    ax4.plot(times, mean_prediction, 'r-', linewidth=2, label='Model (Posterior Mean)')
                except Exception as e:
                    print(f"Failed to plot model fit: {e}")
        
        ax4.set_title('Model Fit Comparison')
        ax4.set_xlabel('Time')
        ax4.set_ylabel('Value')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('uncertainty_analysis_comparison.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    return fig


def main():
    """主函数"""
    print("Hydro-Suite Uncertainty Analysis Example")
    print("=" * 60)
    
    # 创建示例数据
    print("Creating sample data...")
    times, observations, true_params = create_sample_data()
    
    print(f"Generated {len(observations)} observations")
    print(f"True parameters: {true_params}")
    
    # 运行Monte Carlo分析
    mc_analyzer = run_monte_carlo_analysis()
    
    # 运行敏感性分析
    sa_analyzer = run_sensitivity_analysis()
    
    # 运行贝叶斯分析
    bayes_analyzer = run_bayesian_analysis(times, observations)
    
    # 创建对比图
    comparison_fig = create_comparison_plot(mc_analyzer, sa_analyzer, bayes_analyzer)
    
    print("\n" + "=" * 60)
    print("UNCERTAINTY ANALYSIS COMPLETED")
    print("=" * 60)
    print("Results saved to:")
    print("- monte_carlo_results/")
    print("- sensitivity_analysis_results/")
    print("- bayesian_analysis_results/")
    print("- uncertainty_analysis_comparison.png")
    
    # 显示一些关键结果
    print("\nKEY RESULTS SUMMARY:")
    print("-" * 30)
    
    # Monte Carlo结果
    if mc_analyzer.statistics:
        print("Monte Carlo - Peak Runoff:")
        stats = mc_analyzer.statistics['peak_runoff']
        print(f"  Mean: {stats['mean']:.2f} ± {stats['std']:.2f}")
        print(f"  95% CI: [{stats['q25']:.2f}, {stats['q75']:.2f}]")
    
    # 敏感性结果
    if sa_analyzer.sobol_indices:
        print("\nSensitivity Analysis - Most Important Parameters:")
        ranking = sa_analyzer.get_sensitivity_ranking('sobol')
        for i, (_, row) in enumerate(ranking.head(3).iterrows()):
            print(f"  {i+1}. {row['Parameter']}: First={row['First_Order']:.3f}")
    
    # 贝叶斯结果
    if bayes_analyzer.posterior_stats:
        print("\nBayesian Analysis - Parameter Estimates:")
        for param_name, stats in bayes_analyzer.posterior_stats.items():
            if np.isfinite(stats['mean']):
                print(f"  {param_name}: {stats['mean']:.2f} ± {stats['std']:.2f}")
    
    print("\nAnalysis completed successfully!")


if __name__ == "__main__":
    main()

