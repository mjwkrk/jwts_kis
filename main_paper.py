import time
import numpy as np
import polars as pl
from datetime import datetime

from core import SnapshotPanel, SymbolArray
from exchange.kis import KISExchange
from strategy.portfolio import Portfolio, compute_orders
from data.loader import load_panel           
from config import app_logger

WEIGHTS = {"momentum":0.5, "ma_divergence":0.3, "volume_ratio": 0.2}

def main(dry_run: bool = True):
    app_logger.info(f"========== {time.strftime('%Y-%m-%d %H:%M')} 리밸런싱 시작 ==========")
    ex = KISExchange(paper_trading=True)

    # 1. universe (로컬 거래대금 상위) + 과거(로컬) + 현재가(라이브)
    today = int(datetime.now().strftime("%Y%m%d"))
    bars = pl.scan_parquet("KIS_data/1d/*.parquet").filter(pl.col("date") <= today).collect()
    cutoff = bars["date"].unique().sort(descending=True).head(90).min()
    universe = (
        bars.filter(pl.col("date") >= cutoff)
            .group_by("symbol")
            .agg(pl.col("value").median().alias("med"))
            .sort("med", descending=True)
            .head(30)["symbol"].to_list()
    )

    panel = load_panel(universe, lookback=30)              
    snaps = {s: ex.market_snapshot(s) for s in universe}   
    now = SnapshotPanel.from_dict(snaps)
    
    # 2. Signal
    portfolio = Portfolio.from_dict(WEIGHTS)
    scores = portfolio.score(panel, now)
    target_weights = scores.top_n(3).long_normalize()
    app_logger.info(f"선택: {target_weights.non_zero().to_dict()}")

    # 3. Order Caclulate
    account = ex.account_summary()
    current_prices = SymbolArray(now.symbols, now.price)
    sells, buys = compute_orders(target_weights, account, current_prices, qty_step=1.0)
    for o in sells: app_logger.info(f"  [SELL] {o.symbol} x{o.qty:.0f}")
    for o in buys: app_logger.info(f"  [BUY ] {o.symbol} x{o.qty:.0f}")

    # 4. Execute
    if dry_run: app_logger.info("dry_run - 주문 전송 안 함")
    else:
        results = ex.execute(sells, buys, wait_after_sell=2.0)
        for r in results: app_logger.info(f"{r.symbol}: {'OK' if r.success else r.message}")
    app_logger.info("========== 종료 ==========")

if __name__ == "__main__":
    main(dry_run=True)