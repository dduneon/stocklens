import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    KRX_LOGIN_ID: str = os.getenv("KRX_LOGIN_ID", "")
    KRX_LOGIN_PW: str = os.getenv("KRX_LOGIN_PW", "")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "stocklens-dev-secret")

    # 캐시 TTL (초)
    CACHE_TTL_OHLCV: int = 300       # 5분
    CACHE_TTL_FUNDAMENTAL: int = 3600  # 1시간
    CACHE_TTL_MARKET: int = 900       # 15분
    CACHE_TTL_RECOMMENDATIONS: int = 1800  # 30분
