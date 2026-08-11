import numpy as np

def _average_rank(values: np.ndarray) -> np.ndarray:
    """values=[5.0, 3.0, 5.0] → [2.5, 1.0, 2.5]"""
    n = len(values)
    sorted_idx = values.argsort(kind="stable")
    sorted_vals = values[sorted_idx]

    is_bound = np.concatenate([[True], sorted_vals[1:] != sorted_vals[:-1], [True]])
    bounds   = np.flatnonzero(is_bound)
    counts   = np.diff(bounds)             
    starts   = bounds[:-1]                 

    avg_per_group = starts + (counts + 1) / 2.0
    sorted_ranks = np.repeat(avg_per_group, counts)

    ranks = np.empty(n, dtype=np.float64)
    ranks[sorted_idx] = sorted_ranks
    return ranks

# Time-Series helpers
# index 0 = 가장 최근
# 입력: (T,) np.ndarray 
# 출력: scalar

def ts_delay(values: np.ndarray, d: int = 1) -> float:
    """d일 전 값."""
    if len(values) <= d: return np.nan
    return float(values[d])

def ts_delta(values: np.ndarray, d: int = 1) -> float:
    """현재값 - d일 전 값."""
    if len(values) <= d: return np.nan
    return float(values[0] - values[d])

def ts_returns(values: np.ndarray, d: int = 1) -> float:
    """현재값 / d일 전 값 - 1."""
    if len(values) <= d or values[d] == 0: return np.nan
    return float(values[0] / values[d] - 1)

def ts_mean(values: np.ndarray, n: int = 20) -> float:
    if len(values) < n: return np.nan
    return float(np.mean(values[:n]))

def ts_std(values: np.ndarray, n: int = 20) -> float:
    if len(values) < n: return np.nan
    return float(np.std(values[:n]))

def ts_zscore(values: np.ndarray, n: int = 20) -> float:
    if len(values) < n: return np.nan
    w = values[:n]
    sd = w.std()
    if sd == 0: return np.nan
    return float((values[0] - w.mean()) / sd)

def ts_decay_linear(values: np.ndarray, n: int = 20) -> float:
    if len(values) < n: return np.nan
    w = np.arange(n, 0, -1, dtype=np.float64)
    return float((values[:n] * w).sum() / w.sum())

def ts_rank(values: np.ndarray, n: int = 20) -> float:
    if len(values) < n: return np.nan
    return float((values[:n] <= values[0]).sum() / n)

def ts_regression_slope(y: np.ndarray, x: np.ndarray, n: int = 20) -> float:
    if len(y) < n or len(x) < n: return np.nan
    yw, xw = y[:n], x[:n]
    xm, ym = xw.mean(), yw.mean()
    denom = ((xw - xm) ** 2).sum()
    if denom == 0: return np.nan
    return float(((xw - xm) * (yw - ym)).sum() / denom)

def ts_regression_intercept(y: np.ndarray, x: np.ndarray, n: int = 20) -> float:
    if len(y) < n or len(x) < n: return np.nan
    yw, xw = y[:n], x[:n]
    xm, ym = xw.mean(), yw.mean()
    denom = ((xw - xm) ** 2).sum()
    if denom == 0: return np.nan
    slope = ((xw - xm) * (yw - ym)).sum() / denom
    return float(ym - slope * xm)

# Cross-sectional normalizers
# 입력: (N,) np.ndarray 
# 출력: (N,) np.ndarray

def rank_normalize(values: np.ndarray) -> np.ndarray:
    """순위 기반 정규화, 합=1. 동점 평균 순위. NaN은 NaN."""
    out = np.full_like(values, np.nan, dtype=np.float64)
    mask = ~np.isnan(values)
    valid = values[mask]
    if len(valid) == 0: return out
    ranks = _average_rank(valid)
    out[mask] = ranks / ranks.sum()
    return out

def minmax_normalize(values: np.ndarray) -> np.ndarray:
    """0~1 스케일링 후 합=1."""
    out = np.full_like(values, np.nan, dtype=np.float64)
    mask = ~np.isnan(values)
    valid = values[mask]
    if len(valid) == 0: return out
    rng = valid.max() - valid.min()
    if rng == 0: out[mask] = 1.0 / len(valid); return out
    scaled = (valid - valid.min()) / rng
    s = scaled.sum()
    out[mask] = scaled / s if s > 0 else 1.0 / len(valid)
    return out

def zscore_long_short(values: np.ndarray) -> np.ndarray:
    """z-score → 절댓값합=1 (롱숏용)."""
    out = np.full_like(values, np.nan, dtype=np.float64)
    mask = ~np.isnan(values)
    valid = values[mask]
    if len(valid) == 0: return out
    sd = valid.std()
    if sd == 0: return out
    z = (valid - valid.mean()) / sd
    abs_sum = np.abs(z).sum()
    if abs_sum == 0: return out
    out[mask] = z / abs_sum
    return out

def rank_long_short(values: np.ndarray) -> np.ndarray:
    """rank 기반 롱숏. 동점 평균. 합=0, 절댓값합=1."""
    out = np.full_like(values, np.nan, dtype=np.float64)
    mask = ~np.isnan(values)
    valid = values[mask]
    if len(valid) == 0: return out
    ranks = _average_rank(valid)
    sig = ranks - ranks.mean()
    abs_sum = np.abs(sig).sum()
    if abs_sum == 0: return out
    out[mask] = sig / abs_sum
    return out

# Final Weight
# score -> 비중

def weight_sum1(scores: np.ndarray) -> np.ndarray:
    """음수 0 clip, 합=1."""
    out = np.full_like(scores, np.nan, dtype=np.float64)
    mask = ~np.isnan(scores)
    valid = scores[mask]
    if len(valid) == 0: return out
    clipped = np.maximum(valid, 0)
    s = clipped.sum()
    out[mask] = clipped / s if s > 0 else 1.0 / len(valid)
    return out

def weight_abs_sum1(scores: np.ndarray) -> np.ndarray:
    """그대로 사용. 절댓값합=1 (롱숏용)."""
    out = np.full_like(scores, np.nan, dtype=np.float64)
    mask = ~np.isnan(scores)
    valid = scores[mask]
    if len(valid) == 0: return out
    abs_sum = np.abs(valid).sum()
    if abs_sum == 0: return out
    out[mask] = valid / abs_sum
    return out
