"""Study-local numerical reconstruction of the 2x2 stick-residual Jacobian."""

from __future__ import annotations

import numpy as np


def finite_difference_jacobian(
    lambda_p: np.ndarray,
    lambda_s: np.ndarray,
    residual_p: np.ndarray,
    residual_s: np.ndarray,
):
    lp = np.asarray(lambda_p, dtype=float)
    ls = np.asarray(lambda_s, dtype=float)
    rp = np.asarray(residual_p, dtype=float)
    rs = np.asarray(residual_s, dtype=float)
    if rp.shape != rs.shape or rp.shape != (ls.size, lp.size):
        raise ValueError("Residual arrays must be shaped (len(lambda_s), len(lambda_p)).")

    shape = rp.shape
    sigma_min = np.full(shape, np.nan)
    sigma_max = np.full(shape, np.nan)
    kappa = np.full(shape, np.nan)
    determinant = np.full(shape, np.nan)

    for i in range(1, ls.size - 1):
        dls = ls[i + 1] - ls[i - 1]
        for j in range(1, lp.size - 1):
            dlp = lp[j + 1] - lp[j - 1]
            stencil = (
                rp[i, j-1], rp[i, j+1], rp[i-1, j], rp[i+1, j],
                rs[i, j-1], rs[i, j+1], rs[i-1, j], rs[i+1, j],
            )
            if not all(np.isfinite(v) for v in stencil):
                continue
            J = np.array(
                [
                    [
                        (rp[i, j+1] - rp[i, j-1]) / dlp,
                        (rp[i+1, j] - rp[i-1, j]) / dls,
                    ],
                    [
                        (rs[i, j+1] - rs[i, j-1]) / dlp,
                        (rs[i+1, j] - rs[i-1, j]) / dls,
                    ],
                ],
                dtype=float,
            )
            singular = np.linalg.svd(J, compute_uv=False)
            sigma_max[i, j] = singular[0]
            sigma_min[i, j] = singular[-1]
            kappa[i, j] = (
                singular[0] / singular[-1]
                if singular[-1] > 0.0
                else float("inf")
            )
            determinant[i, j] = np.linalg.det(J)
    return sigma_min, sigma_max, kappa, determinant
