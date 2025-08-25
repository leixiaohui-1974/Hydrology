"""
算法优化模块
============

本模块提供水文模型的算法优化功能，包括：
- 线性求解器优化
- 非线性求解器优化
- 数值积分优化
- 微分方程求解优化
- 稀疏矩阵优化
"""

import numpy as np
import logging
import time
from typing import Optional, List, Dict, Any, Callable, Tuple, Union
from scipy import sparse
from scipy.sparse.linalg import spsolve, cg, gmres, spilu
from scipy.optimize import minimize, root_scalar, fsolve
from scipy.integrate import quad, odeint, solve_ivp

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LinearSolverOptimizer:
    """线性求解器优化器"""
    
    def __init__(self, solver_type: str = "auto"):
        self.solver_type = solver_type
        self.solver_stats = {}
        self.available_solvers = {
            'direct': ['spsolve', 'spilu'],
            'iterative': ['cg', 'gmres', 'bicgstab'],
            'auto': ['auto']
        }
        
        logger.info(f"LinearSolverOptimizer initialized: solver_type={solver_type}")
    
    def solve_linear_system(self, A: Union[np.ndarray, sparse.spmatrix], 
                           b: np.ndarray, **kwargs) -> np.ndarray:
        """求解线性系统 Ax = b"""
        start_time = time.time()
        
        # 选择求解器
        solver = self._select_solver(A, b)
        
        try:
            if solver == 'spsolve':
                x = spsolve(A, b)
            elif solver == 'cg':
                x, info = cg(A, b, **kwargs)
            elif solver == 'gmres':
                x, info = gmres(A, b, **kwargs)
            elif solver == 'spilu':
                # 不完全LU分解预处理
                ilu = spilu(A.tocsc())
                x = ilu.solve(b)
            else:
                # 默认使用scipy的spsolve
                x = spsolve(A, b)
            
            solve_time = time.time() - start_time
            
            # 记录统计信息
            self._record_solver_stats(solver, solve_time, A.shape[0])
            
            logger.info(f"Linear system solved using {solver} in {solve_time:.3f}s")
            return x
            
        except Exception as e:
            logger.error(f"Linear solver {solver} failed: {e}")
            # 回退到默认求解器
            logger.info("Falling back to default solver")
            return spsolve(A, b)
    
    def _select_solver(self, A: Union[np.ndarray, sparse.spmatrix], 
                       b: np.ndarray) -> str:
        """选择最优求解器"""
        if self.solver_type == "auto":
            return self._auto_select_solver(A, b)
        elif self.solver_type in self.available_solvers:
            return self.solver_type
        else:
            return 'spsolve'  # 默认
    
    def _auto_select_solver(self, A: Union[np.ndarray, sparse.spmatrix], 
                           b: np.ndarray) -> str:
        """自动选择求解器"""
        n = A.shape[0]
        
        # 根据矩阵大小和稀疏性选择求解器
        if n < 1000:
            # 小矩阵使用直接求解器
            return 'spsolve'
        elif n < 10000:
            # 中等矩阵使用预处理迭代求解器
            return 'spilu'
        else:
            # 大矩阵使用迭代求解器
            return 'cg'
    
    def _record_solver_stats(self, solver: str, solve_time: float, matrix_size: int):
        """记录求解器统计信息"""
        if solver not in self.solver_stats:
            self.solver_stats[solver] = {
                'total_time': 0,
                'total_calls': 0,
                'avg_time': 0,
                'min_time': float('inf'),
                'max_time': 0
            }
        
        stats = self.solver_stats[solver]
        stats['total_time'] += solve_time
        stats['total_calls'] += 1
        stats['avg_time'] = stats['total_time'] / stats['total_calls']
        stats['min_time'] = min(stats['min_time'], solve_time)
        stats['max_time'] = max(stats['max_time'], solve_time)
    
    def get_solver_stats(self) -> Dict[str, Any]:
        """获取求解器统计信息"""
        return self.solver_stats
    
    def benchmark_solvers(self, A: Union[np.ndarray, sparse.spmatrix], 
                         b: np.ndarray, n_runs: int = 5) -> Dict[str, Any]:
        """基准测试不同求解器"""
        logger.info(f"Benchmarking solvers with {n_runs} runs")
        
        results = {}
        solvers = ['spsolve', 'cg', 'gmres', 'spilu']
        
        for solver in solvers:
            times = []
            for i in range(n_runs):
                start_time = time.time()
                try:
                    if solver == 'spsolve':
                        spsolve(A, b)
                    elif solver == 'cg':
                        cg(A, b)[0]
                    elif solver == 'gmres':
                        gmres(A, b)[0]
                    elif solver == 'spilu':
                        ilu = spilu(A.tocsc())
                        ilu.solve(b)
                    
                    solve_time = time.time() - start_time
                    times.append(solve_time)
                    
                except Exception as e:
                    logger.warning(f"Solver {solver} failed: {e}")
                    times.append(float('inf'))
            
            # 过滤掉失败的运行
            valid_times = [t for t in times if t != float('inf')]
            
            if valid_times:
                results[solver] = {
                    'avg_time': np.mean(valid_times),
                    'std_time': np.std(valid_times),
                    'min_time': np.min(valid_times),
                    'max_time': np.max(valid_times),
                    'success_rate': len(valid_times) / n_runs
                }
            else:
                results[solver] = {'error': 'All runs failed'}
        
        logger.info("Benchmarking completed")
        return results

