#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的API测试脚本
不依赖Flask等外部库，使用Python标准库实现基本的HTTP服务器
"""

import json
import http.server
import socketserver
import urllib.parse
from datetime import datetime
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class HydrologyAPIHandler(http.server.BaseHTTPRequestHandler):
    """水文框架API处理器"""
    
    def do_GET(self):
        """处理GET请求"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        if path == '/health':
            self._handle_health()
        elif path == '/api/models':
            self._handle_models()
        elif path == '/api/simulations':
            self._handle_simulations()
        elif path == '/api/datasets':
            self._handle_datasets()
        else:
            self._send_error(404, 'Not Found')
    
    def do_POST(self):
        """处理POST请求"""
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        
        if path == '/api/auth/login':
            self._handle_login()
        elif path == '/api/simulations':
            self._handle_create_simulation()
        else:
            self._send_error(404, 'Not Found')
    
    def _handle_health(self):
        """健康检查"""
        response = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'services': {
                'api': 'running',
                'database': 'connected',
                'models': 'available'
            }
        }
        self._send_json_response(200, response)
    
    def _handle_models(self):
        """获取模型列表"""
        models = [
            {
                'id': 'xaj',
                'name': 'XinAnJiang Model',
                'description': '新安江模型',
                'parameters': ['K', 'B', 'IM', 'WM', 'WUM', 'WLM', 'C'],
                'type': 'conceptual'
            },
            {
                'id': 'hymod',
                'name': 'HYMOD Model',
                'description': 'HYMOD水文模型',
                'parameters': ['cmax', 'bexp', 'alpha', 'Rs', 'Rq'],
                'type': 'conceptual'
            },
            {
                'id': 'lstm',
                'name': 'LSTM Neural Network',
                'description': 'LSTM神经网络模型',
                'parameters': ['hidden_size', 'num_layers', 'dropout'],
                'type': 'deep_learning'
            }
        ]
        
        response = {
            'success': True,
            'data': models,
            'total': len(models)
        }
        self._send_json_response(200, response)
    
    def _handle_simulations(self):
        """获取仿真列表"""
        simulations = [
            {
                'id': 'sim_001',
                'model_id': 'xaj',
                'status': 'completed',
                'created_at': '2024-01-15T10:30:00',
                'completed_at': '2024-01-15T10:35:00',
                'progress': 100
            },
            {
                'id': 'sim_002',
                'model_id': 'hymod',
                'status': 'running',
                'created_at': '2024-01-15T11:00:00',
                'progress': 65
            }
        ]
        
        response = {
            'success': True,
            'data': simulations,
            'total': len(simulations)
        }
        self._send_json_response(200, response)
    
    def _handle_datasets(self):
        """获取数据集列表"""
        datasets = [
            {
                'id': 'rainfall_data',
                'name': '降雨数据',
                'type': 'time_series',
                'size': '1.2MB',
                'records': 8760,
                'last_updated': '2024-01-15T09:00:00'
            },
            {
                'id': 'flow_data',
                'name': '流量数据',
                'type': 'time_series',
                'size': '856KB',
                'records': 8760,
                'last_updated': '2024-01-15T09:00:00'
            }
        ]
        
        response = {
            'success': True,
            'data': datasets,
            'total': len(datasets)
        }
        self._send_json_response(200, response)
    
    def _handle_login(self):
        """处理登录"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            username = data.get('username')
            password = data.get('password')
            
            # 简单的认证逻辑
            if username == 'admin' and password == 'password':
                response = {
                    'success': True,
                    'token': 'mock_jwt_token_12345',
                    'user': {
                        'id': 1,
                        'username': username,
                        'role': 'admin'
                    }
                }
                self._send_json_response(200, response)
            else:
                self._send_error(401, 'Invalid credentials')
        except Exception as e:
            self._send_error(400, f'Bad request: {str(e)}')
    
    def _handle_create_simulation(self):
        """创建仿真"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            response = {
                'success': True,
                'data': {
                    'id': simulation_id,
                    'model_id': data.get('model_id'),
                    'status': 'created',
                    'created_at': datetime.now().isoformat(),
                    'progress': 0
                }
            }
            self._send_json_response(201, response)
        except Exception as e:
            self._send_error(400, f'Bad request: {str(e)}')
    
    def _send_json_response(self, status_code, data):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        
        json_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(json_data.encode('utf-8'))
    
    def _send_error(self, status_code, message):
        """发送错误响应"""
        error_response = {
            'success': False,
            'error': {
                'code': status_code,
                'message': message
            }
        }
        self._send_json_response(status_code, error_response)
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

def run_server(port=8000):
    """启动服务器"""
    try:
        with socketserver.TCPServer(("", port), HydrologyAPIHandler) as httpd:
            print(f"\n=== 水文框架API服务器 ===")
            print(f"服务器启动成功！")
            print(f"地址: http://localhost:{port}")
            print(f"\n可用的API端点:")
            print(f"  GET  /health              - 健康检查")
            print(f"  POST /api/auth/login      - 用户登录")
            print(f"  GET  /api/models          - 获取模型列表")
            print(f"  GET  /api/simulations     - 获取仿真列表")
            print(f"  POST /api/simulations     - 创建仿真")
            print(f"  GET  /api/datasets        - 获取数据集列表")
            print(f"\n按 Ctrl+C 停止服务器")
            print(f"="*50)
            
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"启动服务器时出错: {e}")

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='水文框架简化API服务器')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口 (默认: 8000)')
    
    args = parser.parse_args()
    run_server(args.port)