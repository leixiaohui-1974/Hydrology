"""
实时预报系统示例程序
====================

本程序演示实时预报系统的各项功能
"""

import os
import sys
import time
import logging
import yaml
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from hydro_model.realtime_forecasting import (
    SensorDataAcquisition,
    DataQualityControl,
    RealTimeDataValidator,
    DataInterpolation,
    ShortTermForecaster,
    MediumTermForecaster,
    EnsembleForecaster,
    ForecastCorrector,
    WarningThresholdManager,
    WarningInformationGenerator,
    WarningDistributionSystem,
    WarningEscalationManager,
    RealTimeDashboard,
    ForecastVisualizer,
    WarningMonitor,
    PerformanceTracker
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Configuration loaded from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return {}


def demonstrate_data_acquisition():
    """演示数据接入功能"""
    logger.info("=== 数据接入功能演示 ===")

    try:
        # 配置数据接入
        config = {
            'sensors': {
                'flow_sensor': {'type': 'flow', 'unit': 'm³/s'},
                'water_level_sensor': {'type': 'water_level', 'unit': 'm'},
                'rainfall_sensor': {'type': 'rainfall', 'unit': 'mm'}
            },
            'acquisition_interval': 60
        }

        # 初始化数据接入器
        data_acquisition = SensorDataAcquisition(config)
        logger.info("数据接入器初始化完成")

        # 获取数据统计信息
        stats = data_acquisition.get_data_statistics()
        logger.info(f"数据接入统计: {stats}")

        # 模拟获取最新数据
        latest_data = data_acquisition.get_latest_data()
        logger.info(f"获取到 {len(latest_data)} 条最新数据")

    except Exception as e:
        logger.error(f"数据接入演示失败: {e}")


def demonstrate_data_quality_control():
    """演示数据质量控制功能"""
    logger.info("=== 数据质量控制功能演示 ===")

    try:
        # 配置质量控制
        config = {
            'quality_rules': {
                'flow': {'min_value': 0, 'max_value': 1000},
                'water_level': {'min_value': 0, 'max_value': 50},
                'rainfall': {'min_value': 0, 'max_value': 500}
            }
        }

        # 初始化质量控制器
        quality_control = DataQualityControl(config)
        logger.info("数据质量控制器初始化完成")

        # 模拟传感器数据
        from hydro_model.realtime_forecasting.data_acquisition import SensorData
        
        test_data = SensorData(
            timestamp=datetime.now(),
            sensor_id='test_sensor',
            data_type='flow',
            value=500.0,
            unit='m³/s',
            quality_flag=1,
            metadata={}
        )

        # 验证数据质量
        is_valid, message = quality_control.validate_data(test_data)
        logger.info(f"数据验证结果: {is_valid}, 消息: {message}")

    except Exception as e:
        logger.error(f"数据质量控制演示失败: {e}")


def demonstrate_forecasting_models():
    """演示预报模型功能"""
    logger.info("=== 预报模型功能演示 ===")

    try:
        # 配置短期预报器
        short_term_config = {
            'model_id': 'short_term_forecaster',
            'forecast_horizon': 6,
            'time_step': 15,
            'correction_method': 'kalman_filter',
            'model_params': {},
            'correction_params': {
                'base_uncertainty': 0.1,
                'uncertainty_growth': 0.05
            }
        }

        # 初始化短期预报器
        short_term_forecaster = ShortTermForecaster(short_term_config)
        logger.info("短期预报器初始化完成")

        # 训练模型
        training_data = [{'current_value': 100, 'trend': 5, 'variable': 'flow', 'unit': 'm³/s'}]
        training_success = short_term_forecaster.train(training_data)
        logger.info(f"模型训练结果: {training_success}")

        if training_success:
            # 进行预报
            input_data = {'current_value': 120, 'trend': 3, 'variable': 'flow', 'unit': 'm³/s'}
            lead_time = timedelta(hours=2)
            
            forecast_result = short_term_forecaster.forecast(input_data, lead_time)
            logger.info(f"短期预报结果: {forecast_result.value:.2f} {forecast_result.unit}")

        # 配置中期预报器
        medium_term_config = {
            'model_id': 'medium_term_forecaster',
            'forecast_horizon': 7,
            'time_step': 1,
            'ensemble_size': 5
        }

        # 初始化中期预报器
        medium_term_forecaster = MediumTermForecaster(medium_term_config)
        logger.info("中期预报器初始化完成")

        # 训练模型
        training_success = medium_term_forecaster.train(training_data)
        logger.info(f"中期模型训练结果: {training_success}")

        if training_success:
            # 进行预报
            lead_time = timedelta(days=3)
            forecast_result = medium_term_forecaster.forecast(input_data, lead_time)
            logger.info(f"中期预报结果: {forecast_result.value:.2f} {forecast_result.unit}")

    except Exception as e:
        logger.error(f"预报模型演示失败: {e}")


def demonstrate_warning_system():
    """演示预警系统功能"""
    logger.info("=== 预警系统功能演示 ===")

    try:
        # 配置预警阈值管理器
        threshold_config = {
            'dynamic_thresholds': True,
            'threshold_update_interval': 3600,
            'historical_data_window': 30,
            'percentile_levels': [90, 95, 99]
        }

        # 初始化预警阈值管理器
        threshold_manager = WarningThresholdManager(threshold_config)
        logger.info("预警阈值管理器初始化完成")

        # 添加预警阈值
        from hydro_model.realtime_forecasting.warning_system import WarningThreshold, WarningLevel
        
        flow_threshold = WarningThreshold(
            variable='flow',
            warning_level=WarningLevel.WARNING,
            threshold_value=800.0,
            threshold_type='above',
            description='流量超过800m³/s时发出预警',
            action_required='加强监测，准备应急响应'
        )
        
        threshold_manager.add_threshold('flow', flow_threshold)
        logger.info("预警阈值添加完成")

        # 检查预警
        current_flow = 850.0
        warning_event = threshold_manager.check_warning('flow', current_flow, 'main_river')
        
        if warning_event:
            logger.info(f"预警触发: {warning_event.warning_level.name} - {warning_event.description}")

            # 生成预警信息
            warning_config = {'language': 'zh_CN'}
            warning_generator = WarningInformationGenerator(warning_config)
            
            warning_message = warning_generator.generate_warning_message(warning_event, 'detailed')
            logger.info(f"预警信息: {warning_message['message']}")

            # 发布预警
            distribution_config = {
                'channels': ['database', 'webhook'],
                'email': {},
                'sms': {},
                'webhook': {},
                'database': {}
            }
            
            distribution_system = WarningDistributionSystem(distribution_config)
            distribution_results = distribution_system.distribute_warning(warning_message)
            logger.info(f"预警发布结果: {distribution_results}")

    except Exception as e:
        logger.error(f"预警系统演示失败: {e}")


def demonstrate_real_time_dashboard():
    """演示实时仪表板功能"""
    logger.info("=== 实时仪表板功能演示 ===")

    try:
        # 配置实时仪表板
        dashboard_config = {
            'update_interval': 5,
            'data_sources': {
                'flow_rate': {'name': 'flow_sensor', 'unit': 'm³/s', 'update_frequency': '5s'},
                'water_level': {'name': 'level_sensor', 'unit': 'm', 'update_frequency': '5s'},
                'rainfall': {'name': 'rain_sensor', 'unit': 'mm', 'update_frequency': '5s'}
            },
            'alert_thresholds': {
                'flow_rate': {'warning': 800, 'critical': 1000},
                'water_level': {'warning': 8, 'critical': 10},
                'rainfall': {'warning': 50, 'critical': 100}
            }
        }

        # 初始化实时仪表板
        dashboard = RealTimeDashboard(dashboard_config)
        logger.info("实时仪表板初始化完成")

        # 启动仪表板
        dashboard.start_dashboard()
        logger.info("实时仪表板已启动")

        # 等待一段时间让仪表板收集数据
        time.sleep(10)

        # 获取仪表板数据
        dashboard_data = dashboard.get_dashboard_data()
        logger.info(f"仪表板数据: {dashboard_data['total_metrics']} 个指标")

        # 停止仪表板
        dashboard.stop_dashboard()
        logger.info("实时仪表板已停止")

    except Exception as e:
        logger.error(f"实时仪表板演示失败: {e}")


def demonstrate_forecast_visualization():
    """演示预报可视化功能"""
    logger.info("=== 预报可视化功能演示 ===")

    try:
        # 配置预报可视化器
        visualizer_config = {
            'plot_style': 'modern',
            'color_scheme': 'default',
            'figure_size': (12, 8)
        }

        # 初始化预报可视化器
        visualizer = ForecastVisualizer(visualizer_config)
        logger.info("预报可视化器初始化完成")

        # 生成示例数据
        time_index = [datetime.now() + timedelta(hours=i) for i in range(24)]
        observed_data = [100 + 10 * np.sin(i * np.pi / 12) + np.random.normal(0, 5) for i in range(24)]
        forecast_data = [100 + 10 * np.sin(i * np.pi / 12) for i in range(24)]

        # 绘制预报对比图
        fig = visualizer.plot_forecast_comparison(
            observed_data, forecast_data, time_index,
            title="流量预报对比图"
        )
        logger.info("预报对比图绘制完成")

        # 生成集合预报数据
        ensemble_data = []
        for i in range(5):
            member_data = [100 + 10 * np.sin(i * np.pi / 12) + np.random.normal(0, 3) for i in range(24)]
            ensemble_data.append(member_data)

        # 绘制集合预报图
        fig2 = visualizer.plot_ensemble_forecast(
            ensemble_data, time_index, observed_data,
            title="流量集合预报图"
        )
        logger.info("集合预报图绘制完成")

        # 生成技能评分数据
        skill_metrics = {
            'NSE': 0.85,
            'RMSE': 0.12,
            'MAE': 0.08,
            'Correlation': 0.92
        }

        # 绘制技能评分图
        fig3 = visualizer.plot_forecast_skill(skill_metrics)
        logger.info("技能评分图绘制完成")

        # 保存图片
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        fig.savefig(f"{output_dir}/forecast_comparison.png", dpi=300, bbox_inches='tight')
        fig2.savefig(f"{output_dir}/ensemble_forecast.png", dpi=300, bbox_inches='tight')
        fig3.savefig(f"{output_dir}/forecast_skill.png", dpi=300, bbox_inches='tight')
        
        logger.info(f"图片已保存到 {output_dir} 目录")

    except Exception as e:
        logger.error(f"预报可视化演示失败: {e}")


def demonstrate_warning_monitoring():
    """演示预警监控功能"""
    logger.info("=== 预警监控功能演示 ===")

    try:
        # 配置预警监控器
        monitor_config = {
            'monitoring_interval': 10,
            'auto_resolve': True,
            'escalation_enabled': True
        }

        # 初始化预警监控器
        warning_monitor = WarningMonitor(monitor_config)
        logger.info("预警监控器初始化完成")

        # 模拟预警事件
        from hydro_model.realtime_forecasting.warning_system import WarningEvent, WarningLevel
        
        warning_event = WarningEvent(
            warning_id='test_warning_001',
            timestamp=datetime.now(),
            variable='flow',
            current_value=850.0,
            threshold_value=800.0,
            warning_level=WarningLevel.WARNING,
            location='main_river',
            description='流量超过预警阈值',
            status='active',
            metadata={}
        )

        # 添加预警
        warning_monitor.add_warning(warning_event)
        logger.info("预警事件已添加")

        # 获取活动预警
        active_warnings = warning_monitor.get_active_warnings()
        logger.info(f"活动预警数量: {len(active_warnings)}")

        # 升级预警
        warning_monitor.escalate_warning(warning_event.warning_id, "流量持续上升")
        logger.info("预警已升级")

        # 解除预警
        warning_monitor.resolve_warning(warning_event.warning_id, "流量已恢复正常")
        logger.info("预警已解除")

        # 获取预警摘要
        warning_summary = warning_monitor.get_warning_summary()
        logger.info(f"预警摘要: {warning_summary}")

    except Exception as e:
        logger.error(f"预警监控演示失败: {e}")


def demonstrate_performance_tracking():
    """演示性能跟踪功能"""
    logger.info("=== 性能跟踪功能演示 ===")

    try:
        # 配置性能跟踪器
        tracker_config = {
            'tracking_enabled': True,
            'metric_retention': 7
        }

        # 初始化性能跟踪器
        performance_tracker = PerformanceTracker(tracker_config)
        logger.info("性能跟踪器初始化完成")

        # 跟踪性能指标
        for i in range(10):
            # 模拟CPU使用率
            cpu_usage = 50 + 20 * np.sin(i * np.pi / 5) + np.random.normal(0, 5)
            performance_tracker.track_metric('cpu_usage', cpu_usage, {'source': 'system_monitor'})
            
            # 模拟内存使用率
            memory_usage = 60 + 15 * np.sin(i * np.pi / 5) + np.random.normal(0, 3)
            performance_tracker.track_metric('memory_usage', memory_usage, {'source': 'system_monitor'})
            
            # 模拟预报精度
            forecast_accuracy = 0.8 + 0.1 * np.sin(i * np.pi / 5) + np.random.normal(0, 0.02)
            performance_tracker.track_metric('forecast_accuracy', forecast_accuracy, {'source': 'model_evaluator'})
            
            time.sleep(1)

        # 获取性能摘要
        cpu_summary = performance_tracker.get_performance_summary('cpu_usage')
        logger.info(f"CPU使用率摘要: {cpu_summary}")

        memory_summary = performance_tracker.get_performance_summary('memory_usage')
        logger.info(f"内存使用率摘要: {memory_summary}")

        accuracy_summary = performance_tracker.get_performance_summary('forecast_accuracy')
        logger.info(f"预报精度摘要: {accuracy_summary}")

        # 获取所有指标摘要
        all_summaries = performance_tracker.get_all_metrics_summary()
        logger.info(f"所有指标摘要: {all_summaries['total_metrics']} 个指标")

        # 导出指标数据
        start_time = datetime.now() - timedelta(hours=1)
        end_time = datetime.now()
        
        cpu_data = performance_tracker.export_metrics('cpu_usage', start_time, end_time)
        if cpu_data is not None:
            logger.info(f"CPU使用率数据导出完成: {len(cpu_data)} 条记录")

    except Exception as e:
        logger.error(f"性能跟踪演示失败: {e}")


def main():
    """主函数"""
    logger.info("开始实时预报系统功能演示")
    
    try:
        # 演示各个模块功能
        demonstrate_data_acquisition()
        time.sleep(2)
        
        demonstrate_data_quality_control()
        time.sleep(2)
        
        demonstrate_forecasting_models()
        time.sleep(2)
        
        demonstrate_warning_system()
        time.sleep(2)
        
        demonstrate_real_time_dashboard()
        time.sleep(2)
        
        demonstrate_forecast_visualization()
        time.sleep(2)
        
        demonstrate_warning_monitoring()
        time.sleep(2)
        
        demonstrate_performance_tracking()
        
        logger.info("实时预报系统功能演示完成")
        
    except Exception as e:
        logger.error(f"演示过程中发生错误: {e}")


if __name__ == "__main__":
    main()

