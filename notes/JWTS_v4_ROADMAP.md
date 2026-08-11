<!-- ---
marp: true
--- -->


# JWTS v4 리팩토링 로드맵

> 원칙: 단순하고 직관적이고 빠르게. fanxy보다 실용.

---

## 현재 시스템 진단 (v3)

### 구조 요약
```
paper_JWTS_v3/
├── main_p.py          # 진입점 (build_target → build_orders → execute)
├── broker/            # KIS API 직접 호출 (auth, http, market, trading)
├── strategy/          # 스코어링 (factors, operators, scoring)
├── oms/               # 주문관리 (planner, executor) — 미완성
├── data/              # 비어있음
├── utils/             # Telegram 리포트
└── config/            # 설정, 로깅
```

### 핵심 문제 6가지

**1. 데이터 타입: 전부 dict/list/str**
- KIS API가 `{"stck_clpr": "68400"}` 같은 str을 반환하면, 소비하는 곳마다 `int()`, `float()` 변환
- factors.py의 모든 함수가 `int(daily_data[i]["stck_clpr"])` 패턴 반복
- operators.py의 정규화 함수들이 Python for-loop으로 하나씩 계산
- **np.array 전환 시 10~100배 속도 개선 가능**

**2. KIS API에 완전히 종속**
- `MarketData` 클래스가 KIS 응답 dict를 그대로 반환
- factors.py 함수들이 `"stck_clpr"`, `"acml_vol"` 같은 KIS 필드명을 직접 참조
- trading.py의 tr_id, 헤더 구성이 KIS 전용
- **다른 거래소(crypto 등)를 붙이려면 전체를 다시 써야 하는 구조**

**3. OMS 미완성 — planner와 executor 분리만 되고 연결 안됨**
- `main_p.py`에 `execute_orders()` 함수가 따로 있고, `OrderExecutor`는 쓰이지 않음
- `OrderPlanner`에 `rebalance_calculate()` 메서드가 없는데 `main_p.py`에서 호출 시도
- 매도→체결확인→매수 시퀀스가 제대로 구현되지 않은 상태

**4. 데이터 레이어 부재**
- data/ 디렉토리가 사실상 비어있음
- 매번 실행할 때마다 API를 처음부터 전부 호출
- 캐시, 로컬 저장, 히스토리 축적 구조 없음
- 백테스트 불가능

**5. 오케스트레이션이 main_p.py에 하드코딩**
- `build_target()`, `build_orders()`, `execute_orders()`, `preview_orders()` 가 전부 전역 함수
- 토큰(real vs paper)을 수동으로 골라서 전달
- 파이프라인을 바꾸려면 main_p.py 자체를 수정해야 함

**6. Scorer가 API 호출과 계산을 동시에 수행**
- `Scorer.score()` 안에서 `univ_price_multi()`, `univ_daily_multi()` 호출 → 데이터 fetch
- 그 다음 바로 팩터 계산 → 정규화 → 스코어링
- 데이터 수집과 시그널 계산이 분리되지 않아서 테스트·재사용 불가

---

## 새 아키텍처 설계 (v4)

### 핵심 변경 원칙

| 원칙 | 설명 |
|------|------|
| **np.array 우선** | API 응답을 받자마자 np.array로 변환. 이후 모든 연산은 벡터화 |
| **거래소 추상화** | Exchange 인터페이스로 KIS/Binance/etc를 갈아끼울 수 있게 |
| **데이터↔로직 분리** | fetch한 데이터를 표준 포맷으로 변환 → 시그널은 표준 포맷만 소비 |
| **단순한 파이프라인** | Data → Signal → Target → Order → Execute 5단계를 명확히 |

### 새 디렉토리 구조

