import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    KRX_LOGIN_ID: str = os.getenv("KRX_LOGIN_ID", "")
    KRX_LOGIN_PW: str = os.getenv("KRX_LOGIN_PW", "")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    PORT: int = int(os.getenv("FLASK_PORT", "5001"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "stocklens-dev-secret")

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://stocklens:stocklens_pw@localhost:5432/stocklens",
    )

    # DART 전자공시 API 키 (재무제표 수집용)
    DART_API_KEY: str = os.getenv("DART_API_KEY", "")

    # 한국은행 ECOS API 키
    ECOS_API_KEY: str = os.getenv("ECOS_API_KEY", "")

    # 캐시 TTL (초) — DB가 있으면 실제 만료는 길어도 무방
    CACHE_TTL_OHLCV: int = 300            # 5분
    CACHE_TTL_FUNDAMENTAL: int = 3600     # 1시간
    CACHE_TTL_MARKET: int = 900           # 15분
    CACHE_TTL_RECOMMENDATIONS: int = 1800 # 30분
    CACHE_TTL_ANALYSIS: int = 3600        # 1시간
    CACHE_TTL_MACRO: int = 21600          # 6시간
