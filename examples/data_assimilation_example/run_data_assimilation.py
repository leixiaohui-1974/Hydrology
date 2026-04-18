"""
数据同化系统示例
================

演示数据同化系统的各种功能
"""
import sys
import os

# Add project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)



import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hydro_model.data_assimilation.enkf_enhanced import LocalizedEnKF, AdaptiveEnKF
from hydro_model.data_assimilation.particle_filter import ParticleFilter
from hydro_model.data_assimilation.multi_source_fusion import DataSource, MultiSourceDataFusion
from hydro_model.data_assimilation.observation_system import ObservationNetwork
from hydro_model.data_assimilation.data_quality import DataValidator, AnomalyDetector, DataRepairer


def create_sample_data():
    """创建示例数据"""
    np.random.seed(42)
    
    # 时间设置
    n_timesteps = 50
    time_steps = np.arange(n_timesteps)
    
    # 空间设置
    n_points = 30
    coordinates = np.random.uniform(0, 100, (n_points, 2))
    
    # 真实状态（简化的水文模型）
    true_states = np.zeros((n_points, n_timesteps))
    true_states[:, 0] = np.random.normal(10, 2, n_points)
    
    # 时间演化
    for t in range(1, n_timesteps):
        true_states[:, t] = true_states[:, t-1] + np.random.normal(0, 0.1, n_points)
        
    # 观测数据
    observations = true_states + np.random.normal(0, 0.5, true_states.shape)
    observation_errors = np.ones_like(observations) * 0.5
    
    return {
        'true_states': true_states,
        'observations': observations,
        'observation_errors': observation_errors,
        'coordinates': coordinates,
        'time_steps': time_steps,
        'n_points': n_points,
        'n_timesteps': n_timesteps
    }


def demonstrate_localized_enkf(data_dict):
    """演示局部化EnKF"""
    print("\n=== 局部化EnKF演示 ===")
    
    localized_enkf = LocalizedEnKF(ensemble_size=20, localization_radius=25.0)
    localized_enkf.set_state_info(data_dict['n_points'], data_dict['coordinates'])
    localized_enkf.set_observation_info(data_dict['n_points'], data_dict['coordinates'])
    
    # 创建集合
    ensemble_states = np.random.normal(
        data_dict['true_states'][:, 0:1], 1.0, (data_dict['n_points'], 20)
    )
    ensemble_obs = ensemble_states.copy()
    localized_enkf.set_ensemble(ensemble_states, ensemble_obs)
    
    # 执行同化
    assimilation_results = []
    for t in range(10):
        observations = data_dict['observations'][:, t]
        updated_states = localized_enkf.assimilate(observations)
        state_mean = np.mean(updated_states, axis=1)
        analysis_error = np.mean(np.abs(state_mean - data_dict['true_states'][:, t]))
        assimilation_results.append(analysis_error)
        localized_enkf.ensemble_states = updated_states
        
    print(f"局部化EnKF分析误差: {np.mean(assimilation_results):.4f}")
    return assimilation_results


def demonstrate_adaptive_enkf(data_dict):
    """演示自适应EnKF"""
    print("\n=== 自适应EnKF演示 ===")
    
    adaptive_enkf = AdaptiveEnKF(ensemble_size=20, adaptive_inflation=True)
    adaptive_enkf.set_state_info(data_dict['n_points'])
    adaptive_enkf.set_observation_info(data_dict['n_points'])
    
    # 创建集合
    ensemble_states = np.random.normal(
        data_dict['true_states'][:, 0:1], 1.0, (data_dict['n_points'], 20)
    )
    ensemble_obs = ensemble_states.copy()
    adaptive_enkf.set_ensemble(ensemble_states, ensemble_obs)
    
    # 执行同化
    assimilation_results = []
    for t in range(10):
        observations = data_dict['observations'][:, t]
        obs_errors = data_dict['observation_errors'][:, t]
        updated_states = adaptive_enkf.assimilate(observations, obs_errors)
        state_mean = np.mean(updated_states, axis=1)
        analysis_error = np.mean(np.abs(state_mean - data_dict['true_states'][:, t]))
        assimilation_results.append(analysis_error)
        adaptive_enkf.ensemble_states = updated_states
        
    print(f"自适应EnKF分析误差: {np.mean(assimilation_results):.4f}")
    return assimilation_results


