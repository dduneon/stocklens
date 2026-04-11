"""KRX 로그인 세션 관리.

pykrx 내부 세션(webio._session)을 직접 활용하여 로그인 쿠키를
공유합니다. 스코프를 잃지 않도록 모듈 레벨에서 _session 참조를 고정합니다.
"""
import logging
import threading
import requests

logger = logging.getLogger(__name__)

_LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
_LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
_LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# pykrx 내부 세션을 가져오거나, 없으면 새 세션 생성
def _resolve_pykrx_session() -> requests.Session:
    """pykrx webio 모듈에서 _session 객체를 찾아 반환.

    버전마다 경로가 다를 수 있으므로 여러 경로를 시도합니다.
    """
    candidates = [
        "pykrx.website.comm.webio",
        "pykrx.website.web_utils",
        "pykrx.website.krx.web_utils",
    ]
    for path in candidates:
        try:
            mod = __import__(path, fromlist=["_session"])
            sess = getattr(mod, "_session", None)
            if isinstance(sess, requests.Session):
                logger.info("pykrx 세션 획득: %s._session", path)
                return sess
        except (ImportError, AttributeError):
            continue

    logger.warning("pykrx 내부 세션을 찾을 수 없어 새 세션을 생성합니다.")
    return requests.Session()


# pykrx와 공유하는 전역 단일 세션 — 이 모듈이 임포트될 때 한 번만 고정
_session: requests.Session = _resolve_pykrx_session()

_logged_in: bool = False
_login_lock = threading.Lock()
_refresh_timer: threading.Timer | None = None

# KRX 세션 유효 시간(초). 만료 5분 전에 재갱신
_SESSION_TTL = 6 * 3600
_REFRESH_BEFORE = 5 * 60


def login_krx(login_id: str, login_pw: str) -> bool:
    """KRX data.krx.co.kr 로그인 후 JSESSIONID 쿠키를 갱신합니다.

    로그인 흐름:
      1. GET MDCCOMS001.cmd  → 초기 JSESSIONID 발급
      2. GET login.jsp       → iframe 세션 초기화
      3. POST MDCCOMS001D1.cmd → 실제 로그인
      4. CD011(중복 로그인) → skipDup=Y 재전송
    """
    global _logged_in, _refresh_timer

    with _login_lock:
        try:
            _session.get(_LOGIN_PAGE, headers={"User-Agent": _UA}, timeout=15)
            _session.get(
                _LOGIN_JSP,
                headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE},
                timeout=15,
            )

            payload = {
                "mbrNm": "", "telNo": "", "di": "", "certType": "",
                "mbrId": login_id, "pw": login_pw,
            }
            headers = {"User-Agent": _UA, "Referer": _LOGIN_PAGE}

            resp = _session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
            data = resp.json()
            error_code = data.get("_error_code", "")

            if error_code == "CD011":
                payload["skipDup"] = "Y"
                resp = _session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
                data = resp.json()
                error_code = data.get("_error_code", "")

            _logged_in = error_code == "CD001"

            if _logged_in:
                logger.info("KRX 로그인 성공")
                _sync_cookies_to_other_pykrx_sessions()
                _schedule_refresh(login_id, login_pw)
            else:
                logger.error("KRX 로그인 실패: error_code=%s, msg=%s",
                             error_code, data.get("_error_msg", ""))

            return _logged_in

        except Exception as exc:
            logger.error("KRX 로그인 중 예외 발생: %s", exc)
            return False


def _sync_cookies_to_other_pykrx_sessions() -> None:
    """_session이 pykrx의 기본 세션과 다른 객체인 경우 쿠키를 복사합니다."""
    candidates = [
        "pykrx.website.comm.webio",
        "pykrx.website.web_utils",
        "pykrx.website.krx.web_utils",
    ]
    for path in candidates:
        try:
            mod = __import__(path, fromlist=["_session"])
            other = getattr(mod, "_session", None)
            if other is not None and other is not _session:
                for cookie in _session.cookies:
                    other.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
                logger.debug("쿠키 동기화 완료: %s", path)
        except (ImportError, AttributeError):
            continue


def _schedule_refresh(login_id: str, login_pw: str) -> None:
    global _refresh_timer
    if _refresh_timer is not None:
        _refresh_timer.cancel()

    interval = _SESSION_TTL - _REFRESH_BEFORE
    _refresh_timer = threading.Timer(
        interval,
        lambda: login_krx(login_id, login_pw),
    )
    _refresh_timer.daemon = True
    _refresh_timer.start()
    logger.info("세션 재갱신 예약: %.0f초 후", interval)


def is_logged_in() -> bool:
    return _logged_in
