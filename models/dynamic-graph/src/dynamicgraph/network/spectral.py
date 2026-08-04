r"""Spectral summaries of a graph.

Spectral radius, algebraic connectivity and Laplacian entropy are computed on
the **absolute-weight** adjacency, since the sign of a partial correlation makes
the spectrum hard to interpret (and several quantities undefined).
"""

from __future__ import annotations

import numpy as np

from dynamicgraph.constants import EPS


def spectral_radius(adjacency: np.ndarray) -> float:
    r"""SR_t = lambda_max(A_t) on the absolute-weight graph."""
    weights = np.abs(adjacency)
    if weights.shape[0] < 2:
        return float("nan")
    return float(np.max(np.abs(np.linalg.eigvalsh(0.5 * (weights + weights.T)))))


def laplacian(adjacency: np.ndarray, normalized: bool = False) -> np.ndarray:
    weights = np.abs(adjacency)
    degrees = weights.sum(axis=1)
    L = np.diag(degrees) - weights
    if not normalized:
        return L
    inv_sqrt = np.diag(1.0 / np.sqrt(np.clip(degrees, EPS, None)))
    return inv_sqrt @ L @ inv_sqrt


def algebraic_connectivity(adjacency: np.ndarray) -> float:
    """Second-smallest Laplacian eigenvalue (Fiedler value).

    0 when the graph is disconnected; larger values mean a graph that is harder
    to split, i.e. a more tightly bound market.
    """
    if adjacency.shape[0] < 3:
        return float("nan")
    eigenvalues = np.linalg.eigvalsh(laplacian(adjacency))
    eigenvalues = np.sort(eigenvalues)
    return float(eigenvalues[1])


def laplacian_entropy(adjacency: np.ndarray) -> float:
    r"""Shannon entropy of the normalised Laplacian spectrum.

        H = -sum_i p_i log p_i,  p_i = lambda_i / sum lambda

    High entropy = spectral mass spread evenly = no dominant structure.
    """
    if adjacency.shape[0] < 2:
        return float("nan")
    eigenvalues = np.clip(np.linalg.eigvalsh(laplacian(adjacency)), 0.0, None)
    total = eigenvalues.sum()
    if total <= EPS:
        return float("nan")
    p = eigenvalues / total
    p = p[p > EPS]
    return float(-(p * np.log(p)).sum())


def spectral_gap(adjacency: np.ndarray) -> float:
    """lambda_1 - lambda_2 of the absolute adjacency."""
    weights = np.abs(adjacency)
    if weights.shape[0] < 3:
        return float("nan")
    eigenvalues = np.sort(np.linalg.eigvalsh(0.5 * (weights + weights.T)))[::-1]
    return float(eigenvalues[0] - eigenvalues[1])


def eigenvalue_concentration(adjacency: np.ndarray) -> float:
    """Herfindahl index of the (absolute) eigenvalue spectrum."""
    weights = np.abs(adjacency)
    if weights.shape[0] < 2:
        return float("nan")
    eigenvalues = np.abs(np.linalg.eigvalsh(0.5 * (weights + weights.T)))
    total = eigenvalues.sum()
    if total <= EPS:
        return float("nan")
    shares = eigenvalues / total
    return float(np.sum(shares**2))


def leading_eigenvector(adjacency: np.ndarray) -> np.ndarray:
    """Principal eigenvector of the absolute adjacency, sign-normalised."""
    weights = np.abs(adjacency)
    values, vectors = np.linalg.eigh(0.5 * (weights + weights.T))
    vector = vectors[:, -1]
    if vector.sum() < 0:
        vector = -vector
    return vector