```
JWTS_v4/
│
├── main.py                    # 진입점: Pipeline 실행
│
├── core/                      # 공통 자료구조 + 유틸
│   ├── types.py               # Bar, Snapshot 등 np.array 기반 데이터 컨테이너
│   └── utils.py               # 공통 헬퍼 (로깅 설정 포함)
│
├── exchange/                  # 거래소 추상화 (1개 인터페이스, N개 구현)
│   ├── base.py                # Exchange ABC (fetch_bars, fetch_snapshot, submit_order ...)
│   ├── kis_types.py           # KIS API 응답 @dataclass (raw dict → typed 파싱)
│   ├── kis.py                 # KIS 구현체 (kis_types → core types 변환)
│   └── (binance.py)           # 나중에 추가
│
├── data/                      # 데이터 수집·저장·로딩
│   ├── collector.py           # exchange에서 raw 데이터 수집 → np.array 변환
│   ├── store.py               # 로컬 저장/로딩 (parquet or npy)
│   └── universe.py            # 유니버스 정의·필터
│
├── signal/                    # 시그널 (순수 계산, API 호출 없음)
│   ├── factors.py             # 팩터 함수들 (np.array in → float out)
│   ├── operators.py           # 정규화, 가중 함수들 (np.array in → np.array out)
│   └── scorer.py              # Scorer: factors + operators 조합 → 종목별 점수
│
├── portfolio/                 # 타겟 포트폴리오 구성
│   └── builder.py             # TargetBuilder: score → target weights
│
├── oms/                       # 주문 관리
│   ├── planner.py             # OrderPlanner: target vs holdings → order list
│   └── executor.py            # OrderExecutor: order list → exchange API 전송
│
├── notify/                    # 알림
│   └── telegram.py            # Telegram 전송
│
└── config/
    ├── settings.py            # 설정 (env 로딩)
    └── exchanges.yaml         # 거래소별 설정 (나중에)
```

---

## Phase별 로드맵

---

### Phase 0: core/types.py — 데이터 컨테이너 정의 (Day 1)

**왜 먼저?** 모든 모듈이 소비하는 "공통 언어"를 먼저 정해야 나머지를 만들 수 있다.

**만들 것:**

```python
# core/types.py
import numpy as np
from dataclasses import dataclass

@dataclass
class BarArray:
    """일봉/분봉 데이터. 모든 필드가 np.array (길이 = 날짜 수)"""
    dates:   np.ndarray   # dtype=int64, YYYYMMDD 정수 (예: 20260527)
    open:    np.ndarray   # dtype=float64
    high:    np.ndarray   # dtype=float64
    low:     np.ndarray   # dtype=float64
    close:   np.ndarray   # dtype=float64
    volume:  np.ndarray   # dtype=float64
    # index 0 = 가장 최근 날짜 (KIS API 순서와 동일)

    def __len__(self):
        return len(self.close)

    def __getitem__(self, idx):
        """슬라이싱 지원: bars[:20]"""
        return BarArray(
            dates=self.dates[idx], open=self.open[idx],
            high=self.high[idx], low=self.low[idx],
            close=self.close[idx], volume=self.volume[idx],
        )

@dataclass
class Snapshot:
    """종목 현재가 스냅샷. 스칼라 값들."""
    code:           str
    price:          float
    volume:         float     # 당일 누적거래량
    high_52w:       float     # 52주 최고가
    foreign_ratio:  float     # 외국인 소진율
    per:            float
    pbr:            float

@dataclass
class Holding:
    """보유 종목 1건"""
    code:       str
    name:       str
    qty:        int
    avg_price:  float
    cur_price:  float

@dataclass  
class Order:
    """주문 1건"""
    code:   str
    side:   str       # "buy" | "sell"
    qty:    int
    price:  float     # 0 = 시장가
```

**핵심 포인트:**
- KIS 필드명(`stck_clpr` 등)이 여기엔 없다. 거래소-중립적 이름
- 모든 시계열은 `np.ndarray`. dict 아님
- `Snapshot`, `Holding`, `Order`는 단순 dataclass — 1건의 정보를 담는 그릇
- 나중에 crypto를 붙여도 같은 `BarArray`와 `Snapshot`을 쓰면 됨

---

### Phase 1: exchange/ — 거래소 추상화 (Day 2~3)

**목표:** "KIS API 호출"과 "비즈니스 로직"을 완전히 분리

**1-1. base.py (인터페이스 정의)**

