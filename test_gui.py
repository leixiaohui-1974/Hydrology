import sys
import os
# 将项目根目录和gui目录添加到Python路径中
project_root = os.path.join(os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(project_root))
sys.path.insert(0, os.path.abspath(os.path.join(project_root, 'gui')))

import eel
import time

# 初始化Eel
web_dir = os.path.join(os.path.dirname(__file__), 'gui', 'web')
eel.init(web_dir)

def main():
    print("Starting GUI test...")
    try:
        # 使用指定的端口8085，避免端口冲突
        eel.start('index.html', size=(1280, 800), port=8085, mode='chrome-app')
        print("GUI started successfully on port 8085")
    except Exception as e:
        print(f"Failed to start GUI: {e}")
        # 如果端口8085也被占用，尝试其他端口
        try:
            eel.start('index.html', size=(1280, 800), port=8086, mode='chrome-app')
            print("GUI started successfully on port 8086")
        except Exception as e2:
            print(f"Failed to start GUI on alternative port: {e2}")

if __name__ == "__main__":
    main()