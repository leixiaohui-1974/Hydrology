#!/usr/bin/env python3
"""
环境依赖检查脚本
=================
此脚本检查水文建模框架所需的所有依赖包是否已正确安装。

使用方法:
    python check_dependencies.py
    
或者检查特定组件:
    python check_dependencies.py --component gui
    python check_dependencies.py --component ml
    python check_dependencies.py --component gis
"""

import sys
import importlib
import subprocess
import argparse
from typing import Dict, List, Tuple, Optional
import platform

# 定义依赖包分组
DEPENDENCIES = {
    'core': {
        'numpy': 'numpy',
        'pandas': 'pandas', 
        'pyyaml': 'yaml',
        'scipy': 'scipy'
    },
    'visualization': {
        'matplotlib': 'matplotlib',
        'seaborn': 'seaborn',
        'plotly': 'plotly'
    },
    'gui': {
        'eel': 'eel',
        'dash': 'dash',
        'dash-bootstrap-components': 'dash_bootstrap_components',
        'tkinter': 'tkinter'  # 内置模块
    },
    'ml': {
        'torch': 'torch',
        'torchvision': 'torchvision', 
        'torchaudio': 'torchaudio',
        'scikit-learn': 'sklearn',
        'torch-geometric': 'torch_geometric',
        'xgboost': 'xgboost',
        'lightgbm': 'lightgbm',
        'joblib': 'joblib'
    },
    'gis': {
        'geopandas': 'geopandas',
        'rasterio': 'rasterio',
        'whitebox': 'whitebox'
    },
    'database': {
        'sqlalchemy': 'sqlalchemy'
    },
    'stats': {
        'pykrige': 'pykrige',
        'geovoronoi': 'geovoronoi',
        'emcee': 'emcee',
        'corner': 'corner'
    },
    'utils': {
        'easygui': 'easygui',
        'psutil': 'psutil',
        'gitpython': 'git',
        'schedule': 'schedule',
        'lz4': 'lz4'
    }
}

# 可选依赖（不影响核心功能）
OPTIONAL_DEPENDENCIES = ['ml', 'gis', 'stats']