```python
# exchange/base.py
from abc import ABC, abstractmethod
from core.types import BarArray, Snapshot, Holding, Order

class Exchange(ABC):
    """모든 거래소가 구현해야 할 인터페이스"""

    @abstractmethod
    def get_bars(self, code: str, n: int = 30) -> BarArray:
        """일봉 n개 조회 → BarArray"""
        ...

    @abstractmethod
    def get_snapshot(self, code: str) -> Snapshot:
        """현재가 스냅샷 조회"""
        ...

    @abstractmethod
    def get_top_mktcap(self, n: int = 30) -> list[str]:
        """시총 상위 n개 종목코드 리스트"""
        ...

    @abstractmethod
    def get_holdings(self) -> list[Holding]:
        """보유종목 조회"""
        ...

    @abstractmethod
    def get_buyable_cash(self) -> float:
        """매수가능금액"""
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> dict:
        """주문 전송. 결과 dict 반환"""
        ...

    @abstractmethod
    def has_unfilled(self) -> bool:
        """미체결 주문 존재 여부"""
        ...
```

**1-2. exchange/kis_types.py (KIS API 응답 dataclass)**

KIS API의 raw dict 응답을 바로 core types로 변환하지 않고, 중간 단계로 **KIS 전용 dataclass**를 둔다.
이렇게 하면:
- API 문서의 필드가 코드에 한글 주석으로 남아서 가독성 확보
- IDE 자동완성으로 오타 방지 (`json["stck_clpr"]` 대신 `resp.stck_clpr`)
- KIS API 스펙이 바뀌면 이 파일만 수정하면 됨

```python
# exchange/kis_types.py
from dataclasses import dataclass

@dataclass
class KISPrice:
    """주식현재가 시세 응답 (FHKST01010100)"""
    iscd_stat_cls_code: str   # 종목 상태 구분 코드
    stck_prpr:  int           # 주식 현재가
    acml_vol:   int           # 누적 거래량
    w52_hgpr:   int           # 52주 최고가
    w52_lwpr:   int           # 52주 최저가
    hts_frgn_ehrt: float      # 외국인 소진율
    per:        float         # PER
    pbr:        float         # PBR
    stck_mxpr:  int           # 상한가
    stck_llam:  int           # 하한가

    @classmethod
    def from_json(cls, data: dict) -> "KISPrice":
        return cls(
            iscd_stat_cls_code = data["iscd_stat_cls_code"],
            stck_prpr  = int(data["stck_prpr"]),
            acml_vol   = int(data["acml_vol"]),
            w52_hgpr   = int(data["w52_hgpr"]),
            w52_lwpr   = int(data["w52_lwpr"]),
            hts_frgn_ehrt = float(data["hts_frgn_ehrt"]),
            per        = float(data["per"]),
            pbr        = float(data["pbr"]),
            stck_mxpr  = int(data["stck_mxpr"]),
            stck_llam  = int(data["stck_llam"]),
        )

@dataclass
class KISDailyBar:
    """주식 일봉 1건 (FHKST01010400)"""
    stck_bsop_date: int       # 영업일자 (YYYYMMDD)
    stck_oprc:  int           # 시가
    stck_hgpr:  int           # 고가
    stck_lwpr:  int           # 저가
    stck_clpr:  int           # 종가
    acml_vol:   int           # 누적 거래량

    @classmethod
    def from_json(cls, data: dict) -> "KISDailyBar":
        return cls(
            stck_bsop_date = int(data["stck_bsop_date"]),
            stck_oprc  = int(data["stck_oprc"]),
            stck_hgpr  = int(data["stck_hgpr"]),
            stck_lwpr  = int(data["stck_lwpr"]),
            stck_clpr  = int(data["stck_clpr"]),
            acml_vol   = int(data["acml_vol"]),
        )

@dataclass
class KISHolding:
    """보유종목 1건 (VTTC8434R output1)"""
    pdno:           str       # 종목코드
    prdt_name:      str       # 종목명
    hldg_qty:       int       # 보유수량
    pchs_avg_pric:  float     # 매입평균가
    prpr:           int       # 현재가
    evlu_pfls_rt:   float     # 평가손익률

    @classmethod
    def from_json(cls, data: dict) -> "KISHolding":
        return cls(
            pdno          = data["pdno"],
            prdt_name     = data["prdt_name"],
            hldg_qty      = int(data["hldg_qty"]),
            pchs_avg_pric = float(data["pchs_avg_pric"]),
            prpr          = int(data["prpr"]),
            evlu_pfls_rt  = float(data["evlu_pfls_rt"]),
        )
```

