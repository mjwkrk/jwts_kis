import polars as pl
from pathlib import Path

from config import app_logger
from datetime import datetime

def build_meta(root = "KIS_data") -> pl.DataFrame:
    """KOSPI + KOSDAQ 마스터 → meta.parquet 저장 후 반환."""
    root = Path(root)
    ks = _parse_mst(root / "master" / "kospi_code.mst",  "KOSPI")
    kq = _parse_mst(root / "master" / "kosdaq_code.mst", "KOSDAQ")
    meta = pl.concat([ks, kq]).unique(subset=["symbol"], keep="last").sort("symbol")
    meta.write_parquet(root / "meta.parquet")

    today = datetime.now().strftime("%Y-%m-%d")
    app_logger.info(f"meta 저장 [{today}]: {len(meta)}종목 (KOSPI {len(ks)}, KOSDAQ {len(kq)})")
    return meta

def _parse_mst(path: Path, market: str) -> pl.DataFrame:
    """KIS 마스터 앞부분만 파싱 (뒤쪽 숫자 필드 무시).
    0-9 단축코드 | 9-21 표준코드 | 21-61 이름(40, 공백패딩) | 61-63 증권그룹."""
    rows = []
    with open(path, "rb") as f:
        for raw in f:
            raw = raw.rstrip(b"\r\n")
            symbol    = raw[0:9].decode("euc-kr").strip()
            name      = raw[21:61].decode("euc-kr", errors="replace").strip()
            sec_group = raw[61:63].decode("euc-kr").strip()
            rows.append((symbol, name, market, sec_group))

    return pl.DataFrame(rows, schema=["symbol", "name", "market", "sec_group"], orient="row")

def load_symbols(
    root: str = "KIS_data",
    markets: tuple[str, ...] | None = None,
    sec_groups: tuple[str, ...] | None = None,
) -> list[str]:

    meta = pl.read_parquet(Path(root) / "meta.parquet")
    if markets is not None:
        meta = meta.filter(pl.col("market").is_in(markets))
    if sec_groups is not None:
        meta = meta.filter(pl.col("sec_group").is_in(sec_groups))
    return meta["symbol"].to_list()