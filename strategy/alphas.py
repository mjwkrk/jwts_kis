import numpy as np
from core import *
from typing import Callable
from strategy.operators import rank_normalize
from config import app_logger

def inverse(value: float) -> float:
    if value <= 0: return np.nan
    return 1.0 / value

# Time-Series factors
def momentum(panel: PanelArray, n: int = 30) -> np.ndarray:
    if panel.T < n : return np.full(panel.N, np.nan)
    return panel.close[0] / panel.close[n-1] -1

def ma_divergence(panel: PanelArray, n: int = 20) -> np.ndarray:
    if panel.T < n : return np.full(panel.N, np.nan)
    ma = panel.close[:n].mean(axis=0)
    return np.divide(panel.close[0], ma, out=np.full(panel.N, np.nan), where=ma != 0) -1

def volume_ratio(panel: PanelArray, n:int = 20) -> np.ndarray:
    if panel.T < n+1 : return np.full(panel.N, np.nan)
    avg = panel.volume[1:n+1].mean(axis=0)
    return np.divide(panel.volume[0], avg, out=np.full(panel.N, np.nan), where=avg != 0)

# Point-in-time factors
def high_proximity(snap: SnapshotPanel) -> np.ndarray:
    return np.divide(snap.price, snap.high_52w,
                     out=np.full(snap.N, np.nan), where=snap.high_52w != 0)
def value_per(snap: SnapshotPanel) -> np.ndarray:
    return np.divide(1.0, snap.per, 
                    out=np.full(snap.N, np.nan), where=snap.per > 0)


# Factor Registry

FACTOR_REGISTRY = {
    "momentum":         lambda panel, snap: momentum(panel, n=14),
    "volume_ratio":     lambda panel, snap: volume_ratio(panel, n=14),
    "ma_divergence":    lambda panel, snap: ma_divergence(panel, n=14),
    "high_proximity":   lambda panel, snap: high_proximity(snap),
    "value_per":        lambda panel, snap: value_per(snap),
}