**데이터 흐름 (3단계):**
```
KIS API (raw dict) → KISPrice/KISDailyBar (KIS dataclass) → Snapshot/BarArray (core type)
                      ↑ kis_types.py에서 파싱          ↑ kis.py에서 변환
```

필요한 API endpoint마다 하나씩 dataclass를 만들면 된다.
나중에 KIS API 필드를 추가로 쓰고 싶으면 해당 dataclass에 필드만 추가.

**1-3. exchange/kis.py (KIS 구현체)**

현재 `broker/` 폴더의 코드를 이 한 파일로 합친다:
- `auth.py`의 토큰 관리 → `KISExchange.__init__()` 에서 처리
- `httpclient.py`의 rate limiter → `KISExchange` 내부 private 메서드
- `market.py`의 API 호출 → `get_bars()`, `get_snapshot()` 등으로 매핑
- `trading.py`의 주문/잔고 → `submit_order()`, `get_holdings()` 등으로 매핑

**핵심 변환 — KIS dataclass → core types:**

```python
# exchange/kis.py 내부 예시
from exchange.kis_types import KISDailyBar, KISPrice, KISHolding

def get_bars(self, code: str, n: int = 30) -> BarArray:
    raw: list[dict] = self._call_daily_api(code)
    
    # Step 1: raw dict → KIS dataclass (타입 안전하게 파싱)
    kis_bars = [KISDailyBar.from_json(d) for d in raw[:n]]
    
    # Step 2: KIS dataclass → core BarArray (거래소-중립 포맷)
    return BarArray(
        dates  = np.array([b.stck_bsop_date for b in kis_bars], dtype=np.int64),
        open   = np.array([b.stck_oprc      for b in kis_bars], dtype=np.float64),
        high   = np.array([b.stck_hgpr      for b in kis_bars], dtype=np.float64),
        low    = np.array([b.stck_lwpr      for b in kis_bars], dtype=np.float64),
        close  = np.array([b.stck_clpr      for b in kis_bars], dtype=np.float64),
        volume = np.array([b.acml_vol       for b in kis_bars], dtype=np.float64),
    )

def get_snapshot(self, code: str) -> Snapshot:
    raw: dict = self._call_price_api(code)
    
    kp = KISPrice.from_json(raw)   # IDE가 kp.per, kp.pbr 자동완성
    return Snapshot(
        code=code, price=kp.stck_prpr, volume=kp.acml_vol,
        high_52w=kp.w52_hgpr, foreign_ratio=kp.hts_frgn_ehrt,
        per=kp.per, pbr=kp.pbr,
    )
```

**핵심:** `data["stck_clpr"]` 같은 문자열 키 접근이 코드에서 완전히 사라진다.
`kis_types.py`의 `from_json()`에서 한 번만 파싱하고, 이후엔 전부 `.stck_clpr` 같은 속성 접근.

---

### Phase 2: signal/ — 팩터 + 스코어링 np.array 전환 (Day 4~5)

**목표:** 현재 factors.py의 Python loop → numpy 벡터 연산

**2-1. factors.py 리팩토링**

현재 (느림):
```python
def KIS_momentum(daily_data: list[dict], n=20):
    recent = int(daily_data[0]["stck_clpr"])
    past = int(daily_data[n-1]["stck_clpr"])
    return (recent / past) - 1
```

새 버전 (빠름):
```python
def momentum(close: np.ndarray, n: int = 20) -> float:
    """close[0] = 최근. np.array를 직접 받는다."""
    if len(close) < n: return 0.0
    return (close[0] / close[n-1]) - 1

def volume_ratio(volume: np.ndarray, n: int = 20) -> float:
    if len(volume) < n + 1: return 0.0
    return volume[0] / volume[1:n+1].mean()

def volatility(close: np.ndarray, n: int = 20) -> float:
    if len(close) < n + 1: return 0.0
    returns = np.diff(close[:n+1]) / close[1:n+1]  # 벡터 연산
    return -returns.std()

def ma_divergence(close: np.ndarray, n: int = 20) -> float:
    if len(close) < n: return 0.0
    return (close[0] / close[:n].mean()) - 1
```

