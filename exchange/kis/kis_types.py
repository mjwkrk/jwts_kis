from dataclasses import dataclass

@dataclass(frozen=True)
class KISBar:
    """KIS 주식현재가 일자별.
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/quotations/inquire-daily-price
    tr_id:      FHKST01010400
    """
    date:    int    # stck_bsop_date — YYYYMMDD
    open:    int    # stck_oprc
    high:    int    # stck_hgpr
    low:     int    # stck_lwpr
    close:   int    # stck_clpr
    volume:  int    # acml_vol

    @classmethod
    def from_json(cls, data: dict) -> "KISBar":
        return cls(
            date = int(data["stck_bsop_date"]),
            open   = int(data["stck_oprc"]),
            high   = int(data["stck_hgpr"]),
            low    = int(data["stck_lwpr"]),
            close  = int(data["stck_clpr"]),
            volume = int(data["acml_vol"]),
        )
    
@dataclass(frozen=True)
class KISSnapshot:
    """KIS 주식현재가 시세.
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/quotations/inquire-price
    tr_id:      FHKST01010100
    """
    status_code:            str 
    current_price:          int
    accumulated_volume:     int
    high_52w:               int
    low_52w:                int
    change:                 int
    change_rate:            float
    foreign_ratio:          float
    per:                    float
    pbr:                    float

    @classmethod
    def from_json(cls, data: dict) -> "KISSnapshot":
        return cls(
            status_code         = data["iscd_stat_cls_code"],
            current_price       = int(data["stck_prpr"]),
            accumulated_volume  = int(data["acml_vol"]),
            high_52w            = int(data["w52_hgpr"]),
            low_52w             = int(data["w52_lwpr"]),
            change              = int(data["prdy_vrss"] or 0),
            change_rate         = float(data["prdy_ctrt"] or 0),
            foreign_ratio       = float(data["hts_frgn_ehrt"]),
            per                 = float(data["per"] or 0),   
            pbr                 = float(data["pbr"] or 0),
        )

@dataclass(frozen=True)
class KISMktcapItem:
    """KIS 주식현재가 일자별.
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/ranking/market-cap
    tr_id:      FHPST01740000
    """
    symbol:     str
    name:       str

    @classmethod
    def from_json(cls, data: dict) -> "KISMktcapItem":
        return cls(
            symbol  = data["mksc_shrn_iscd"],
            name    = data["hts_kor_isnm"]
        )
    
@dataclass(frozen=True)
class KISBalanceHolding:
    """KIS 주식잔고조회. [output1]
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/trading/inquire-balance
    tr_id:      VTTC8434R #실전:TTTC8434R
    """
    symbol:         str
    name:           str
    qty:            int
    avg_price:      float
    current_price:  int

    @classmethod
    def from_json(cls, data: dict) -> "KISBalanceHolding":
        return cls(
            symbol         = data["pdno"],
            name           = data["prdt_name"],
            qty            = int(data["hldg_qty"]),
            avg_price      = float(data["pchs_avg_pric"]),
            current_price  = int(data["prpr"]),
        )

@dataclass(frozen=True)
class KISBalanceSummary:
    """KIS 주식잔고조회.[output2]
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/trading/inquire-balance
    tr_id:      VTTC8434R #실전:TTTC8434R
    """
    holdings_value:     int
    total_value:        int
    buy_amount:         int
    total_pnl:          int

    @classmethod
    def from_json(cls, data: dict) -> "KISBalanceSummary":
        return cls(
            holdings_value  = int(data["evlu_amt_smtl_amt"]),
            total_value     = int(data["tot_evlu_amt"]),
            buy_amount      = int(data["pchs_amt_smtl_amt"]),
            total_pnl       = int(data["evlu_pfls_smtl_amt"]),
        )

@dataclass(frozen=True)
class KISOrderResponse:
    """KIS 주식주문[현금].
    
    API Docs:   https://apiportal.koreainvestment.com/apiservice-apiservice?/uapi/domestic-stock/v1/trading/order-cash
    tr_id:      (매도) VTTC0011U (매수) VTTC0012U       #실전:(매도) TTTC0011U (매수) TTTC0012U
    """
    rt_code:    str
    message:    str
    order_id:   str | None

    @classmethod
    def from_json(cls, data: dict) -> "KISOrderResponse":
        output = data.get("output") or {}
        return cls(
            rt_code  = data.get("rt_cd", ""),
            message  = data.get("msg1", ""),
            order_id = output.get("ODNO"),
        )
    
    @property
    def success(self) -> bool:
        return self.rt_code == "0"