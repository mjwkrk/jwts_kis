import numpy as np
from dataclasses import dataclass, replace
from typing import Literal

@dataclass(frozen=True)
class BarArray:
    """한 종목 * 여러 날짜."""
    dates:  np.ndarray # dtype=int, #YYYYMMDD
    open:   np.ndarray # dtype=float
    high:   np.ndarray # dtype=float
    low:    np.ndarray # dtype=float
    close:  np.ndarray # dtype=float
    volume: np.ndarray # dtype=float

    def __len__(self) -> int:
        return len(self.close)
    
    def __getitem__(self, idx) -> "BarArray":
        return BarArray(
            dates=self.dates[idx],  open=self.open[idx],
            high=self.high[idx],    low=self.low[idx],
            close=self.close[idx],  volume=self.volume[idx],
        )

@dataclass(frozen=True)
class SymbolArray:
    """여러 종목 * 값 하나."""
    symbols:    tuple[str,...]
    values:     np.ndarray

    def __post_init__(self):
        if len(self.symbols) != len(self.values): 
            raise ValueError(f"symbols, values 길이 불일치")

    def __len__(self) -> int:
        return len(self.symbols)

    def __iter__(self):
        return zip(self.symbols, self.values)
    
    def __getitem__(self, key):
        if isinstance(key, str):
            try: return float(self.values[self.symbols.index(key)])
            except ValueError: raise KeyError(key)
        return self.values[key]
    
    def get(self, symbol: str, default: float = np.nan) -> float:
        try: return float(self.values[self.symbols.index(symbol)])
        except ValueError: return default

    def to_dict(self, drop_nan: bool = True) -> dict[str, float]:
        """{symbol: value}."""
        return {
            symbol: float(value)
            for symbol, value in zip(self.symbols, self.values)
            if not drop_nan or not np.isnan(value)
        }

    def top_n(self, n: int) -> "SymbolArray":
        out = np.zeros_like(self.values, dtype=np.float64)
        valid_idx = np.flatnonzero(~np.isnan(self.values))
        top_idx = valid_idx[np.argsort(self.values[valid_idx])[-n:]]
        out[top_idx] = self.values[top_idx]
        return SymbolArray(self.symbols, out)
    
    def bottom_n(self, n: int) -> "SymbolArray":
        out = np.zeros_like(self.values, dtype=np.float64)
        valid_idx = np.flatnonzero(~np.isnan(self.values))
        top_idx = valid_idx[np.argsort(self.values[valid_idx])[:n]]
        out[top_idx] = self.values[top_idx]
        return SymbolArray(self.symbols, out)

    def non_zero(self) -> "SymbolArray":
        mask = self.values != 0
        return SymbolArray(
            symbols=tuple(s for s, m in zip(self.symbols, mask) if m),
            values=self.values[mask],
        )
    
    def drop_nan(self) -> "SymbolArray":
        mask = ~np.isnan(self.values)
        return SymbolArray(
            symbols = tuple(s for s, m in zip(self.symbols, mask) if m),
            values  = self.values[mask],
        )

    def sorted(self, descending: bool = True) -> "SymbolArray":
        clean = self.drop_nan()
        idx = np.argsort(clean.values)
        if descending: idx = idx[::-1]
        return SymbolArray(
            symbols = tuple(clean.symbols[i] for i in idx),
            values  = clean.values[idx],
        )
    
    def long_normalize(self) -> "SymbolArray":
        clipped = np.maximum(self.values, 0)
        total = np.nansum(clipped)
        if total == 0: return self
        return SymbolArray(symbols=self.symbols, values=clipped / total)
    
    def longshort_normalize(self) -> "SymbolArray":
        demeaned = self.values - np.nanmean(self.values)
        return SymbolArray(symbols=self.symbols, values=demeaned / np.nansum(np.abs(demeaned)),)
    
