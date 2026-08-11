from abc import ABC, abstractmethod
from core import BarArray, Snapshot, Holding, AccountSummary, Order, OrderResult

class Exchange(ABC):
    """모든 거래소가 구현해야 할 공통 인터페이스.

    원칙:
    - 단일 쿼리만 제공. 병렬화는 호출자(data/collector.py) 소관
    - 응답은 core/types의 표준 dataclass로 변환해서 반환
    - 거래소 고유 필드명/코드는 구현체 안에서만 존재
    """


    # Market data
    @abstractmethod
    def market_bars(self, symbol: str, n: int = 30) -> BarArray:
        """일봉 n개 조회. index 0 = 가장 최근."""
        ...

    @abstractmethod
    def market_snapshot(self, symbol: str) -> Snapshot:
        """현시점 스냅샷 (현재가, 누적거래량 등)"""
        ...

    # Universe
    @abstractmethod
    def universe_top_mktcap(self, n: int = 30, market: str = "KOSPI") -> list[str]:
        """시총 상위 n개 종목코드.
        market: 'KOSPI', 'SPOT', 'FUTURES', 'ALL'등. 구현체별 해석"""
        ...


    # Account
    @abstractmethod
    def account_summary(self) -> AccountSummary:
        """현재 보유종목. key=symbol"""
        ...

    @abstractmethod
    def account_buyable_cash(self) -> float:
        """매수가능금액 (현금 잔고)"""
        ...


    # Order
    @abstractmethod
    def order_submit(self, order: Order) -> OrderResult:
        """주문 전송. 성공/실패 정보를 OrderResult로 반환."""
        ...

    @abstractmethod
    def order_cancel(self, order_id: str) -> OrderResult:
        """기존 주문 취소"""
        ...
        
    @abstractmethod
    def order_unfilled(self) -> bool:
        """미체결 주문 존재 여부"""
        ...

    