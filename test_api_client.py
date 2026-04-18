#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API客户端测试脚本
测试水文框架API的各个端点
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

class APIClient:
    """API客户端"""
    
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
        self.token = None
    
    def _make_request(self, method, endpoint, data=None, headers=None):
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                req = urllib.request.Request(url, headers=headers)
            else:
                json_data = json.dumps(data).encode('utf-8') if data else None
                req = urllib.request.Request(url, data=json_data, headers=headers)
                req.get_method = lambda: method
            
            with urllib.request.urlopen(req) as response:
                response_data = response.read().decode('utf-8')
                return json.loads(response_data), response.status
        
        except urllib.error.HTTPError as e:
            error_data = e.read().decode('utf-8')
            try:
                return json.loads(error_data), e.code
            except:
                return {'error': error_data}, e.code
        except Exception as e:
            return {'error': str(e)}, 500
    
    def test_health(self):
        """测试健康检查"""
        print("\n=== 测试健康检查 ===")
        response, status = self._make_request('GET', '/health')
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 200
    
    def test_login(self, username="admin", password="password"):
        """测试用户登录"""
        print("\n=== 测试用户登录 ===")
        data = {'username': username, 'password': password}
        response, status = self._make_request('POST', '/api/auth/login', data)
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        
        if status == 200 and response.get('success'):
            self.token = response.get('token')
            print(f"登录成功，获取到token: {self.token}")
            return True
        return False
    
    def test_models(self):
        """测试获取模型列表"""
        print("\n=== 测试获取模型列表 ===")
        response, status = self._make_request('GET', '/api/models')
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 200
    
    def test_simulations(self):
        """测试获取仿真列表"""
        print("\n=== 测试获取仿真列表 ===")
        response, status = self._make_request('GET', '/api/simulations')
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 200
    
    def test_create_simulation(self):
        """测试创建仿真"""
        print("\n=== 测试创建仿真 ===")
        data = {
            'model_id': 'xaj',
            'parameters': {
                'K': 0.5,
                'B': 0.3,
                'IM': 0.01
            },
            'dataset_id': 'rainfall_data'
        }
        response, status = self._make_request('POST', '/api/simulations', data)
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 201
    
    def test_datasets(self):
        """测试获取数据集列表"""
        print("\n=== 测试获取数据集列表 ===")
        response, status = self._make_request('GET', '/api/datasets')
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 200
    
    def test_invalid_endpoint(self):
        """测试无效端点"""
        print("\n=== 测试无效端点 ===")
        response, status = self._make_request('GET', '/api/invalid')
        print(f"状态码: {status}")
        print(f"响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return status == 404
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("开始API功能测试")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"API地址: {self.base_url}")
        print("="*60)
        
        tests = [
            ('健康检查', self.test_health),
            ('用户登录', self.test_login),
            ('获取模型列表', self.test_models),
            ('获取仿真列表', self.test_simulations),
            ('创建仿真', self.test_create_simulation),
            ('获取数据集列表', self.test_datasets),
            ('无效端点', self.test_invalid_endpoint)
        ]
        
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"测试 '{test_name}' 出错: {e}")
                results.append((test_name, False))
        
        # 输出测试结果摘要
        print("\n" + "="*60)
        print("测试结果摘要")
        print("="*60)
        
        passed = 0
        for test_name, result in results:
            status = "✓ 通过" if result else "✗ 失败"
            print(f"{test_name:<20} {status}")
            if result:
                passed += 1
        
        print(f"\n总计: {passed}/{len(results)} 个测试通过")
        print(f"成功率: {passed/len(results)*100:.1f}%")
        
        if passed == len(results):
            print("\n🎉 所有API测试通过！")
        else:
            print(f"\n⚠️  有 {len(results)-passed} 个测试失败")
        
        return passed == len(results)

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='水文框架API客户端测试')
    parser.add_argument('--url', default='http://localhost:8080', help='API服务器地址')
    parser.add_argument('--test', choices=['health', 'login', 'models', 'simulations', 'datasets', 'all'], 
                       default='all', help='要运行的测试')
    
    args = parser.parse_args()
    
    client = APIClient(args.url)
    
    if args.test == 'all':
        client.run_all_tests()
    elif args.test == 'health':
        client.test_health()
    elif args.test == 'login':
        client.test_login()
    elif args.test == 'models':
        client.test_models()
    elif args.test == 'simulations':
        client.test_simulations()
    elif args.test == 'datasets':
        client.test_datasets()

if __name__ == '__main__':
    main()