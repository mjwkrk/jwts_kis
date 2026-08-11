import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FORMATTER = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)-5s | %(filename)-15s:%(lineno)d | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def make_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # 중복 핸들러 방지
        return logger

    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    fh.setFormatter(_FORMATTER)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(_FORMATTER)
    logger.addHandler(ch)

    return logger

app_logger   = make_logger("app",   "app.log")
error_logger = make_logger("error", "error.log")
order_logger = make_logger("order", "order.log")