def demonstrate_particle_filter(data_dict):
    """演示粒子滤波"""
    print("\n=== 粒子滤波演示 ===")
    
    def transition_model(particles, control=None):
        return particles + np.random.normal(0, 0.1, particles.shape)
        
    def observation_model(particles):
        return particles + np.random.normal(0, 0.5, particles.shape)
        
    def initial_distribution(n_particles, **kwargs):
        return np.random.normal(10, 2, (n_particles, data_dict['n_points']))
        
    # 创建粒子滤波
    pf = ParticleFilter(n_particles=50)
    pf.set_transition_model(transition_model)
    pf.set_observation_model(observation_model)
    pf.initialize_particles(initial_distribution)
    
    # 运行粒子滤波
    assimilation_results = []
    for t in range(10):
        observations = data_dict['observations'][:, t]
        pf.step(observations)
        estimate = pf.get_state_estimate()
        estimated_state = estimate['mean']
        error = np.mean(np.abs(estimated_state - data_dict['true_states'][:, t]))
        assimilation_results.append(error)
        
    print(f"粒子滤波分析误差: {np.mean(assimilation_results):.4f}")
    return assimilation_results


def demonstrate_multi_source_fusion(data_dict):
    """演示多源数据融合"""
    print("\n=== 多源数据融合演示 ===")
    
    # 创建数据源
    source1 = DataSource(
        name="High_Quality_Sparse",
        data=data_dict['observations'][::2, :],
        coordinates=data_dict['coordinates'][::2],
        quality_scores=np.ones(data_dict['n_points']//2) * 0.9
    )
    
    source2 = DataSource(
        name="Medium_Quality_Dense",
        data=data_dict['observations'] + np.random.normal(0, 0.3, data_dict['observations'].shape),
        coordinates=data_dict['coordinates'],
        quality_scores=np.ones(data_dict['n_points']) * 0.7
    )
    
    # 创建融合系统
    fusion_system = MultiSourceDataFusion(quality_weighted=True)
    fusion_system.add_data_source(source1)
    fusion_system.add_data_source(source2)
    
    # 执行数据融合
    target_coords = data_dict['coordinates']
    fusion_result = fusion_system.fuse_data(target_coords, time_index=0)
    
    # 计算融合质量
    fused_data = fusion_result['data']
    true_data = data_dict['true_states'][:, 0]
    fusion_error = np.mean(np.abs(fused_data - true_data))
    
    print(f"数据融合误差: {fusion_error:.4f}")
    return fusion_error


def demonstrate_data_quality_control(data_dict):
    """演示数据质量控制"""
    print("\n=== 数据质量控制演示 ===")
    
    # 创建有问题的数据
    problematic_data = data_dict['observations'].copy()
    problematic_data[10, 0] = 100  # 异常值
    problematic_data[15, 0] = np.nan  # 缺失值
    
    # 数据验证
    validator = DataValidator()
    
    def range_check(data, min_val=-20, max_val=30):
        valid_mask = ~np.isnan(data)
        valid_data = data[valid_mask]
        in_range = np.sum((valid_data >= min_val) & (valid_data <= max_val))
        total_valid = len(valid_data)
        score = in_range / total_valid if total_valid > 0 else 0.0
        issues = []
        if score < 1.0:
            issues.append(f"部分数据超出范围 [{min_val}, {max_val}]")
        return {'status': 'success', 'score': score, 'issues': issues}
        
    validator.add_validation_rule('range_check', range_check, {'min_val': -20, 'max_val': 30})
    
    # 执行验证
    validation_results = validator.validate_data(problematic_data[:, 0], "problematic_data")
    print(f"数据验证评分: {validation_results['overall_score']:.3f}")
    
    # 异常检测
    detector = AnomalyDetector()
    detection_results = detector.detect_anomalies(problematic_data[:, 0], "problematic_data", threshold=3.0)
    print(f"检测到异常: {detection_results['anomaly_count']}")
    
    # 数据修复
    repairer = DataRepairer()
    repaired_data = repairer.repair_data(problematic_data[:, 0], detection_results['anomalies'], 'interpolation')
    
    # 计算修复质量
    original_error = np.mean(np.abs(problematic_data[:, 0] - data_dict['true_states'][:, 0]))
    repaired_error = np.mean(np.abs(repaired_data - data_dict['true_states'][:, 0]))
    
    print(f"修复前误差: {original_error:.4f}")
    print(f"修复后误差: {repaired_error:.4f}")
    
    return repaired_error


def plot_results(data_dict, results_dict):
    """绘制结果"""
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    
    # 真实状态和观测
    ax1 = axes[0, 0]
    ax1.plot(data_dict['time_steps'][:20], data_dict['true_states'][0, :20], 'b-', label='True State', linewidth=2)
    ax1.plot(data_dict['time_steps'][:20], data_dict['observations'][0, :20], 'r.', label='Observations', alpha=0.6)
    ax1.set_title('True State vs Observations')
    ax1.set_xlabel('Time Step')
    ax1.set_ylabel('State Value')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 同化误差比较
    ax2 = axes[0, 1]
    if 'localized_enkf' in results_dict:
        ax2.plot(results_dict['localized_enkf'], 'b-', label='Localized EnKF', linewidth=2)
    if 'adaptive_enkf' in results_dict:
        ax2.plot(results_dict['adaptive_enkf'], 'r-', label='Adaptive EnKF', linewidth=2)
    if 'particle_filter' in results_dict:
        ax2.plot(results_dict['particle_filter'], 'g-', label='Particle Filter', linewidth=2)
    ax2.set_title('Assimilation Error Comparison')
    ax2.set_xlabel('Time Step')
    ax2.set_ylabel('Error')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 空间分布
    ax3 = axes[1, 0]
    scatter = ax3.scatter(data_dict['coordinates'][:, 0], data_dict['coordinates'][:, 1], 
                          c=data_dict['true_states'][:, 0], s=50, cmap='viridis')
    ax3.set_title('Spatial Distribution (t=0)')
    ax3.set_xlabel('X Coordinate')
    ax3.set_ylabel('Y Coordinate')
    plt.colorbar(scatter, ax=ax3)
    ax3.grid(True, alpha=0.3)
    
    # 时间演化
    ax4 = axes[1, 1]
    for i in range(0, data_dict['n_points'], 5):
        ax4.plot(data_dict['time_steps'][:20], data_dict['true_states'][i, :20], alpha=0.6)
    ax4.set_title('Temporal Evolution')
    ax4.set_xlabel('Time Step')
    ax4.set_ylabel('State Value')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.show()


def main():
    """主函数"""
    print("数据同化系统演示")
    print("=" * 50)
    
    # 创建示例数据
    print("创建示例数据...")
    data_dict = create_sample_data()
    print(f"数据创建完成: {data_dict['n_points']} 个空间点, {data_dict['n_timesteps']} 个时间步")
    
    # 存储结果
    results_dict = {}
    
    # 演示各种功能
    try:
        results_dict['localized_enkf'] = demonstrate_localized_enkf(data_dict)
        results_dict['adaptive_enkf'] = demonstrate_adaptive_enkf(data_dict)
        results_dict['particle_filter'] = demonstrate_particle_filter(data_dict)
        results_dict['data_fusion'] = demonstrate_multi_source_fusion(data_dict)
        results_dict['data_quality'] = demonstrate_data_quality_control(data_dict)
        
        # 绘制结果
        plot_results(data_dict, results_dict)
        
        # 总结
        print("\n" + "=" * 50)
        print("演示完成总结:")
        print(f"  局部化EnKF平均误差: {np.mean(results_dict['localized_enkf']):.4f}")
        print(f"  自适应EnKF平均误差: {np.mean(results_dict['adaptive_enkf']):.4f}")
        print(f"  粒子滤波平均误差: {np.mean(results_dict['particle_filter']):.4f}")
        print(f"  数据融合误差: {results_dict['data_fusion']:.4f}")
        print(f"  数据修复误差: {results_dict['data_quality']:.4f}")
        
    except Exception as e:
        print(f"演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
