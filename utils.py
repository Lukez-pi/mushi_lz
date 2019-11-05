#! /usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as onp
import jax.numpy as np
from typing import Callable


def C(n: int) -> onp.ndarray:
    """The C matrix defined in the text

    n: number of sampled haplotypes
    """
    W1 = onp.zeros((n - 1, n - 1))
    W2 = onp.zeros((n - 1, n - 1))
    b = onp.arange(1, n - 1 + 1)
    # j = 2
    W1[:, 0] = 6 / (n + 1)
    W2[:, 0] = 0
    # j = 3
    W1[:, 1] = 10 * (5 * n - 6 * b - 4) / (n + 2) / (n + 1)
    W2[:, 1] = (20 * (n - 2)) / (n+1) / (n+2)
    for col in range(n - 3):
        # this cast is crucial for floating point precision
        j = onp.float64(col + 2)
        # procedurally generated by Zeilberger's algorithm in Mathematica
        W1[:, col + 2] = -((-((-1 + j)*(1 + j)**2*(3 + 2*j)*(j - n)*(4 + 2*j - 2*b*j + j**2 - b*j**2 + 4*n + 2*j*n + j**2*n)*W1[:, col]) - (-1 + 2*j)*(3 + 2*j)*(-4*j - 12*b*j - 4*b**2*j - 6*j**2 - 12*b*j**2 - 2*b**2*j**2 - 4*j**3 + 4*b**2*j**3 - 2*j**4 + 2*b**2*j**4 + 4*n + 2*j*n - 6*b*j*n + j**2*n - 9*b*j**2*n - 2*j**3*n - 6*b*j**3*n - j**4*n - 3*b*j**4*n + 4*n**2 + 6*j*n**2 + 7*j**2*n**2 + 2*j**3*n**2 + j**4*n**2)*W1[:, col + 1])/(j**2*(2 + j)*(-1 + 2*j)*(1 + j + n)*(3 + b + j**2 - b*j**2 + 3*n + j**2*n)))
        W2[:, col + 2] = ((-1 + j)*(1 + j)*(2 + j)*(3 + 2*j)*(j - n)*(1 + j - n)*(1 + j + n)*W2[:, col] + (-1 + 2*j)*(3 + 2*j)*(1 + j - n)*(j + n)*(2 - j - 2*b*j - j**2 - 2*b*j**2 + 2*n + j*n + j**2*n)*W2[:, col + 1])/((-1 + j)*j*(2 + j)*(-1 + 2*j)*(j - n)*(j + n)*(1 + j + n))

    return W1 - W2


