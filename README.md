# JWTS v5 — KIS API 국내주식 자동매매 (모의투자)

한국투자증권 Open API 기반 팩터 퀀트 자동매매 시스템. **모의투자 계좌 검증용**이다.
자동완성을 끄고 전부 손으로 작성하며 퀀트 시스템의 로직을 체득하는 것이 목표였다.

약 1,500줄. 실제로 모의계좌에서 5종목 매매·체결까지 돌렸다.

---

## ⚠️ 계정 구성 — 시세와 주문을 다른 계정으로 쓴다

이 시스템은 **KIS 실전 계정과 모의투자 계정을 동시에** 사용한다.

| 용도 | 계정 | 이유 |
|---|---|---|
| **시세·차트·순위 조회** | **실전** (`REAL_KIS`) | 모의투자 서버는 시세 조회 API 지원이 제한적이고 데이터가 실제와 다르다 |
| **주문 집행·잔고 조회** | **모의투자** (`PAPER_KIS`) | 실제 자금이 나가지 않는다 |

```python
# exchange/kis/kis_exchange.py
class KISExchange(Exchange):
    def __init__(self, paper_trading: bool = True):
        self._market = KISSession(REAL_KIS,  min_interval=0.0)   # 시세 = 실전
        if paper_trading:
            self._trade = KISSession(PAPER_KIS, min_interval=1)  # 주문 = 모의
        else:
            self._trade = self._market
```

데이터 수집(`data/fetcher.py`)도 실전 세션을 쓴다 — 5.5년치 전종목 일봉을 받으려면
실제 시세 API가 필요하기 때문이다.

**따라서 `.env`에 두 계정의 키가 모두 필요하다.** 다만 실전 키는 조회에만 쓰이고
주문 경로(`_trade`)로는 절대 흐르지 않는다. `paper_trading=False`로 바꾸지 않는 한
실제 주문은 발생하지 않는다.

---

## 구조

```
core/types.py          표준 컨테이너 — BarArray / SymbolArray / PanelArray / Order / Holding
exchange/
  base.py              Exchange ABC — 거래소 무관 인터페이스
  kis/                 KIS 격리 — 세션(토큰 캐시·throttle), 응답 파싱, 구현체
strategy/
  operators.py         시계열·크로스섹션 연산자 (ts_*, rank_normalize, weight_*)
  alphas.py            팩터 정의 + FACTOR_REGISTRY
  portfolio.py         가중 팩터 조합 → 목표비중 → compute_orders
data/
  fetcher.py           KIS 일봉 → polars → parquet (append+dedupe 멱등)
  master.py            거래소 마스터파일(.mst) 고정폭 파싱 → meta.parquet
  loader.py            load_panel(symbols, lookback, as_of_date) → PanelArray
main_paper.py          오케스트라 — universe → 시그널 → 주문 → 집행
```

### 실행 흐름

```
로컬 parquet (과거)  ─┐
                      ├→ PanelArray (T,N) ─→ 팩터 (F,N) ─→ 가중합 → 점수 (N,)
라이브 API (현재가)  ─┘                                              │
                                                          top_n → 목표비중
                                                                     │
                          compute_orders  ← 행렬 도메인에서 객체 도메인으로 전환하는 유일한 지점
                                                                     │
                                                      list[Order] → KIS 주문 전송
```

## 설계 포인트

**행렬 도메인과 객체 도메인의 분리.** 시그널 계산은 익명 숫자 배열 `(T,N)`로,
주문은 이름 붙은 개별 객체로 다룬다. 전환은 `compute_orders`의 `zip` 순회 **한 지점**에서만
일어난다. 이 경계를 흐리면 벡터화 이점과 추적 가능성을 둘 다 잃는다.

**lookahead 방지.** `load_panel(..., as_of_date=...)`로 과거 특정 시점을 재현할 수 있다.
백테스트의 정직성은 "그 시점에 알 수 없던 데이터를 안 쓰는 것"에서 나온다.

**NaN 규약.** 결측은 0이 아니라 NaN. NaN-safe 정규화가 랭킹에서 결측 종목을 자동 제외한다.

**멱등 저장.** `append + unique(keep="last")`로 재실행해도 결과가 같다. cron 자동화의 전제.

**에러 분류.** 진짜 실패는 `raise`로 명확히, 예상 가능한 빈 결과는 분류, 일시적 오류
(rate limit)는 재시도로 흡수. "정상 응답(`rt_cd=0`) ≠ 데이터 있음"이 반복해서 문제였다.

## 데이터

`KIS_data/`는 **저장소에 포함되지 않는다** (99MB, 재수집 가능).

| 파일 | 내용 |
|---|---|
| `KIS_data/1d/{year}.parquet` | 일봉. 5.5년 × 전종목 4,389개 = **525만 행** |
| `KIS_data/meta.parquet` | 종목 마스터 (symbol, name, market, sec_group) |
| `KIS_data/master/*.mst` | KIS 배포 마스터파일 (고정폭, EUC-KR) |

재생성:

```python
from data.master import build_meta, load_symbols
from data.fetcher import DataFetcher

build_meta()                                   # .mst → meta.parquet
DataFetcher().fetch_daily_range(load_symbols(), 20200101, 20260101)
```

## 실행

```bash
pip install -r notes/requirements.txt      # requests, python-dotenv (+ polars, numpy, tqdm)
cp .env.example .env                       # 두 계정 키 입력
python main_paper.py                       # 기본 dry_run=True (주문 전송 안 함)
```

`main_paper.py`의 `main(dry_run=False)`로 바꿔야 실제(모의계좌) 주문이 나간다.

## 알려진 한계

이 코드는 학습 단계의 산출물이고, 후속 버전(v6) 설계 전에 스스로 검수해 아래를 확인했다.

**버그**
- `data/fetcher.py` 재시도 로직에 `continue; raise` — `raise`가 도달 불가 코드다.
  최종 실패 시 예외가 조용히 삼켜지고 다음 줄에서 `NameError`로 터진다
- `fetch_daily_range`가 전 종목을 메모리에 모은 뒤 한 번에 저장 — 중간에 죽으면 전부 유실
- `_save_daily`가 저장할 때마다 연도 파일 전체를 재작성

**설계 결함**
- 스냅샷 기반 팩터(`high_proximity`, `value_per`)는 라이브 API에서만 계산돼
  히스토리가 없다 → **백테스트가 원천 불가능**
- `core/types.py`에 KIS 도메인 누수 (`per`, `pbr`, `foreign_ratio`)
- 롱온리 전제가 `compute_orders`·`Holding`·`top_n`에 박혀 있다
- `qty_step`이 전역 상수 — 종목별 호가단위 미반영
- universe 선정 로직이 라이브 API와 로컬 쿼리 두 곳에 중복
- 테스트 0개

이 검수 결과가 v6의 설계 규약 대부분을 만들었다.

## 후속

v6에서 Binance USDT-M 선물로 전환하며 재작성 중이다.
시간축 방향(ascending), epoch ms UTC, 심볼/월 파티셔닝, float64 강제,
"위치가 아닌 성질로 검사" 등이 위 한계에서 도출된 규약이다.

---

*모의투자 전용. 실계좌 운용에 사용하지 말 것. 투자 손실에 대한 책임은 사용자에게 있다.*
