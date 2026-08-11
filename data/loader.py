import polars as pl
import numpy as np
from core import PanelArray

def load_panel(
    symbols: list[str],
    lookback: int,
    period: str = "1d",
    as_of_date: int | None = None,
    root: str = "KIS_data",
) -> PanelArray:
    """parquet → PanelArray (T,N). 시그널 계산 입력 """
    lf = pl.scan_parquet(f"{root}/{period}/*.parquet")
    if as_of_date is not None: 
        lf = lf.filter(pl.col("date") <= as_of_date)
    lf = lf.filter(pl.col("symbol").is_in(symbols))
    df = lf.collect()
    df = (df.sort("date", descending=True).group_by("symbol", maintain_order=True)
          .head(lookback))

    def wide(field: str) -> np.ndarray:
        return (df.pivot(values=field, index="date", on="symbol"). sort("date", descending=True)).select(symbols).to_numpy()

    return PanelArray(
        dates = (df.get_column("date").unique().sort(descending=True).to_numpy()),
        symbols = tuple(symbols),
        open    = wide("open"),
        high    = wide("high"),
        low     = wide("low"),
        close   = wide("close"),
        volume  = wide("volume"),
    )
    

