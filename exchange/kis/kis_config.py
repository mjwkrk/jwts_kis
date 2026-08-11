import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

TOKEN_DIR = Path(__file__).resolve().parents[2] / ".tokens"
TOKEN_DIR.mkdir(exist_ok=True)

@dataclass(frozen=True)
class KISConfig:
    base_url:   str | None
    cano:       str | None
    appkey:     str | None
    appsecret:  str | None
    token_file: Path


REAL_KIS = KISConfig(
    base_url    = "https://openapi.koreainvestment.com:9443",
    cano        = os.getenv("KIS_CANO"),
    appkey      = os.getenv("KIS_APP_KEY"),
    appsecret   = os.getenv("KIS_APP_SECRET"),
    token_file  = TOKEN_DIR / "access_token.json",
)

PAPER_KIS = KISConfig(
    base_url    = "https://openapivts.koreainvestment.com:29443",
    cano        = os.getenv("KIS_PAPER_CANO"),
    appkey      = os.getenv("KIS_PAPER_APP_KEY"),
    appsecret   = os.getenv("KIS_PAPER_APP_SECRET"),
    token_file  = TOKEN_DIR / "paper_access_token.json",
)