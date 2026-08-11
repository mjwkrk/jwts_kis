import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from exchange.kis.kis_config import KISConfig
from config import app_logger, error_logger

class KISSession:
    def __init__(self, config: KISConfig, min_interval: float = 0.0):
        self._config = config
        self._min_interval = min_interval
        self._last_call_at = 0.0
        self._token: str | None = None      
        self._token_exp: datetime | None = None
        
    # Token
    @property
    def token(self) -> str:
        if self._token and self._token_exp and datetime.now() < self._token_exp - timedelta(minutes=5):
            return self._token
        return self._issue_token() 
    
    def _load_token_file(self) -> tuple[str, datetime] | None:
        if not self._config.token_file.exists():    return None
        try:
            data=json.loads(self._config.token_file.read_text(encoding="utf-8"))
            return data["access_token"], datetime.strptime(data["expires_at"], "%Y-%m-%d %H:%M:%S")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            error_logger.warning(f"토큰 파일 로드 실패 ({self._config.token_file.name}) : {e}")
            return None
        
    def _save_token_file(self, token: str, exp: datetime) -> None:
        self._config.token_file.write_text(
            json.dumps({
                "access_token": token,
                "expires_at": exp.strftime("%Y-%m-%d %H:%M:%S"),
            }, indent=4),
            encoding="utf-8"
        )

    def _issue_token(self) -> str :
        cached = self._load_token_file()
        if cached and datetime.now() < cached[1] - timedelta(minutes=5):
            self._token, self._token_exp = cached
            app_logger.info(f"토큰 캐시 로드 성공: {self._config.token_file.name}")
            return self._token
        
        try:
            resp = requests.post(
                f"{self._config.base_url}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey":     self._config.appkey,
                    "appsecret":  self._config.appsecret,
                },
                timeout=10,
            ).json()
        except requests.RequestException as e:
            error_logger.critical(f"토큰 발급 네트워크 실패: {e}")
            raise
        
        if "access_token" not in resp:
            error_logger.critical(f"토큰 발급 거절: {resp}")
            raise RuntimeError(f"토큰 발급 실패: {resp['msg1']}")
        
        token = resp["access_token"]
        exp = datetime.now() + timedelta(seconds=int(resp["expires_in"]))
        self._save_token_file(token, exp)
        self._token, self._token_exp = token, exp
        app_logger.info(f"토큰 신규 발급 완료 / 만료: {exp:%Y-%m-%d %H:%M}")
        return token
    

    # Throttle
    def _throttle(self) -> None:
        if self._min_interval == 0: return
        elapsed = time.time() - self._last_call_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_at = time.time()


    # HTTP request
    def _headers(self, tr_id: str, custtype: str = "P") -> dict:
        return {
            "authorization": f"Bearer {self.token}",
            "appkey":        self._config.appkey,
            "appsecret":     self._config.appsecret,
            "tr_id":         tr_id,
            "custtype":      custtype,
        }

    def _check_response(self, data: dict, tr_id: str) -> dict:
            rt_cd = data.get("rt_cd")
            if rt_cd not in (None, "0"):
                msg = f"KIS API 에러 [{tr_id}] rt_cd={rt_cd} {data.get('msg_cd','')}: {data.get('msg1','')}"
                error_logger.error(msg)
                raise RuntimeError(msg)
            return data

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        self._throttle()
        url = f"{self._config.base_url}{path}"
        try: resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        except requests.RequestException as e: error_logger.error(f"GET 실패 [{tr_id}] {path}: {e}") ; raise
        return self._check_response(resp.json(), tr_id)

    def post(self, path: str, tr_id: str, body: dict) -> dict:
        self._throttle()
        url = f"{self._config.base_url}{path}"
        try: resp = requests.post(url, headers=self._headers(tr_id), json=body, timeout=10)
        except requests.RequestException as e: error_logger.error(f"POST 실패 [{tr_id}] {path}: {e}") ; raise
        return self._check_response(resp.json(), tr_id)
    
    @property
    def cano(self) -> str:
        return self._config.cano or ""
    
