"""Dense linear solvers (stdlib only): Gaussian elimination with partial pivoting and conjugate gradient."""
from typing import List, Sequence


def gaussian_solve(A: Sequence[Sequence[float]], b: Sequence[float]) -> List[float]:
    n = len(A)
    M = [list(map(float, A[i])) + [float(b[i])] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            raise ValueError("singular or ill-conditioned matrix")
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            if f:
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))
        x[i] = s / M[i][i]
    return x


def conjugate_gradient(A: Sequence[Sequence[float]], b: Sequence[float], tol: float = 1e-10, max_iter: int = 1000) -> List[float]:
    """For symmetric positive definite A."""
    n = len(A)
    x = [0.0] * n
    r = [float(b[i]) for i in range(n)]
    p = list(r)
    rs = sum(v * v for v in r)
    for _ in range(max_iter):
        if rs ** 0.5 < tol:
            break
        Ap = [sum(A[i][j] * p[j] for j in range(n)) for i in range(n)]
        denom = sum(p[i] * Ap[i] for i in range(n))
        if abs(denom) < 1e-300:
            break
        alpha = rs / denom
        x = [x[i] + alpha * p[i] for i in range(n)]
        r = [r[i] - alpha * Ap[i] for i in range(n)]
        rs_new = sum(v * v for v in r)
        p = [r[i] + (rs_new / rs) * p[i] for i in range(n)]
        rs = rs_new
    return x