class NonlinearSolverOptimizer:
    """非线性求解器优化器"""
    
    def __init__(self, solver_type: str = "auto"):
        self.solver_type = solver_type
        self.solver_stats = {}
        
        logger.info(f"NonlinearSolverOptimizer initialized: solver_type={solver_type}")
    
    def solve_nonlinear_equation(self, func: Callable, x0: Union[float, np.ndarray], 
                                method: str = "auto", **kwargs) -> Union[float, np.ndarray]:
        """求解非线性方程 f(x) = 0"""
        start_time = time.time()
        
        try:
            if method == "auto":
                method = self._auto_select_method(func, x0)
            
            if method == "root_scalar":
                if isinstance(x0, (int, float)):
                    result = root_scalar(func, x0=x0, **kwargs)
                    x = result.root
                else:
                    raise ValueError("root_scalar requires scalar x0")
            
            elif method == "fsolve":
                x = fsolve(func, x0, **kwargs)
            
            elif method == "minimize":
                # 将方程求解转换为最小化问题
                def objective(x):
                    return np.sum(func(x)**2)
                
                result = minimize(objective, x0, **kwargs)
                x = result.x
            
            else:
                raise ValueError(f"Unknown method: {method}")
            
            solve_time = time.time() - start_time
            
            # 记录统计信息
            self._record_solver_stats(method, solve_time)
            
            logger.info(f"Nonlinear equation solved using {method} in {solve_time:.3f}s")
            return x
            
        except Exception as e:
            logger.error(f"Nonlinear solver {method} failed: {e}")
            raise
    
    def _auto_select_method(self, func: Callable, x0: Union[float, np.ndarray]) -> str:
        """自动选择求解方法"""
        if isinstance(x0, (int, float)):
            return "root_scalar"
        elif isinstance(x0, np.ndarray) and x0.size == 1:
            return "root_scalar"
        else:
            return "fsolve"
    
    def _record_solver_stats(self, method: str, solve_time: float):
        """记录求解器统计信息"""
        if method not in self.solver_stats:
            self.solver_stats[method] = {
                'total_time': 0,
                'total_calls': 0,
                'avg_time': 0
            }
        
        stats = self.solver_stats[method]
        stats['total_time'] += solve_time
        stats['total_calls'] += 1
        stats['avg_time'] = stats['total_time'] / stats['total_calls']
    
    def get_solver_stats(self) -> Dict[str, Any]:
        """获取求解器统计信息"""
        return self.solver_stats