**변경 포인트:**
- 함수 인자: `list[dict]` → `np.ndarray`
- KIS 필드명 참조 제거 — `close`, `volume` 같은 보편적 이름
- `KIS_` 접두어 제거 — 거래소 무관한 순수 계산
- 내부 연산: for loop → numpy 벡터

**2-2. operators.py 리팩토링**

현재:
```python
def normalize_rank(values: list[float]):
    sorted_indices = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for rank, idx in enumerate(sorted_indices, start=1):
        ranks[idx] = rank
    return [r/sum(ranks) for r in ranks]
```

새 버전:
```python
def rank_normalize(values: np.ndarray) -> np.ndarray:
    """순위 기반 정규화. 합=1"""
    ranks = values.argsort().argsort().astype(float) + 1  # 1-based rank
    return ranks / ranks.sum()

def minmax_normalize(values: np.ndarray) -> np.ndarray:
    rng = values.max() - values.min()
    if rng == 0: return np.full_like(values, 1.0 / len(values))
    scaled = (values - values.min()) / rng
    s = scaled.sum()
    return scaled / s if s > 0 else np.full_like(values, 1.0 / len(values))
```

**2-3. scorer.py 리팩토링**

핵심 변경: 데이터 fetch를 밖으로 빼고, 순수 계산만 수행

```python
class Scorer:
    def __init__(self, weights: dict[str, float], norm_fn=rank_normalize):
        self.weights = weights
        self.norm_fn = norm_fn

    def score(
        self,
        codes: list[str],
        bars: dict[str, BarArray],          # 이미 fetch된 데이터
        snapshots: dict[str, Snapshot],     # 이미 fetch된 데이터
    ) -> np.ndarray:
        """codes 순서대로 종합점수 np.array 반환"""
        n = len(codes)
        
        FACTOR_MAP = {
            "momentum":   lambda snap, bar: momentum(bar.close),
            "volume":     lambda snap, bar: volume_ratio(bar.volume),
            "volatility": lambda snap, bar: volatility(bar.close),
            "foreign":    lambda snap, bar: snap.foreign_ratio,
            # ...
        }

        # 팩터별 raw 값 수집 → (n_factors × n_stocks) 행렬
        raw = np.zeros((len(self.weights), n))
        for i, factor_name in enumerate(self.weights):
            fn = FACTOR_MAP[factor_name]
            for j, code in enumerate(codes):
                raw[i, j] = fn(snapshots[code], bars[code])

        # 팩터별 정규화
        normed = np.zeros_like(raw)
        for i in range(len(self.weights)):
            normed[i] = self.norm_fn(raw[i])

        # 가중합
        w = np.array(list(self.weights.values()))
        scores = (w[:, None] * normed).sum(axis=0)  # (n_stocks,)
        return scores
```

---

### Phase 3: portfolio/ + oms/ — 타겟 구성 + 주문 (Day 6~7)

**3-1. portfolio/builder.py**

```python
class TargetBuilder:
    def top_n(self, codes: np.ndarray, scores: np.ndarray, n: int = 5) -> dict[str, float]:
        """상위 n개 선택, 비중 합=1"""
        top_idx = np.argsort(scores)[-n:][::-1]
        top_scores = scores[top_idx]
        weights = top_scores / top_scores.sum()
        return {codes[i]: float(w) for i, w in zip(top_idx, weights)}
```

**3-2. oms/planner.py — 현재 코드 정리**

현재 planner.py의 로직은 괜찮은 편. 다만:
- 입력을 `list[Holding]`으로 통일
- 출력을 `list[Order]`로 통일
- `rebalance()` 메서드 하나로 매도+매수 통합

```python
class OrderPlanner:
    def rebalance(
        self,
        target: dict[str, float],        # {code: weight}
        holdings: list[Holding],
        buyable_cash: float,
        exchange: Exchange,               # 현재가 조회용
    ) -> list[Order]:
        """매도 orders + 매수 orders를 한번에 반환"""
        ...
```

**3-3. oms/executor.py — 실제 주문 전송**

