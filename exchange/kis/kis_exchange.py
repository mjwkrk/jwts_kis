from core import AccountSummary
from exchange.base import Exchange
from exchange.kis.kis_types import *
from exchange.kis.kis_config import REAL_KIS, PAPER_KIS
from exchange.kis.kis_session import KISSession
from config.logging import order_logger, error_logger
from core import *
import numpy as np
import time

class KISExchange(Exchange):
    """KIS Exchange ABC 구현체."""
    _MARKET_MAP = {"ALL": "0000", "KRX": "0001", "KOSDAQ": "1002"}

    def __init__(self, paper_trading: bool = True):
        self._paper_trading = paper_trading
        self._market = KISSession(REAL_KIS, min_interval=0.0)
        if paper_trading: self._trade = KISSession(PAPER_KIS, min_interval=1)
        else: self._trade = self._market

    @property
    def _prefix(self) -> str:
        return "VTTC" if self._paper_trading else "TTTC"
    
    def _order_tr(self, side: str) -> str:
        return self._prefix + ("0012U" if side =="buy" else "0011U")

    # Market
    def market_bars(self, symbol: str, n: int = 30) -> BarArray:
        raw = self._market.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            tr_id="FHKST01010400",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         symbol,
                "FID_PERIOD_DIV_CODE":    "D",
                "FID_ORG_ADJ_PRC":        "0",
            },
        )            
        kis_bars = [KISBar.from_json(row) for row in raw["output"][:n]]
        return BarArray(
            dates  = np.array([b.date   for b in kis_bars], dtype=np.int64),
            open   = np.array([b.open   for b in kis_bars], dtype=np.float64),
            high   = np.array([b.high   for b in kis_bars], dtype=np.float64),
            low    = np.array([b.low    for b in kis_bars], dtype=np.float64),
            close  = np.array([b.close  for b in kis_bars], dtype=np.float64),
            volume = np.array([b.volume for b in kis_bars], dtype=np.float64),
        )

    def market_snapshot(self, symbol: str) -> Snapshot:
        raw = self._market.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )   
        kis = KISSnapshot.from_json(raw["output"])
        return Snapshot(
            symbol         = symbol,
            price          = kis.current_price,
            volume         = kis.accumulated_volume,
            high_52w       = kis.high_52w,
            foreign_ratio  = kis.foreign_ratio,
            per            = kis.per,
            pbr            = kis.pbr,
        )
    

    # Universe
    def universe_top_mktcap(self, n: int = 30, market: str = "KRX") -> list[str]:
        raw = self._market.get(
            "/uapi/domestic-stock/v1/ranking/market-cap",
            tr_id="FHPST01740000",
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_cond_scr_div_code":  "20174",
                "fid_div_cls_code":       "0",
                "fid_input_iscd":         self._MARKET_MAP[market],
                "fid_trgt_cls_code":      "0",
                "fid_trgt_exls_cls_code": "0",
                "fid_input_price_1":      "",
                "fid_input_price_2":      "",
                "fid_vol_cnt":            "",
            },
        )

        return [KISMktcapItem.from_json(row).symbol for row in raw["output"][:n]]
    

    # Account
    def account_summary(self) -> AccountSummary:
        raw = self._trade.get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id=self._prefix + "8434R",
            params={
                "CANO":                   self._trade.cano,
                "ACNT_PRDT_CD":           "01",
                "AFHR_FLPR_YN":           "N",
                "OFL_YN":                 "",
                "INQR_DVSN":              "02",
                "UNPR_DVSN":              "01",
                "FUND_STTL_ICLD_YN":      "N",
                "FNCG_AMT_AUTO_RDPT_YN":  "N",
                "PRCS_DVSN":              "00",
                "CTX_AREA_FK100":         "",
                "CTX_AREA_NK100":         "",
            },
        )
    
        holdings: dict[str, Holding] = {}
        for row in raw.get("output1", []):
            kh = KISBalanceHolding.from_json(row)
            if kh.qty <= 0: continue
            holdings[kh.symbol] = Holding(
                symbol    = kh.symbol,
                name      = kh.name,
                qty       = kh.qty,
                avg_price = kh.avg_price,
                cur_price = kh.current_price,                
            )

        summary_rows = raw.get("output2", [])
        if not summary_rows: error_logger.warning("output2 비어있음"); return AccountSummary(holdings=holdings, holdings_value=0.0, total_value=0.0)
        ks = KISBalanceSummary.from_json(summary_rows[0])
        return AccountSummary(
            holdings       = holdings,
            holdings_value = float(ks.holdings_value),
            total_value    = float(ks.total_value),
        )

    def account_buyable_cash(self) -> float:
        raw = self._trade.get(
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            tr_id=self._prefix + "8908R",
            params={
                "CANO":                  self._trade.cano,
                "ACNT_PRDT_CD":          "01",
                "PDNO":                  "",
                "ORD_UNPR":              "",
                "ORD_DVSN":              "00",
                "CMA_EVLU_AMT_ICLD_YN":  "N",
                "OVRS_ICLD_YN":          "N",
            },
        )
        return float(raw.get("output", {}).get("max_buy_amt", 0))
    
    # Order
    def order_submit(self, order: Order) -> OrderResult:
        body = {
            "CANO":         self._trade.cano,
            "ACNT_PRDT_CD": "01",
            "PDNO":         order.symbol,
            "ORD_DVSN":     "01" if order.is_market else "00",
            "ORD_QTY":      str(int(order.qty)),   
            "ORD_UNPR":     str(int(order.price)),
        }
        raw = self._trade.post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id=self._order_tr(order.side),
            body=body,
        )
        kr = KISOrderResponse.from_json(raw)
        result = OrderResult(
            symbol   = order.symbol,
            success  = kr.success,
            order_id = kr.order_id,
            message  = kr.message,
            raw      = raw,
        )
        if kr.success:
            order_logger.info(
                f"주문 성공 [{order.side.upper()}] {order.symbol} "
                f"x{int(order.qty)} @ {'시장가' if order.is_market else f'{int(order.price):,}원'} "
                f"→ ODNO={kr.order_id}"
            )
        else:
            order_logger.error(f"주문 실패 [{order.side.upper()}] {order.symbol}: {kr.message}")
        return result
    
    def order_cancel(self, order_id: str) -> OrderResult:
        body = {
            "CANO":                self._trade.cano,
            "ACNT_PRDT_CD":        "01",
            "KRX_FWDG_ORD_ORGNO":  "",
            "ORGN_ODNO":           order_id,
            "ORD_DVSN":            "00",
            "RVSE_CNCL_DVSN_CD":   "02",   # 02 = 취소
            "ORD_QTY":             "0",
            "ORD_UNPR":            "0",
            "QTY_ALL_ORD_YN":      "Y",    # 전량 취소
        }
        raw = self._trade.post(
            "/uapi/domestic-stock/v1/trading/order-rvsecncl",
            tr_id=self._prefix + "0013U", 
            body=body,
        )
        kr = KISOrderResponse.from_json(raw)
        result = OrderResult(
            symbol   = "",   
            success  = kr.success,
            order_id = order_id,
            message  = kr.message,
            raw      = raw,
        )
        order_logger.info(f"주문 취소 ODNO={order_id} → {'성공' if kr.success else kr.message}")
        return result
    

    def order_unfilled(self) -> bool:
        today = time.strftime("%Y%m%d")
        raw = self._trade.get(
            "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id=self._prefix + "0081R",
            params={
                "CANO":             self._trade.cano,
                "ACNT_PRDT_CD":     "01",
                "INQR_STRT_DT":     today,
                "INQR_END_DT":      today,
                "SLL_BUY_DVSN_CD":  "00",
                "PDNO":             "",
                "ORD_GNO_BRNO":     "",
                "ODNO":             "",
                "CCLD_DVSN":        "02",   # 02 = 미체결만
                "INQR_DVSN":        "00",
                "INQR_DVSN_1":      "",
                "INQR_DVSN_3":      "00",
                "EXCG_ID_DVSN_CD":  "KRX",
                "CTX_AREA_FK100":   "",
                "CTX_AREA_NK100":   "",
            },
        )
        return any(int(row.get("rmn_qty", 0)) > 0 for row in raw.get("output1", []))
    
    def execute(self, sells: list[Order], buys: list[Order], wait_after_sell: float = 2.0) -> list[OrderResult]:

        if not sells and not buys: order_logger.info("실행할 주문 없음") ; return []

        results: list[OrderResult] = []

        if sells:
            order_logger.info(f"매도 {len(sells)}건 전송")
            for o in sells:
                results.append(self.order_submit(o))
            time.sleep(wait_after_sell)

        if buys:
            order_logger.info(f"매수 {len(buys)}건 전송")
            for o in buys:
                results.append(self.order_submit(o))        
        
        return results
    
