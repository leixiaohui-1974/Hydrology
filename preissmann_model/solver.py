"""
Solver Module
=============

This module contains the numerical solvers required for the hydraulic model,
specifically the Double-Sweep (Thomas) algorithm for block-tridiagonal systems.
"""
import numpy as np

def solve_block_tridiagonal(A, B, C, D):
    """
    Solves a block-tridiagonal system of linear equations.
    The system is of the form:
        B_0*x_0 + C_0*x_1 = D_0
        A_i*x_{i-1} + B_i*x_i + C_i*x_{i+1} = D_i  (for i=1..n-2)
        A_{n-1}*x_{n-2} + B_{n-1}*x_{n-1} = D_{n-1}

    where A, B, C are lists of coefficient matrices (blocks),
    and D is the right-hand side vector/matrix.
    For the St. Venant equations, each x_i is a vector [dQ_i, dZ_i]^T,
    and A, B, C are 2x2 matrices. D_i are 2x1 vectors.

    Args:
        A (list of np.ndarray): Lower diagonal blocks (size n-1).
        B (list of np.ndarray): Main diagonal blocks (size n).
        C (list of np.ndarray): Upper diagonal blocks (size n-1).
        D (list of np.ndarray): Right-hand side vectors (size n).

    Returns:
        np.ndarray: The solution vector x.
    """
    n = len(B)
    if n == 0:
        return []

    # Use np.linalg.solve for better stability and efficiency than np.linalg.inv

    # Forward sweep (elimination)
    C_prime = [np.zeros_like(C[0]) for _ in range(n - 1)]
    D_prime = [np.zeros_like(D[0]) for _ in range(n)]

    # First row
    C_prime[0] = np.linalg.solve(B[0], C[0])
    D_prime[0] = np.linalg.solve(B[0], D[0])

    # Middle rows (i=1 to n-2)
    for i in range(1, n - 1):
        M = B[i] - A[i-1] @ C_prime[i-1]
        C_prime[i] = np.linalg.solve(M, C[i])
        D_prime[i] = np.linalg.solve(M, D[i] - A[i-1] @ D_prime[i-1])

    # Last row
    M_last = B[n-1] - A[n-2] @ C_prime[n-2]
    D_prime[n-1] = np.linalg.solve(M_last, D[n-1] - A[n-2] @ D_prime[n-2])

    # Backward sweep (substitution)
    X = [np.zeros_like(D[0]) for _ in range(n)]
    X[n-1] = D_prime[n-1]

    for i in range(n - 2, -1, -1):
        X[i] = D_prime[i] - C_prime[i] @ X[i+1]

    return X