```python
class OrderExecutor:
    def __init__(self, exchange: Exchange):
        self.exchange = exchange

    def execute(self, orders: list[Order]) -> list[dict]:
        sells = [o for o in orders if o.side == "sell"]
        buys  = [o for o in orders if o.side == "buy"]

        results = []
        for o in sells:
            results.append(self.exchange.submit_order(o))

        if sells:
            self._wait_settle()

        for o in buys:
            results.append(self.exchange.submit_order(o))

        return results
```

---

### Phase 4: data/ — 데이터 수집·저장 (Day 8~9)

**목표:** API를 매번 호출하지 않고 로컬에 축적

**4-1. data/collector.py**

```python
class DataCollector:
    def __init__(self, exchange: Exchange):
        self.exchange = exchange

    def collect_bars(self, codes: list[str], n: int = 30) -> dict[str, BarArray]:
        """여러 종목 일봉 수집. ThreadPool로 병렬 호출"""
        ...

    def collect_snapshots(self, codes: list[str]) -> dict[str, Snapshot]:
        ...
```

**4-2. data/store.py**

```python
class DataStore:
    def __init__(self, base_dir: str = "data/"):
        ...

    def save_bars(self, code: str, bars: BarArray):
        """np.savez 또는 parquet로 저장"""
        ...

    def load_bars(self, code: str, n: int = 30) -> BarArray | None:
        """로컬에 있으면 로드, 없으면 None"""
        ...
```

저장 포맷은 처음엔 `np.savez`로 시작 (가장 단순). 나중에 parquet으로 전환해도 됨.

**4-3. data/universe.py**

```python
class Universe:
    def __init__(self, exchange: Exchange):
        self.exchange = exchange

    def top_mktcap(self, n: int = 30) -> list[str]:
        return self.exchange.get_top_mktcap(n)

    def from_list(self, codes: list[str]) -> list[str]:
        """수동 지정 유니버스"""
        return codes
```

---

### Phase 5: main.py + notify/ — 파이프라인 통합 (Day 10)

**깔끔한 진입점:**

```python
# main.py
from exchange.kis import KISExchange
from data.collector import DataCollector
from data.universe import Universe
from signal.scorer import Scorer
from portfolio.builder import TargetBuilder
from oms.planner import OrderPlanner
from oms.executor import OrderExecutor
from notify.telegram import send_trade_report

def run():
    # 1. 거래소 연결
    exchange = KISExchange()

    # 2. 유니버스 선정
    codes = Universe(exchange).top_mktcap(30)

    # 3. 데이터 수집
    collector = DataCollector(exchange)
    bars = collector.collect_bars(codes)
    snapshots = collector.collect_snapshots(codes)

    # 4. 시그널 → 타겟
    weights = {"momentum": 0.5, "volume": 0.2, "volatility": 0.3}
    scores = Scorer(weights).score(codes, bars, snapshots)
    target = TargetBuilder().top_n(codes, scores, n=5)

    # 5. 주문 계산 → 실행
    holdings = exchange.get_holdings()
    cash = exchange.get_buyable_cash()
    orders = OrderPlanner().rebalance(target, holdings, cash, exchange)
    OrderExecutor(exchange).execute(orders)

    # 6. 알림
    send_trade_report(orders)
```

**현재 main_p.py 75줄 vs 새 main.py ~25줄.** 각 단계가 뭘 하는지 한눈에 보임.

---

### Phase 6: 백테스트 엔진 (Day 11~14)

Phase 0~5가 끝나면 백테스트는 자연스럽게 가능해짐:
- `BarArray`에 과거 데이터가 들어있음
- `Scorer`는 API를 안 부르고 데이터만 받으면 됨
- 날짜를 한칸씩 밀면서 `score() → target → rebalance()` 반복

```python
# backtest/engine.py (개략)
class Backtest:
    def run(self, bars: dict[str, BarArray], start: int, end: int):
        for t in range(start, end):
            window = {code: bar[t:t+30] for code, bar in bars.items()}
            scores = self.scorer.score(codes, window, ...)
            target = self.builder.top_n(codes, scores)
            # 가상 리밸런싱 + PnL 기록
```

---