class NumericalIntegrator:
    """数值积分器"""
    
    def __init__(self, method: str = "auto"):
        self.method = method
        self.integration_stats = {}
        
        logger.info(f"NumericalIntegrator initialized: method={method}")
    
    def integrate_function(self, func: Callable, a: float, b: float, 
                          method: str = "auto", **kwargs) -> Tuple[float, float]:
        """数值积分"""
        start_time = time.time()
        
        if method == "auto":
            method = self._auto_select_integration_method(func, a, b)
        
        try:
            if method == "quad":
                result, error = quad(func, a, b, **kwargs)
            else:
                # 默认使用quad
                result, error = quad(func, a, b, **kwargs)
            
            integration_time = time.time() - start_time
            
            # 记录统计信息
            self._record_integration_stats(method, integration_time)
            
            logger.info(f"Integration completed using {method} in {integration_time:.3f}s")
            return result, error
            
        except Exception as e:
            logger.error(f"Integration method {method} failed: {e}")
            raise
    
    def integrate_ode(self, func: Callable, t_span: Tuple[float, float], 
                      y0: np.ndarray, method: str = "auto", **kwargs) -> np.ndarray:
        """求解常微分方程"""
        start_time = time.time()
        
        if method == "auto":
            method = self._auto_select_ode_method(func, t_span, y0)
        
        try:
            if method == "odeint":
                solution = odeint(func, y0, np.linspace(t_span[0], t_span[1], 100), **kwargs)
            elif method == "solve_ivp":
                solution = solve_ivp(func, t_span, y0, **kwargs)
                solution = solution.y.T
            else:
                # 默认使用odeint
                solution = odeint(func, y0, np.linspace(t_span[0], t_span[1], 100), **kwargs)
            
            integration_time = time.time() - start_time
            
            # 记录统计信息
            self._record_integration_stats(method, integration_time)
            
            logger.info(f"ODE integration completed using {method} in {integration_time:.3f}s")
            return solution
            
        except Exception as e:
            logger.error(f"ODE integration method {method} failed: {e}")
            raise
    
    def _auto_select_integration_method(self, func: Callable, a: float, b: float) -> str:
        """自动选择积分方法"""
        # 简化的自动选择逻辑
        return "quad"
    
    def _auto_select_ode_method(self, func: Callable, t_span: Tuple[float, float], 
                               y0: np.ndarray) -> str:
        """自动选择ODE求解方法"""
        # 简化的自动选择逻辑
        return "odeint"
    
    def _record_integration_stats(self, method: str, integration_time: float):
        """记录积分统计信息"""
        if method not in self.integration_stats:
            self.integration_stats[method] = {
                'total_time': 0,
                'total_calls': 0,
                'avg_time': 0
            }
        
        stats = self.integration_stats[method]
        stats['total_time'] += integration_time
        stats['total_calls'] += 1
        stats['avg_time'] = stats['total_time'] / stats['total_calls']
    
    def get_integration_stats(self) -> Dict[str, Any]:
        """获取积分统计信息"""
        return self.integration_stats

class DifferentialEquationSolver:
    """微分方程求解器"""
    
    def __init__(self, solver_type: str = "auto"):
        self.solver_type = solver_type
        self.solver_stats = {}
        
        logger.info(f"DifferentialEquationSolver initialized: solver_type={solver_type}")
    
    def solve_initial_value_problem(self, func: Callable, t_span: Tuple[float, float], 
                                   y0: np.ndarray, method: str = "auto", **kwargs) -> Dict[str, Any]:
        """求解初值问题"""
        start_time = time.time()
        
        if method == "auto":
            method = self._auto_select_ode_method(func, t_span, y0)
        
        try:
            if method == "solve_ivp":
                solution = solve_ivp(func, t_span, y0, method='RK45', **kwargs)
                result = {
                    't': solution.t,
                    'y': solution.y,
                    'success': solution.success,
                    'message': solution.message
                }
            elif method == "odeint":
                t = np.linspace(t_span[0], t_span[1], 100)
                y = odeint(func, y0, t, **kwargs)
                result = {
                    't': t,
                    'y': y.T,
                    'success': True,
                    'message': 'odeint completed successfully'
                }
            else:
                raise ValueError(f"Unknown method: {method}")
            
            solve_time = time.time() - start_time
            
            # 记录统计信息
            self._record_solver_stats(method, solve_time)
            
            logger.info(f"ODE solved using {method} in {solve_time:.3f}s")
            return result
            
        except Exception as e:
            logger.error(f"ODE solver {method} failed: {e}")
            raise
    
    def solve_boundary_value_problem(self, func: Callable, bc_func: Callable, 
                                   t_span: Tuple[float, float], y0: np.ndarray,
                                   method: str = "shooting", **kwargs) -> Dict[str, Any]:
        """求解边值问题（简化实现）"""
        logger.warning("Boundary value problem solver is simplified")
        
        # 这里使用简化的打靶法
        try:
            # 使用初值问题求解器
            result = self.solve_initial_value_problem(func, t_span, y0, **kwargs)
            result['method'] = 'shooting'
            return result
        except Exception as e:
            logger.error(f"BVP solver failed: {e}")
            raise
    
    def _auto_select_ode_method(self, func: Callable, t_span: Tuple[float, float], 
                               y0: np.ndarray) -> str:
        """自动选择ODE求解方法"""
        # 简化的自动选择逻辑
        return "solve_ivp"
    
    def _record_solver_stats(self, method: str, solve_time: float):
        """记录求解器统计信息"""
        if method not in self.solver_stats:
            self.solver_stats[method] = {
                'total_time': 0,
                'total_calls': 0,
                'avg_time': 0
            }
        
        stats = self.solver_stats[method]
        stats['total_time'] += solve_time
        stats['total_calls'] += 1
        stats['avg_time'] = stats['total_time'] / stats['total_calls']
    
    def get_solver_stats(self) -> Dict[str, Any]:
        """获取求解器统计信息"""
        return self.solver_stats

