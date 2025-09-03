# 水文建模框架安装指南

本指南提供了详细的安装步骤和常见问题解决方案，帮助您快速搭建水文建模框架的运行环境。

## 目录

- [系统要求](#系统要求)
- [快速安装](#快速安装)
- [详细安装步骤](#详细安装步骤)
- [依赖检查](#依赖检查)
- [常见问题](#常见问题)
- [离线安装](#离线安装)
- [开发环境设置](#开发环境设置)

## 系统要求

### 基本要求
- **Python**: 3.8 或更高版本
- **操作系统**: Windows 10+, macOS 10.14+, Ubuntu 18.04+
- **内存**: 最少 4GB RAM (推荐 8GB+)
- **存储**: 至少 2GB 可用空间

### 推荐配置
- **Python**: 3.9 或 3.10
- **内存**: 16GB RAM
- **GPU**: 支持CUDA的NVIDIA显卡 (用于深度学习模型)

## 快速安装

### 方法1: 使用pip安装所有依赖

```bash
# 克隆项目
git clone https://github.com/your-repo/Hydrology.git
cd Hydrology

# 创建虚拟环境 (推荐)
python -m venv hydrology_env

# 激活虚拟环境
# Windows:
hydrology_env\Scripts\activate
# macOS/Linux:
source hydrology_env/bin/activate

# 安装依赖
pip install -r requirements.txt

# 检查安装
python check_dependencies.py
```

### 方法2: 使用conda安装

```bash
# 创建conda环境
conda create -n hydrology python=3.9
conda activate hydrology

# 安装基础科学计算包
conda install numpy pandas matplotlib scipy pyyaml

# 安装其他依赖
pip install -r requirements.txt
```

## 详细安装步骤

### 步骤1: 准备Python环境

#### Windows用户
1. 从 [python.org](https://www.python.org/downloads/) 下载Python 3.9+
2. 安装时勾选 "Add Python to PATH"
3. 验证安装: `python --version`

#### macOS用户
```bash
# 使用Homebrew安装
brew install python@3.9

# 或使用pyenv管理多个Python版本
brew install pyenv
pyenv install 3.9.16
pyenv global 3.9.16
```

#### Ubuntu/Debian用户
```bash
sudo apt update
sudo apt install python3.9 python3.9-venv python3.9-dev
```

### 步骤2: 创建虚拟环境

```bash
# 创建虚拟环境
python -m venv hydrology_env

# 激活虚拟环境
# Windows PowerShell:
hydrology_env\Scripts\Activate.ps1
# Windows CMD:
hydrology_env\Scripts\activate.bat
# macOS/Linux:
source hydrology_env/bin/activate

# 升级pip
python -m pip install --upgrade pip
```

### 步骤3: 安装核心依赖

```bash
# 安装核心科学计算包
pip install numpy pandas matplotlib scipy pyyaml

# 安装GUI相关包
pip install eel dash plotly dash-bootstrap-components

# 安装GIS处理包
pip install geopandas rasterio

# 安装机器学习包
pip install scikit-learn xgboost lightgbm
```

### 步骤4: 安装PyTorch (用于深度学习)

#### CPU版本
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

#### GPU版本 (CUDA 11.8)
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

#### 安装torch-geometric
```bash
pip install torch-geometric
```

### 步骤5: 安装其他依赖

```bash
# 统计和不确定性分析
pip install emcee corner seaborn

# 数据库支持
pip install sqlalchemy

# 实用工具
pip install easygui psutil gitpython schedule lz4

# GIS高级功能
pip install whitebox pykrige geovoronoi
```

## 依赖检查

使用我们提供的依赖检查脚本来验证安装:

```bash
# 检查所有依赖
python check_dependencies.py

# 只检查核心依赖
python check_dependencies.py --component core

# 检查特定组件
python check_dependencies.py --component gui
python check_dependencies.py --component ml
python check_dependencies.py --component gis

# 跳过可选依赖
python check_dependencies.py --skip-optional

# 生成检查报告
python check_dependencies.py --save-report
```

## 常见问题

### 问题1: pip安装失败 - 网络连接错误

**解决方案**: 使用国内镜像源

```bash
# 临时使用镜像源
pip install package_name -i https://pypi.tuna.tsinghua.edu.cn/simple

# 永久配置镜像源
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

**其他可用镜像源**:
- 阿里云: `https://mirrors.aliyun.com/pypi/simple/`
- 豆瓣: `https://pypi.douban.com/simple/`
- 华为云: `https://mirrors.huaweicloud.com/repository/pypi/simple/`

### 问题2: SSL证书验证错误

```bash
# 临时跳过SSL验证 (不推荐用于生产环境)
pip install package_name --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

### 问题3: 权限错误 (Windows)

```bash
# 以管理员身份运行PowerShell
# 或使用用户级安装
pip install package_name --user
```

### 问题4: geopandas安装失败

**Windows用户**:
```bash
# 先安装依赖
conda install geopandas
# 或使用预编译轮子
pip install geopandas --find-links https://girder.github.io/large_image_wheels
```

**macOS用户**:
```bash
# 安装系统依赖
brew install gdal geos proj
pip install geopandas
```

**Ubuntu用户**:
```bash
sudo apt install gdal-bin libgdal-dev libgeos-dev libproj-dev
pip install geopandas
```

### 问题5: PyTorch安装问题

1. **检查CUDA版本** (如果使用GPU):
   ```bash
   nvidia-smi
   ```

2. **选择正确的PyTorch版本**:
   访问 [PyTorch官网](https://pytorch.org/get-started/locally/) 获取适合您系统的安装命令

### 问题6: 内存不足

```bash
# 增加pip的超时时间和重试次数
pip install package_name --timeout 1000 --retries 5

# 清理pip缓存
pip cache purge
```

## 离线安装

### 准备离线包

在有网络的机器上:

```bash
# 下载所有依赖包
pip download -r requirements.txt -d offline_packages/

# 创建离线安装脚本
echo "pip install --no-index --find-links offline_packages/ -r requirements.txt" > install_offline.sh
```

### 离线安装

在目标机器上:

```bash
# 复制offline_packages文件夹到目标机器
# 运行离线安装
bash install_offline.sh
```

## 开发环境设置

### 安装开发工具

```bash
# 代码格式化和检查
pip install black flake8 isort mypy

# 测试工具
pip install pytest pytest-cov

# 文档生成
pip install sphinx sphinx-rtd-theme

# Jupyter支持
pip install jupyter ipykernel
python -m ipykernel install --user --name hydrology
```

### 配置IDE

#### VS Code
1. 安装Python扩展
2. 选择正确的Python解释器 (`Ctrl+Shift+P` -> "Python: Select Interpreter")
3. 配置工作区设置:

```json
{
    "python.defaultInterpreterPath": "./hydrology_env/Scripts/python.exe",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.flake8Enabled": true
}
```

#### PyCharm
1. 打开项目
2. File -> Settings -> Project -> Python Interpreter
3. 添加虚拟环境解释器

## 验证安装

运行测试脚本验证安装:

```bash
# 运行依赖检查
python check_dependencies.py

# 运行简单测试
python -c "from common.config_parser import ConfigParser; print('Core modules OK')"

# 运行示例
python examples/run_example.py
```

## 获取帮助

如果遇到问题:

1. **检查依赖**: 运行 `python check_dependencies.py --save-report`
2. **查看日志**: 检查错误信息和堆栈跟踪
3. **搜索文档**: 查看 `docs/` 目录下的相关文档
4. **提交Issue**: 在GitHub仓库提交问题报告

## 更新和维护

### 更新依赖

```bash
# 更新所有包到最新版本
pip list --outdated
pip install --upgrade package_name

# 或批量更新
pip freeze > current_requirements.txt
pip install --upgrade -r requirements.txt
```

### 环境备份

```bash
# 导出当前环境
pip freeze > my_requirements.txt
conda env export > environment.yml  # 如果使用conda

# 恢复环境
pip install -r my_requirements.txt
conda env create -f environment.yml
```

---

**注意**: 本指南会持续更新。如有问题或建议，请提交Issue或Pull Request。