class DependencyChecker:
    """依赖检查器类"""
    
    def __init__(self):
        self.results = {}
        self.missing_packages = []
        self.failed_imports = []
        
    def check_python_version(self) -> bool:
        """检查Python版本"""
        version = sys.version_info
        print(f"Python版本: {version.major}.{version.minor}.{version.micro}")
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            print("❌ 警告: 建议使用Python 3.8或更高版本")
            return False
        else:
            print("✅ Python版本符合要求")
            return True
    
    def check_package(self, package_name: str, import_name: str) -> bool:
        """检查单个包是否可用"""
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False
    
    def get_package_version(self, import_name: str) -> Optional[str]:
        """获取包版本"""
        try:
            module = importlib.import_module(import_name)
            return getattr(module, '__version__', 'unknown')
        except:
            return None
    
    def check_component(self, component: str) -> Dict[str, bool]:
        """检查特定组件的依赖"""
        if component not in DEPENDENCIES:
            print(f"❌ 未知组件: {component}")
            return {}
        
        print(f"\n检查 {component} 组件依赖:")
        print("-" * 40)
        
        results = {}
        for package_name, import_name in DEPENDENCIES[component].items():
            is_available = self.check_package(package_name, import_name)
            version = self.get_package_version(import_name) if is_available else None
            
            status = "✅" if is_available else "❌"
            version_str = f" (v{version})" if version else ""
            print(f"{status} {package_name}{version_str}")
            
            results[package_name] = is_available
            if not is_available:
                self.missing_packages.append(package_name)
                self.failed_imports.append(import_name)
        
        return results
    
    def check_all_dependencies(self, skip_optional: bool = False) -> Dict[str, Dict[str, bool]]:
        """检查所有依赖"""
        print("=" * 50)
        print("水文建模框架 - 依赖检查")
        print("=" * 50)
        
        # 检查Python版本
        self.check_python_version()
        
        all_results = {}
        for component in DEPENDENCIES.keys():
            if skip_optional and component in OPTIONAL_DEPENDENCIES:
                print(f"\n⏭️  跳过可选组件: {component}")
                continue
                
            results = self.check_component(component)
            all_results[component] = results
        
        return all_results
    
    def generate_install_commands(self) -> List[str]:
        """生成安装命令"""
        if not self.missing_packages:
            return []
        
        commands = []
        
        # 基础pip安装命令
        basic_packages = [pkg for pkg in self.missing_packages 
                         if pkg not in ['torch', 'torchvision', 'torchaudio', 'torch-geometric']]
        
        if basic_packages:
            commands.append(f"pip install {' '.join(basic_packages)}")
        
        # PyTorch特殊处理
        torch_packages = [pkg for pkg in self.missing_packages 
                         if pkg in ['torch', 'torchvision', 'torchaudio']]
        if torch_packages:
            commands.append("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu")
        
        # torch-geometric特殊处理
        if 'torch-geometric' in self.missing_packages:
            commands.append("pip install torch-geometric")
        
        return commands
    
    def print_summary(self):
        """打印检查摘要"""
        print("\n" + "=" * 50)
        print("检查摘要")
        print("=" * 50)
        
        total_packages = sum(len(deps) for deps in DEPENDENCIES.values())
        missing_count = len(self.missing_packages)
        installed_count = total_packages - missing_count
        
        print(f"总包数: {total_packages}")
        print(f"已安装: {installed_count}")
        print(f"缺失: {missing_count}")
        
        if self.missing_packages:
            print(f"\n❌ 缺失的包: {', '.join(self.missing_packages)}")
            
            print("\n建议的安装命令:")
            commands = self.generate_install_commands()
            for i, cmd in enumerate(commands, 1):
                print(f"{i}. {cmd}")
            
            # 提供镜像源选项
            print("\n如果网络连接有问题，可以使用国内镜像源:")
            for i, cmd in enumerate(commands, 1):
                mirror_cmd = cmd + " -i https://pypi.tuna.tsinghua.edu.cn/simple"
                print(f"{i}. {mirror_cmd}")
        else:
            print("\n✅ 所有依赖都已正确安装!")
    
    def save_report(self, filename: str = "dependency_report.txt"):
        """保存检查报告到文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("水文建模框架 - 依赖检查报告\n")
            f.write("=" * 40 + "\n\n")
            
            f.write(f"Python版本: {sys.version}\n")
            f.write(f"平台: {platform.platform()}\n\n")
            
            if self.missing_packages:
                f.write("缺失的包:\n")
                for pkg in self.missing_packages:
                    f.write(f"- {pkg}\n")
                
                f.write("\n建议的安装命令:\n")
                commands = self.generate_install_commands()
                for cmd in commands:
                    f.write(f"{cmd}\n")
            else:
                f.write("所有依赖都已正确安装!\n")
        
        print(f"\n📄 报告已保存到: {filename}")

def main():
    parser = argparse.ArgumentParser(description='检查水文建模框架的依赖包')
    parser.add_argument('--component', '-c', 
                       choices=list(DEPENDENCIES.keys()) + ['all'],
                       default='all',
                       help='要检查的组件 (默认: all)')
    parser.add_argument('--skip-optional', '-s', 
                       action='store_true',
                       help='跳过可选依赖检查')
    parser.add_argument('--save-report', '-r',
                       action='store_true', 
                       help='保存检查报告到文件')
    
    args = parser.parse_args()
    
    checker = DependencyChecker()
    
    if args.component == 'all':
        checker.check_all_dependencies(skip_optional=args.skip_optional)
    else:
        checker.check_component(args.component)
    
    checker.print_summary()
    
    if args.save_report:
        checker.save_report()

if __name__ == '__main__':
    main()