class SparseMatrixOptimizer:
    """稀疏矩阵优化器"""
    
    def __init__(self):
        self.optimization_stats = {}
        
        logger.info("SparseMatrixOptimizer initialized")
    
    def optimize_matrix_storage(self, A: Union[np.ndarray, sparse.spmatrix]) -> sparse.spmatrix:
        """优化矩阵存储格式"""
        start_time = time.time()
        
        try:
            if not sparse.issparse(A):
                # 转换为稀疏矩阵
                A_sparse = sparse.csr_matrix(A)
            else:
                A_sparse = A
            
            # 选择最优存储格式
            optimal_format = self._select_optimal_format(A_sparse)
            
            if optimal_format == 'csr':
                A_optimized = A_sparse.tocsr()
            elif optimal_format == 'csc':
                A_optimized = A_sparse.tocsc()
            elif optimal_format == 'coo':
                A_optimized = A_sparse.tocoo()
            else:
                A_optimized = A_sparse
            
            optimization_time = time.time() - start_time
            
            # 记录统计信息
            self._record_optimization_stats('storage', optimization_time)
            
            logger.info(f"Matrix storage optimized to {optimal_format} in {optimization_time:.3f}s")
            return A_optimized
            
        except Exception as e:
            logger.error(f"Matrix storage optimization failed: {e}")
            return A if sparse.issparse(A) else sparse.csr_matrix(A)
    
    def _select_optimal_format(self, A: sparse.spmatrix) -> str:
        """选择最优存储格式"""
        # 简化的选择逻辑
        if A.shape[0] == A.shape[1]:  # 方阵
            return 'csr'
        else:  # 非方阵
            return 'csc'
    
    def optimize_matrix_operations(self, A: sparse.spmatrix, operation: str) -> sparse.spmatrix:
        """优化矩阵运算"""
        start_time = time.time()
        
        try:
            if operation == "transpose":
                result = A.T
            elif operation == "inverse":
                # 对于稀疏矩阵，使用伪逆
                result = sparse.linalg.pinv(A)
            elif operation == "power":
                # 矩阵幂运算
                result = A ** 2
            else:
                result = A
            
            optimization_time = time.time() - start_time
            
            # 记录统计信息
            self._record_optimization_stats(operation, optimization_time)
            
            logger.info(f"Matrix operation {operation} optimized in {optimization_time:.3f}s")
            return result
            
        except Exception as e:
            logger.error(f"Matrix operation optimization failed: {e}")
            return A
    
    def _record_optimization_stats(self, operation: str, optimization_time: float):
        """记录优化统计信息"""
        if operation not in self.optimization_stats:
            self.optimization_stats[operation] = {
                'total_time': 0,
                'total_calls': 0,
                'avg_time': 0
            }
        
        stats = self.optimization_stats[operation]
        stats['total_time'] += optimization_time
        stats['total_calls'] += 1
        stats['avg_time'] = stats['total_time'] / stats['total_calls']
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        return self.optimization_stats