@dataclass(frozen=True)
class PanelArray:
    """여러 종목 * 여러 날짜."""
    dates:   np.ndarray              # (T,) int64
    symbols: tuple[str, ...]         # (N,)
    open:    np.ndarray              # (T, N) float64
    high:    np.ndarray              # (T, N) float64
    low:     np.ndarray              # (T, N) float64
    close:   np.ndarray              # (T, N) float64
    volume:  np.ndarray              # (T, N) float64

    def __len__(self) -> int:
        return len(self.dates)
    
    @property
    def T(self) -> int: return self.close.shape[0]
    @property
    def N(self) -> int: return self.close.shape[1]

    def column(self, symbol: str) -> "BarArray":
        idx = self.symbols.index(symbol)
        return BarArray(
            dates  = self.dates,
            open   = self.open[:, idx],
            high   = self.high[:, idx],
            low    = self.low[:, idx],
            close  = self.close[:, idx],
            volume = self.volume[:, idx],
        )
    
    def slice_dates(self, start: int, end: int) -> "PanelArray":
        return PanelArray(
            dates  = self.dates[start:end],
            symbols= self.symbols,
            open   = self.open[start:end],
            high   = self.high[start:end],
            low    = self.low[start:end],
            close  = self.close[start:end],
            volume = self.volume[start:end],
        )

@dataclass(frozen=True)
class Snapshot:
    """한 종목 * 현재 시점 여러 필드"""
    symbol:           str
    price:          float
    volume:         float
    high_52w:       float
    foreign_ratio:  float
    per:            float
    pbr:            float
    # iscd_stat_cls_code: int

@dataclass(frozen=True)
class SnapshotPanel:
    """여러 종목 * 현재 시점 여러 필드"""
    symbols:        tuple[str, ...]   # (N,)
    price:          np.ndarray         # (N,) float64
    volume:         np.ndarray         # (N,)
    high_52w:       np.ndarray         # (N,)
    foreign_ratio:  np.ndarray         # (N,)
    per:            np.ndarray         # (N,)
    pbr:            np.ndarray         # (N,)

    @property
    def N(self) -> int: return len(self.symbols)

    @classmethod
    def from_dict(cls, snapshots: dict[str, Snapshot]) -> "SnapshotPanel":
        syms = tuple(snapshots.keys())
        ss = list(snapshots.values())           
        return cls(
            symbols       = syms,
            price         = np.array([s.price         for s in ss], dtype=np.float64),
            volume        = np.array([s.volume        for s in ss], dtype=np.float64),
            high_52w      = np.array([s.high_52w      for s in ss], dtype=np.float64),
            foreign_ratio = np.array([s.foreign_ratio for s in ss], dtype=np.float64),
            per           = np.array([s.per           for s in ss], dtype=np.float64),
            pbr           = np.array([s.pbr           for s in ss], dtype=np.float64),
        )


@dataclass(frozen=True)
class Holding:
    symbol:       str
    name:       str
    qty:        float
    avg_price:  float   
    cur_price:  float

    @property
    def market_value(self) -> float:
        return self.qty * self.cur_price

    @property
    def pnl_rate(self) -> float:
        if self.avg_price == 0: return 0.0
        return (self.cur_price / self.avg_price) - 1
    
    @property
    def buy_amount(self) -> float:
        return self.qty * self.avg_price
    
    @property
    def pnl_amount(self) -> float:
        return self.market_value - self.buy_amount
    
@dataclass(frozen=True)
class AccountSummary:
    holdings        :dict[str, Holding]
    holdings_value  :float
    total_value     :float

@dataclass(frozen=True)
class Order:
    symbol:   str
    side:   Literal["buy", "sell"]
    qty:    float
    price:  float # 0 = market price

    def __post_init__(self):
        if self.qty <= 0:   raise ValueError(f"qty must be positive, got {self.qty}")
        if self.price < 0:  raise ValueError(f"price must be positive, got {self.price}")
        if self.side not in ("buy", "sell"): raise ValueError(f"side must be buy/sell, got {self.side}") 

    @property
    def amount(self) -> float:
        return self.qty * self.price
    
    @property
    def is_market(self) -> bool:
        return self.price == 0
    

@dataclass(frozen=True)
class OrderResult:
    symbol:       str
    success:    bool
    order_id:   str | None
    message:    str
    raw:        dict
    