### Phase 7: 멀티 거래소 확장 (Day 15+)

새 거래소 추가 = `exchange/binance.py` 파일 1개 작성:

```python
class BinanceExchange(Exchange):
    def get_bars(self, code, n=30) -> BarArray: ...
    def get_snapshot(self, code) -> Snapshot: ...
    def submit_order(self, order: Order) -> dict: ...
    # ...
```

나머지 코드(signal, portfolio, oms)는 **한 글자도 안 바꿔도 됨**.

---

## 작업 순서 체크리스트

| # | Phase | 파일 | 예상 시간 | 선행 |
|---|-------|------|-----------|------|
| 0 | 데이터 타입 정의 | `core/types.py` | 1시간 | - |
| 1a | Exchange 인터페이스 | `exchange/base.py` | 30분 | Phase 0 |
| 1b | KIS 응답 dataclass | `exchange/kis_types.py` | 1시간 | Phase 1a |
| 1c | KIS 구현체 | `exchange/kis.py` | 2.5시간 | Phase 1b |
| 2a | 팩터 np 전환 | `signal/factors.py` | 1시간 | Phase 0 |
| 2b | 연산자 np 전환 | `signal/operators.py` | 1시간 | Phase 0 |
| 2c | 스코어러 리팩토링 | `signal/scorer.py` | 1.5시간 | Phase 2a,2b |
| 3a | 타겟빌더 | `portfolio/builder.py` | 30분 | Phase 2c |
| 3b | 주문플래너 | `oms/planner.py` | 1.5시간 | Phase 0 |
| 3c | 주문실행기 | `oms/executor.py` | 1시간 | Phase 1b, 3b |
| 4 | 데이터 수집·저장 | `data/` | 2시간 | Phase 1b |
| 5 | 파이프라인 통합 | `main.py` + `notify/` | 1시간 | 전부 |
| 6 | 백테스트 | `backtest/` | 4시간 | Phase 4 |
| 7 | 멀티거래소 | `exchange/binance.py` | 3시간 | Phase 5 |

---

## 마이그레이션 전략

**점진적 교체를 권장합니다.**

1. Phase 0~2를 먼저 만들고, 기존 `main_p.py`에서 새 모듈을 import해서 테스트
2. 새 모듈이 기존과 같은 결과를 내는지 확인
3. 확인되면 기존 `broker/`, `strategy/` 삭제
4. Phase 3~5 진행

이렇게 하면 새 시스템이 완성되기 전에도 기존 시스템이 계속 돌아갑니다.

---

## np.array 전환 효과 요약

| 연산 | 현재 (dict/list) | 전환 후 (np.array) |
|------|-----------------|-------------------|
| 30종목 모멘텀 계산 | for loop 30회 + int() 변환 | 벡터 나눗셈 1회 |
| 팩터 정규화 | sorted() + enumerate + list comprehension | `argsort().argsort()` |
| 가중합 스코어 | for loop + dict 접근 | `(w * normed).sum(axis=0)` |
| 슬라이싱 | `daily_data[0:20]` (list of dict) | `bar.close[:20]` (ndarray view, zero-copy) |

---

## 질문이 생길 수 있는 것들

**Q: `BarArray`를 왜 DataFrame이 아니라 dataclass + ndarray로?**
A: DataFrame은 편리하지만 오버헤드가 있고, 컬럼 이름으로 접근(`df["close"]`)하면 typo 방지가 안 됨. dataclass는 IDE 자동완성이 되고, ndarray는 pandas보다 빠름. 나중에 필요하면 `.to_dataframe()` 메서드 하나 추가하면 됨.

**Q: `Exchange` ABC에 메서드가 너무 많지 않나?**
A: 7개 메서드. 이것보다 줄이면 기능이 부족하고, 늘리면 새 거래소 붙일 때 부담됨. 딱 필요한 만큼.

**Q: 기존 operators.py의 ts_ 함수들은?**
A: `ts_delay`, `ts_delta` 등은 Phase 2에서 np 버전으로 전환해서 `signal/operators.py`에 유지. 다만 이미 np.array이면 `close[d]`, `close[0] - close[d]`로 끝나서 함수가 필요 없을 수도 있음. 판단은 그때.