def M(n: int, t: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The M matrix defined in the text

    t: time grid, starting at zero and ending at np.inf
    y: population size in each epoch
    """
    # epoch durations
    s = np.diff(t)
    # we handle the final infinite epoch carefully to facilitate autograd
    u = np.exp(-s[:-1] / y[:-1])
    u = np.concatenate((np.array([1]), u, np.array([0])))

    binom_vec = np.arange(2, n + 1) * (np.arange(2, n + 1) - 1) / 2

    return np.exp(binom_vec[:, np.newaxis]
                  * np.cumsum(np.log(u[np.newaxis, :-1]), axis=1)
                  - np.log(binom_vec[:, np.newaxis])) \
        @ (np.eye(len(y), k=0) - np.eye(len(y), k=-1)) \
        @ np.diag(y)


def prf(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> np.float64:
    u"""Poisson random field log-likelihood of history

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    Ξ = L @ Z
    ℓ = (X * np.log(Ξ) - Ξ).sum()
    return ℓ


def d_kl(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> np.float64:
    u"""Kullback-Liebler divergence between normalized SFS and its
    expectation under history
    ignores constant term

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    X_normalized = X / X.sum(axis=0)
    Ξ = L @ Z
    Ξ_normalized = Ξ / Ξ.sum(axis=1, keepdims=True)
    d_kl = (-X_normalized * np.log(Ξ_normalized)).sum()
    return d_kl


def lsq(Z: np.ndarray, X: np.ndarray, L: np.ndarray) -> float:
    u"""least-squares loss between SFS and its expectation under history

    Z: mutation spectrum history matrix (μ.Z)
    X: k-SFS data
    L: model matrix
    """
    Ξ = L @ Z
    lsq = (1 / 2) * ((Ξ - X) ** 2).sum()
    return lsq


def acc_prox_grad_descent(x: np.ndarray,
                          g: Callable[[np.ndarray], np.float64],
                          grad_g: Callable[[np.ndarray], np.float64],
                          h: Callable[[np.ndarray], np.float64],
                          prox: Callable[[np.ndarray, np.float64], np.float64],
                          tol: np.float64 = 1e-10,
                          max_iter: int = 100,
                          s0: np.float64 = 1,
                          max_line_iter: int = 100,
                          γ: np.float64 = 0.8,
                          nonneg: bool = False) -> np.ndarray:
    u"""Nesterov accelerated proximal gradient descent

    x: initial point
    g: differential term in onjective function
    grad_g: gradient of g
    h: non-differentiable term in objective function
    prox: proximal operator corresponding to h
    tol: relative tolerance in objective function for convergence
    max_iter: maximum number of proximal gradient steps
    s0: initial step size
    max_line_iter: maximum number of line search steps
    γ: step size shrinkage rate for line search
    nonneg: if True, line search succeeds only for steps in positive orthant
    """
    if nonneg:
        assert np.all(x >= 0), 'initial x must be in positive orthant when ' \
                               'nonneg=True'
    # initialize step size
    s = s0
    # initialize momentum iterate
    q = x
    # initial objective value as first element of f_trajectory we'll append to
    f = g(x) + h(x)
    for k in range(1, max_iter + 1):
        print(f'iteration {k}, cost {f: .2g}', end='        \r')
        # evaluate differtiable part of objective at momentum point
        g1 = g(q)
        grad_g1 = grad_g(q)
        # store old iterate
        x_old = x
        # Armijo line search
        for line_iter in range(max_line_iter):
            if not np.all(np.isfinite(grad_g1)):
                raise RuntimeError(f'invalid gradient at step {k}, line '
                                   f'search step {line_iter}: {grad_g1}')
            # new point via prox-gradient of momentum point
            x = prox(q - s * grad_g1, s)
            if nonneg and np.any(x < 0):
                print('warning: line search left positive orthant')
            # G_s(q) as in the notes linked above
            G = (1 / s) * (q - x)
            # test g(q - sG_s(q)) for sufficient decrease
            if g(q - s * G) <= (g1 - s * (grad_g1 * G).sum()
                                + (s / 2) * (G ** 2).sum()):
                # Armijo satisfied
                break
            else:
                # Armijo not satisfied
                s *= γ  # shrink step size
        # update momentum term
        q = x + ((k - 1) / (k + 2)) * (x - x_old)
        if line_iter == max_line_iter - 1:
            print('warning: line search failed')
            s = s0
        if not np.all(np.isfinite(x)):
            print(f'warning: x contains invalid values')
        if nonneg and np.any(x < 0):
            print(f'warning: x contains negative values')
        # terminate if objective function is constant within tolerance
        f_old = f
        f = g(x) + h(x)
        rel_change = np.abs((f - f_old) / f_old)
        if rel_change < tol:
            print(f'relative change in objective function {rel_change:.2g} '
                  f'is within tolerance {tol} after {k} iterations')
            break
        if k == max_iter:
            print(f'maximum iteration {max_iter} reached with relative '
                  f'change in objective function {rel_change:.2g}')

    return x

def three_op_prox_grad_descent(x: np.ndarray,
                          g: Callable[[np.ndarray], np.float64],
                          grad_g: Callable[[np.ndarray], np.float64],
                          h: Callable[[np.ndarray], np.float64],
                          prox: Callable[[np.ndarray, np.float64], np.float64],
                          tol: np.float64 = 1e-10,
                          max_iter: int = 100,
                          s0: np.float64 = 1,
                          max_line_iter: int = 100,
                          γ: np.float64 = 0.8) -> np.ndarray:
    u"""Three operator splitting proximal gradient descent
    
    We implement the method of Pedregosa and Gidel (2018),
    which combines splitting and a backtracking line search.

    The optimization problem solved is:

      min_x f(x) s.t. x >= 0

    where f(x) = g(x) + h(x), g is differentiable, and prox_h is available.

    x: initial point
    g: differential term in onjective function
    grad_g: gradient of g
    h: non-differentiable term in objective function
    prox: proximal operator corresponding to h
    tol: relative tolerance in objective function for convergence
    max_iter: maximum number of proximal gradient steps
    s0: initial step size
    max_line_iter: maximum number of line search steps
    γ: step size shrinkage rate for line search
    """
    # initialize step size
    s = s0

    # line search tolerance
    ls_tol = 1e-10
    
    # initialize z, u variables by taking a step
    z = np.maximum(x, 0)
    g1 = g(z)
    grad_g1 = grad_g(z)
    x = prox(z - s * grad_g1, s)
    u = np.zeros_like(x)
    
    # initial objective value
    f = g(x) + h(x)
    for k in range(1, max_iter + 1):
        print(f'iteration {k}, cost {f: .2g}', end='        \r')
        # evaluate differtiable part of objective at momentum point
        g1 = g(z)
        grad_g1 = grad_g(z)
        # store old iterate
        x_old = x
        # Armijo line search
        for line_iter in range(max_line_iter):
            if not np.all(np.isfinite(grad_g1)):
                raise RuntimeError(f'invalid gradient at step {k}, line '
                                   f'search step {line_iter}: {grad_g1}')
            # new point via prox-gradient of momentum point
            x = prox(z - s * (u + grad_g1), s)
            incr = x - z
            norm_incr = np.linalg.norm(incr)
            # Qt
            Qt = g1 + (grad_g1 * incr).sum() + (norm_incr ** 2) / (2 * s)
            if g(x) - Qt <= ls_tol:
                # sufficient decrease satisfied
                break
            else:
                # sufficient decrease not satisfied
                s *= γ  # shrink step size
        if line_iter == max_line_iter - 1:
            print('warning: line search failed')
        
        # now take prox of nonnegative constraint
        z = np.maximum(x + s * u, 0)
        u = u + (x - z) / s
        certificate = norm_incr / s
        s /= γ  # grow step size a little bit
        
        if not np.all(np.isfinite(x)):
            print(f'warning: x contains invalid values')
        if np.any(x < 0):
            print(f'warning: x contains negative values')
        # terminate if objective function is constant within tolerance
        f_old = f
        f = g(x) + h(x)
        rel_change = np.abs((f - f_old) / f_old)
        if rel_change < tol:
            print(f'relative change in objective function {rel_change:.2g} '
                  f'is within tolerance {tol} after {k} iterations')
            break
        # if certificate < tol:
        #     print(f'certificate norm {certificate:.2g} '
        #           f'is within tolerance {tol} after {k} iterations')
        #     break
        if k == max_iter:
            print(f'maximum iteration {max_iter} reached with relative '
                  f'change in objective function {rel_change:.2g}')

    return x
