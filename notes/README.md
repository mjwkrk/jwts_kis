# PAPER_JWTS_V2 
KIS API-based 자동화 매매 시스템

# Framework


# Development
1. OCI 서버에 올려두고 cron으로 9시마다 주문
2. Telegram API로 매매시, 그리고 하루에 3번 PnL 보고 하도록 자동화

# 팩터 추가하는 법
1. factors.py에 팩터 함수 추가
2. scorer.py의 FACTOR_MAP에 추가 
    - e.g. "yest_vol": lambda p, d: KIS_yesterday_volume(d)
3. weights: dict을 바꿔서 호출
    - weights = {"yest_vol": 0.5, "momentum": 0.3, "value_per": 0.2}

# To-Do
X KRX 등의 Data source를 연결해서 시그널 자동계산하도록 연동 => 취소
1. DataFetcher를 만들어서 데이터베이스 구축하기
2. Backtesting 엔진을 만들기
3. 전략 구현하기 -> FACTOR_POOL에 추가
4. market들 확장하기



