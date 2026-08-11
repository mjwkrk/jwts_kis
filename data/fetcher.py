import polars as pl
import time
from datetime import datetime, timedelta
from pathlib import Path
from tqdm import tqdm

from exchange.kis import KISSession, REAL_KIS
from config import app_logger, error_logger

def _date_windows(start: int, end: int, span_days: int = 130):
    cur = datetime.strptime(str(start), "%Y%m%d")
    last = datetime.strptime(str(end), "%Y%m%d")
    while cur <=last:
        win_end = min(cur + timedelta(days=span_days-1), last)
        yield int(cur.strftime("%Y%m%d")), int(win_end.strftime("%Y%m%d"))
        cur = win_end + timedelta(days=1)

class DataFetcher:
    """KIS 일봉 → parquet 파일로 저장. JSON → polars DF로 변환"""

    def __init__(self, session: KISSession | None = None, root: str = "KIS_data"):
        self.session = session or KISSession(REAL_KIS, min_interval=0.2)
        self.root = Path(root)

    def _fetch_daily(self, symbol: str, start: int, end:int, retries: int = 2) -> pl.DataFrame:
        """한 종목 일봉. 일시적 오류는 재시도."""
        for attempt in range(retries + 1):
            try:
                raw = self.session.get(
                    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                    tr_id="FHKST03010100",
                    params={
                        "FID_COND_MRKT_DIV_CODE": "J",
                        "FID_INPUT_ISCD":         symbol,
                        "FID_INPUT_DATE_1":       str(start),
                        "FID_INPUT_DATE_2":       str(end),
                        "FID_PERIOD_DIV_CODE":    "D",
                        "FID_ORG_ADJ_PRC":        "0",
                    },
                )
                break                             
            except Exception as e:
                if attempt < retries:
                    time.sleep(2); continue; raise        
    
        rows = raw.get("output2") or [] # type: ignore        
        if not rows: return pl.DataFrame()
        return (
            pl.DataFrame(rows)
            .select(
                pl.col("stck_bsop_date").cast(pl.Int64).alias("date"),
                pl.lit(symbol).alias("symbol"),
                pl.col("stck_oprc").cast(pl.Float64).alias("open"),
                pl.col("stck_hgpr").cast(pl.Float64).alias("high"),
                pl.col("stck_lwpr").cast(pl.Float64).alias("low"),
                pl.col("stck_clpr").cast(pl.Float64).alias("close"),
                pl.col("acml_vol").cast(pl.Float64).alias("volume"),
                pl.col("acml_tr_pbmn").cast(pl.Float64).alias("value"),
            )
            .filter(pl.col("close").is_not_null())
        )
    
    def fetch_daily_range(self, symbols: list[str], start: int, end: int) -> None:
        """초기 bulk/backfill 용"""
        frames: list[pl.DataFrame] = []
        empty: list[str] = []; failed: list[str] = []

        for sym in tqdm(symbols, desc="일봉 수집", unit="종목"):
            try:
                parts = [self._fetch_daily(sym, w0, w1) for w0, w1 in _date_windows(start, end)]
                parts = [p for p in parts if len(p) > 0]
                if parts: frames.append(pl.concat(parts))
                else: empty.append(sym)
            except Exception as e:
                error_logger.warning(f"{sym} 일봉 수집 실패: {e}")
                failed.append(sym)

        if frames: self._save_daily(pl.concat(frames))
        app_logger.info(f"수집 완료: 성공 {len(frames)}, 데이터없음 {len(empty)}, 실패 {len(failed)}")
        if failed: app_logger.warning(f"실패 종목: {failed[:20]}{'...' if len(failed) > 20 else ''}")

    def _save_daily(self, df: pl.DataFrame) -> None:
        if df.is_empty(): return
        
        df = df.with_columns(year=pl.col("date") // 10000)
        for (year,), group in df.group_by(["year"]):
            path = self.root / "1d" / f"{year}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)

            group = group.drop("year")
            if path.exists(): 
                group = pl.concat([pl.read_parquet(path), group])

            (group
                .unique(subset=["date", "symbol"], keep="last")
                .sort(["date", "symbol"], descending=[True, False])
                .write_parquet(path))

    def _last_saved_date(self) -> int | None:
        files = sorted((self.root / "1d").glob("*.parquet"))
        if not files: return None
        latest = pl.read_parquet(files[-1])["date"].max()
        return int(latest) if latest is not None else None # type: ignore
    
    def update_daily(self, symbols: list[str], min_lookback: int = 10) -> None:
        """마지막 저장일 기준으로 필요한 만큼 재수집(최소 min_lookback일 겹침)."""
        today = datetime.now(); last = self._last_saved_date()        
        if last is None: app_logger.warning("저장된 데이터 없음 — bulk 먼저 필요") ; return
        last_dt = datetime.strptime(str(last), "%Y%m%d")
        gap_days = (today - last_dt).days
        lookback = max(min_lookback, gap_days + min_lookback)  
        start = int((today - timedelta(days=lookback)).strftime("%Y%m%d"))
        end   = int(today.strftime("%Y%m%d"))
        app_logger.info(f"일봉 업데이트: 마지막={last}, {lookback}일 재수집 ({start}~{end})")
        self.fetch_daily_range(symbols, start, end)
        