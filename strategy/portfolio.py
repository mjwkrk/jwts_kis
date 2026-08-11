import numpy as np
from typing import Callable
from core import PanelArray, SnapshotPanel, SymbolArray, AccountSummary, Order
from strategy.operators import rank_normalize, weight_sum1
from strategy.alphas import FACTOR_REGISTRY
from config import app_logger

class Portfolio:
    """가중 팩터 조합 → 종목별 종합점수 (SymbolArray).
      1. 각 행 = 한 팩터의 전 종목 값          -> raw.shape == (F, N) 
      2. 팩터별 cross-section 정규화         -> normed.shape == (F, N)    
      3. weights · normed → (N,) score    -> score.shape == (F,)@(F,N) = (N,)
      4. final_weight_fn 적용    
    """
    def __init__(
        self,
        weights: np.ndarray | list[float] | tuple[float, ...],
        factor_names: tuple[str, ...] | list[str],
        factor_map: dict[str, Callable] | None = None,
        norm_fn: Callable = rank_normalize,
        final_weight_fn: Callable = weight_sum1,
    ):
        self.weights = np.asarray(weights, dtype=np.float64)
        self.factor_map = factor_map or FACTOR_REGISTRY
        self.factor_names = tuple(factor_names)
        self.norm_fn = norm_fn
        self.final_weight_fn = final_weight_fn
        if len(self.factor_names) != len(self.weights): raise ValueError("factor_names와 weight 길이가 다름")
        if set(self.factor_names) - set(self.factor_map): raise ValueError("factor_map에 없는 factor 존재")
        self.factor_funcs: tuple[Callable, ...] = tuple(self.factor_map[name] for name in self.factor_names)

    @classmethod
    def from_dict(cls, weights: dict[str, float], **kwargs) -> "Portfolio":
        """dict로 간편 생성."""
        return cls(
            factor_names = tuple(weights.keys()),
            weights      = np.fromiter(weights.values(), dtype=np.float64),
            **kwargs,
        )
    
    def score(self, panel: PanelArray, snap: SnapshotPanel) -> SymbolArray:
        """팩터 -> 점수."""
        if panel.symbols != snap.symbols: raise ValueError("panel과 snapshot의 symbols 다름")

        raw = np.array([func(panel,snap) for func in self.factor_funcs], dtype=np.float64)
        normed = np.array([self.norm_fn(row) for row in raw], dtype=np.float64)             
        scores = self.weights @ normed

        if self.final_weight_fn is not None: scores = self.final_weight_fn(scores)
        return SymbolArray(panel.symbols, values=scores)
    
    def to_value(self, weights: SymbolArray, total_value: float) -> SymbolArray:
        """비중 -> 금액"""
        return SymbolArray(weights.symbols, weights.values * total_value)
    
    def to_qty(
        self,
        target_value:   SymbolArray,
        current_value:  SymbolArray,
        prices:         SymbolArray,
        qty_step:       float = 1.0,
    ) -> SymbolArray:
        """delta_value -> signed qty"""

        delta   = target_value.values - current_value.values
        qty     = np.floor(np.abs(delta) / prices.values / qty_step) * qty_step
        return SymbolArray(target_value.symbols, qty * np.sign(delta)) 

def compute_orders(
    weights:        SymbolArray,
    account:        AccountSummary,
    current_prices: SymbolArray,
    qty_step:       float = 1.0,
) -> tuple[list[Order], list[Order]]:
    """ [행렬 도메인]  PanelArray → score() → SymbolArray(점수) → top_n → SymbolArray(비중)
                                        ↓
                                ★ compute_orders ★
                                        ↓
        [객체 도메인]  list[Order] → KISExchange.execute() → list[OrderResult].

    - Universe 안: delta value → floor qty → Order
    - Universe 밖: 전량 매도    
    """
    if weights.symbols != current_prices.symbols:
        raise ValueError("weights와 prices의 symbols 다름")
    universe = weights.symbols

    # 행렬 파트: 전부 size (N,) 1차원 ndarray
    target_value = weights.values * account.total_value
    current_value = np.array([
        account.holdings[s].market_value if s in account.holdings else 0.0
        for s in universe
    ], dtype=np.float64)
    delta_value = target_value - current_value
    abs_qty = np.floor(np.abs(delta_value) / current_prices.values / qty_step) * qty_step

    # 객체 파트: 1건씩
    sells, buys = [],[]
    for sym, dv, qty in zip(universe, delta_value, abs_qty):
        if not np.isfinite(qty) or qty < qty_step: continue
        if dv > 0:
            buys.append(Order(sym, "buy", float(qty), 0.0))
        else:
            qty = min(qty, account.holdings[sym].qty)
            if qty < qty_step: continue
            sells.append(Order(sym, "sell", float(qty), 0.0))

    universe_set = set(universe)
    for sym, h in account.holdings.items():
        if sym in universe_set: continue
        if h.qty >= qty_step:
            sells.append(Order(sym, "sell", float(h.qty), 0.0))
    
    return sells, buys