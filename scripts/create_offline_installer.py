#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线安装包创建工具

此脚本用于创建水文建模框架的离线安装包，包括：
1. 下载所有依赖包
2. 创建离线安装脚本
3. 生成安装指南
4. 打包所有文件

使用方法:
    python create_offline_installer.py [--output-dir OUTPUT_DIR] [--python-version PYTHON_VERSION]
"""

import os
import sys
import subprocess
import argparse
import shutil
import zipfile
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class OfflineInstallerCreator:
    """离线安装包创建器"""
    
    def __init__(self, output_dir: str = "offline_installer", python_version: str = None):
        self.output_dir = Path(output_dir)
        self.python_version = python_version or f"{sys.version_info.major}.{sys.version_info.minor}"
        self.packages_dir = self.output_dir / "packages"
        self.scripts_dir = self.output_dir / "scripts"
        self.docs_dir = self.output_dir / "docs"
        
        # 创建目录结构
        self._create_directories()
        
        # 依赖包分组
        self.package_groups = {
            "core": [
                "numpy>=1.20.0",
                "pandas>=1.3.0",
                "pyyaml>=5.4.0",
                "scipy>=1.7.0"
            ],
            "visualization": [
                "matplotlib>=3.4.0",
                "plotly>=5.0.0",
                "seaborn>=0.11.0"
            ],
            "gui": [
                "eel>=0.14.0",
                "dash>=2.0.0",
                "dash-bootstrap-components>=1.0.0"
            ],
            "gis": [
                "geopandas>=0.10.0",
                "rasterio>=1.2.0",
                "pykrige>=1.6.0",
                "geovoronoi>=0.4.0",
                "whitebox>=2.0.0"
            ],
            "ml": [
                "scikit-learn>=1.0.0",
                "xgboost>=1.5.0",
                "lightgbm>=3.3.0",
                "torch>=1.10.0",
                "torch-geometric>=2.0.0"
            ],
            "database": [
                "sqlalchemy>=1.4.0"
            ],
            "stats": [
                "emcee>=3.1.0",
                "corner>=2.2.0"
            ],
            "utils": [
                "psutil>=5.8.0",
                "gitpython>=3.1.0",
                "schedule>=1.1.0",
                "joblib>=1.1.0",
                "lz4>=3.1.0"
            ]
        }
    
    def _create_directories(self):
        """创建必要的目录结构"""
        for directory in [self.output_dir, self.packages_dir, self.scripts_dir, self.docs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        print(f"✅ 创建目录结构: {self.output_dir}")
    
    def download_packages(self, groups: List[str] = None, platform: str = None) -> bool:
        """下载指定组的依赖包"""
        if groups is None:
            groups = list(self.package_groups.keys())
        
        print(f"📦 开始下载依赖包...")
        print(f"🎯 目标组: {', '.join(groups)}")
        
        all_packages = []
        for group in groups:
            if group in self.package_groups:
                all_packages.extend(self.package_groups[group])
            else:
                print(f"⚠️  未知的包组: {group}")
        
        if not all_packages:
            print("❌ 没有找到要下载的包")
            return False
        
        # 创建临时requirements文件
        temp_requirements = self.output_dir / "temp_requirements.txt"
        with open(temp_requirements, 'w', encoding='utf-8') as f:
            for package in all_packages:
                f.write(f"{package}\n")
        
        try:
            # 构建pip download命令
            cmd = [
                sys.executable, "-m", "pip", "download",
                "-r", str(temp_requirements),
                "-d", str(self.packages_dir),
                "--no-deps"  # 不下载依赖的依赖，避免版本冲突
            ]
            
            # 添加平台特定选项
            if platform:
                cmd.extend(["--platform", platform])
            
            print(f"🔄 执行命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode == 0:
                print("✅ 依赖包下载完成")
                
                # 下载依赖的依赖
                self._download_dependencies(all_packages)
                
                # 清理临时文件
                temp_requirements.unlink()
                return True
            else:
                print(f"❌ 下载失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ 下载过程中出错: {str(e)}")
            return False
    
    def _download_dependencies(self, packages: List[str]):
        """下载包的依赖项"""
        print("📦 下载依赖项...")
        
        # 创建完整的requirements文件（包含依赖）
        full_requirements = self.output_dir / "full_requirements.txt"
        with open(full_requirements, 'w', encoding='utf-8') as f:
            for package in packages:
                f.write(f"{package}\n")
        
        try:
            cmd = [
                sys.executable, "-m", "pip", "download",
                "-r", str(full_requirements),
                "-d", str(self.packages_dir)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode == 0:
                print("✅ 依赖项下载完成")
            else:
                print(f"⚠️  部分依赖项下载失败: {result.stderr}")
            
            # 清理临时文件
            full_requirements.unlink()
            
        except Exception as e:
            print(f"⚠️  下载依赖项时出错: {str(e)}")
    
    def create_install_scripts(self):
        """创建安装脚本"""
        print("📝 创建安装脚本...")
        
        # Windows批处理脚本
        windows_script = self.scripts_dir / "install_windows.bat"
        with open(windows_script, 'w', encoding='utf-8') as f:
            f.write(self._get_windows_install_script())
        
        # Linux/macOS shell脚本
        unix_script = self.scripts_dir / "install_unix.sh"
        with open(unix_script, 'w', encoding='utf-8') as f:
            f.write(self._get_unix_install_script())
        
        # 使shell脚本可执行
        try:
            os.chmod(unix_script, 0o755)
        except:
            pass  # Windows上可能会失败
        
        # Python安装脚本
        python_script = self.scripts_dir / "install.py"
        with open(python_script, 'w', encoding='utf-8') as f:
            f.write(self._get_python_install_script())
        
        print("✅ 安装脚本创建完成")
    
    def _get_windows_install_script(self) -> str:
        """生成Windows安装脚本"""
        return '''
@echo off
echo ========================================
echo 水文建模框架离线安装程序 (Windows)
echo ========================================
echo.

echo 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

echo Python环境检查通过
echo.

echo 开始安装依赖包...
python -m pip install --no-index --find-links ../packages -r ../requirements.txt

if errorlevel 1 (
    echo 安装失败，请检查错误信息
    pause
    exit /b 1
)

echo.
echo ========================================
echo 安装完成！
echo ========================================
echo.
echo 运行以下命令验证安装:
echo python -c "import numpy, pandas, matplotlib; print('安装成功!')"
echo.
pause
'''
    
    def _get_unix_install_script(self) -> str:
        """生成Unix安装脚本"""
        return '''
#!/bin/bash

echo "========================================"
echo "水文建模框架离线安装程序 (Unix/Linux/macOS)"
echo "========================================"
echo

echo "检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python 3.8+"
    exit 1
fi

echo "Python环境检查通过"
echo

echo "开始安装依赖包..."
python3 -m pip install --no-index --find-links ../packages -r ../requirements.txt

if [ $? -ne 0 ]; then
    echo "安装失败，请检查错误信息"
    exit 1
fi

echo
echo "========================================"
echo "安装完成！"
echo "========================================"
echo
echo "运行以下命令验证安装:"
echo "python3 -c \"import numpy, pandas, matplotlib; print('安装成功!')\""
echo
'''
    
    def _get_python_install_script(self) -> str:
        """生成Python安装脚本"""
        return '''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水文建模框架离线安装程序
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    if sys.version_info < (3, 8):
        print("❌ 错误: 需要Python 3.8或更高版本")
        print(f"   当前版本: {sys.version}")
        return False
    print(f"✅ Python版本检查通过: {sys.version}")
    return True

def install_packages():
    """安装依赖包"""
    packages_dir = Path(__file__).parent.parent / "packages"
    requirements_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not packages_dir.exists():
        print(f"❌ 错误: 找不到包目录 {packages_dir}")
        return False
    
    if not requirements_file.exists():
        print(f"❌ 错误: 找不到requirements文件 {requirements_file}")
        return False
    
    print("📦 开始安装依赖包...")
    
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--no-index",
        "--find-links", str(packages_dir),
        "-r", str(requirements_file)
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ 依赖包安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 安装失败: {e.stderr}")
        return False

def verify_installation():
    """验证安装"""
    print("🔍 验证安装...")
    
    test_imports = [
        "numpy", "pandas", "matplotlib", "yaml", "scipy"
    ]
    
    failed_imports = []
    for module in test_imports:
        try:
            __import__(module)
            print(f"  ✅ {module}")
        except ImportError:
            print(f"  ❌ {module}")
            failed_imports.append(module)
    
    if failed_imports:
        print(f"\n⚠️  以下模块导入失败: {', '.join(failed_imports)}")
        return False
    else:
        print("\n🎉 所有核心模块验证通过！")
        return True

def main():
    print("========================================")
    print("水文建模框架离线安装程序")
    print("========================================")
    print()
    
    if not check_python_version():
        return 1
    
    if not install_packages():
        return 1
    
    if not verify_installation():
        print("\n⚠️  安装可能不完整，请检查错误信息")
        return 1
    
    print("\n========================================")
    print("🎉 安装完成！")
    print("========================================")
    print("\n现在可以使用水文建模框架了。")
    print("运行示例: python examples/run_example.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''
    
    def create_documentation(self):
        """创建离线安装文档"""
        print("📚 创建安装文档...")
        
        # 创建README
        readme_file = self.output_dir / "README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(self._get_offline_readme())
        
        # 创建requirements.txt
        requirements_file = self.output_dir / "requirements.txt"
        with open(requirements_file, 'w', encoding='utf-8') as f:
            for group_packages in self.package_groups.values():
                for package in group_packages:
                    f.write(f"{package}\n")
        
        # 创建安装信息文件
        info_file = self.output_dir / "install_info.json"
        install_info = {
            "created_at": datetime.now().isoformat(),
            "python_version": self.python_version,
            "platform": sys.platform,
            "package_groups": self.package_groups,
            "total_packages": sum(len(packages) for packages in self.package_groups.values())
        }
        
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(install_info, f, indent=2, ensure_ascii=False)
        
        print("✅ 安装文档创建完成")
    
    def _get_offline_readme(self) -> str:
        """生成离线安装README"""
        return f'''
# 水文建模框架离线安装包

本离线安装包包含了水文建模框架运行所需的所有Python依赖包。

## 系统要求

- Python {self.python_version}+
- 操作系统: Windows, macOS, 或 Linux
- 可用磁盘空间: 至少2GB

## 安装方法

### 方法1: 使用自动安装脚本

#### Windows用户
```cmd
cd scripts
install_windows.bat
```

#### macOS/Linux用户
```bash
cd scripts
./install_unix.sh
```

#### 跨平台Python脚本
```bash
cd scripts
python install.py
```

### 方法2: 手动安装

```bash
# 安装所有依赖
pip install --no-index --find-links packages -r requirements.txt

# 验证安装
python -c "import numpy, pandas, matplotlib; print('安装成功!')"
```

## 包含的组件

- **核心组件**: numpy, pandas, scipy, pyyaml
- **可视化**: matplotlib, plotly, seaborn
- **GUI界面**: eel, dash
- **GIS处理**: geopandas, rasterio
- **机器学习**: scikit-learn, xgboost, pytorch
- **数据库**: sqlalchemy
- **统计分析**: emcee, corner
- **实用工具**: psutil, gitpython

## 故障排除

### 常见问题

1. **权限错误**
   - Windows: 以管理员身份运行命令提示符
   - macOS/Linux: 使用 `sudo` 或虚拟环境

2. **Python版本不兼容**
   - 确保使用Python 3.8或更高版本
   - 使用 `python --version` 检查版本

3. **磁盘空间不足**
   - 确保有足够的磁盘空间（推荐2GB+）
   - 清理临时文件和缓存

4. **网络相关错误**
   - 本安装包为离线安装，不需要网络连接
   - 如果仍有网络错误，使用 `--no-deps` 参数

### 获取帮助

如果遇到问题：
1. 检查 `install_info.json` 文件了解安装包信息
2. 查看错误日志定位问题
3. 参考主项目的 `INSTALL_GUIDE.md`
4. 在GitHub仓库提交Issue

## 文件结构

```
offline_installer/
├── README.md              # 本文件
├── requirements.txt       # 依赖列表
├── install_info.json     # 安装包信息
├── packages/             # 离线依赖包
├── scripts/              # 安装脚本
│   ├── install.py        # Python安装脚本
│   ├── install_windows.bat  # Windows批处理脚本
│   └── install_unix.sh   # Unix/Linux shell脚本
└── docs/                 # 文档目录
```

---

创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Python版本: {self.python_version}
平台: {sys.platform}
'''
    
    def create_archive(self, archive_name: str = None) -> Path:
        """创建压缩包"""
        if archive_name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = f"hydrology_offline_installer_{timestamp}.zip"
        
        archive_path = self.output_dir.parent / archive_name
        
        print(f"📦 创建压缩包: {archive_path}")
        
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    file_path = Path(root) / file
                    arc_name = file_path.relative_to(self.output_dir.parent)
                    zipf.write(file_path, arc_name)
        
        print(f"✅ 压缩包创建完成: {archive_path}")
        print(f"📊 文件大小: {archive_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        return archive_path
    
    def get_package_info(self) -> Dict:
        """获取包信息统计"""
        package_files = list(self.packages_dir.glob("*.whl")) + list(self.packages_dir.glob("*.tar.gz"))
        
        total_size = sum(f.stat().st_size for f in package_files)
        
        return {
            "total_packages": len(package_files),
            "total_size_mb": total_size / 1024 / 1024,
            "package_files": [f.name for f in package_files]
        }


def main():
    parser = argparse.ArgumentParser(description="创建水文建模框架离线安装包")
    parser.add_argument("--output-dir", default="offline_installer", help="输出目录")
    parser.add_argument("--python-version", help="目标Python版本")
    parser.add_argument("--groups", nargs="+", help="要包含的包组", 
                       choices=["core", "visualization", "gui", "gis", "ml", "database", "stats", "utils"])
    parser.add_argument("--platform", help="目标平台")
    parser.add_argument("--no-archive", action="store_true", help="不创建压缩包")
    parser.add_argument("--archive-name", help="压缩包名称")
    
    args = parser.parse_args()
    
    print("🚀 开始创建离线安装包...")
    print(f"📁 输出目录: {args.output_dir}")
    
    creator = OfflineInstallerCreator(args.output_dir, args.python_version)
    
    # 下载包
    if not creator.download_packages(args.groups, args.platform):
        print("❌ 下载失败，退出")
        return 1
    
    # 创建脚本和文档
    creator.create_install_scripts()
    creator.create_documentation()
    
    # 显示统计信息
    info = creator.get_package_info()
    print(f"\n📊 统计信息:")
    print(f"   包数量: {info['total_packages']}")
    print(f"   总大小: {info['total_size_mb']:.1f} MB")
    
    # 创建压缩包
    if not args.no_archive:
        archive_path = creator.create_archive(args.archive_name)
        print(f"\n🎉 离线安装包创建完成: {archive_path}")
    else:
        print(f"\n🎉 离线安装包创建完成: {creator.output_dir}")
    
    print("\n📋 使用说明:")
    print("   1. 将安装包复制到目标机器")
    print("   2. 解压并运行安装脚本")
    print("   3. 按照README.md中的说明操作")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())