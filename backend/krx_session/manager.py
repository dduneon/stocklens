"""KRX 로그인 세션 관리.

pykrx webio.Get.read / Post.read 를 monkey-patch하여
로그인 쿠키가 담긴 세션을 모든 pykrx 요청에 주입합니다.
"""
import logging
import threading
import requests

logger = logging.getLogger(__name__)

_LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
_LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
_LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 로그인 쿠키를 보관하는 전용 세션 (pykrx와 독립)
_session: requests.Session = requests.Session()

_logged_in: bool = False
_login_lock = threading.Lock()
_refresh_timer: threading.Timer | None = None

_SESSION_TTL    = 6 * 3600   # KRX 세션 유효 시간(초)
_REFRESH_BEFORE = 5 * 60     # 만료 5분 전 재갱신


# ── pykrx monkey-patch ────────────────────────────────────────────────────

def _apply_session_patch() -> None:
    """pykrx webio.Get / Post 의 read() 를 우리 세션으로 교체."""
    try:
        from pykrx.website.comm import webio

        def patched_get_read(self, **params):
            return _session.get(self.url, headers=self.headers, params=params)

        def patched_post_read(self, **params):
            return _session.post(self.url, headers=self.headers, data=params)

        webio.Get.read  = patched_get_read
        webio.Post.read = patched_post_read
        logger.info("pykrx webio 세션 패치 완료")
    except Exception as e:
        logger.error("pykrx webio 패치 실패: %s", e)


# ── 로그인 ────────────────────────────────────────────────────────────────

def login_krx(login_id: str, login_pw: str) -> bool:
    """KRX 로그인 후 세션 쿠키 갱신 및 pykrx에 주입.

    흐름:
      1. GET MDCCOMS001.cmd  → 초기 JSESSIONID
      2. GET login.jsp       → iframe 세션 초기화
      3. POST MDCCOMS001D1.cmd → 실제 로그인
      4. CD011(중복) → skipDup=Y 재전송
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
                # 로그인 직후 pykrx에 세션 주입
                _apply_session_patch()
                _schedule_refresh(login_id, login_pw)
            else:
                logger.error(
                    "KRX 로그인 실패: error_code=%s, msg=%s",
                    error_code, data.get("_error_msg", ""),
                )

            return _logged_in

        except Exception as exc:
            logger.error("KRX 로그인 중 예외: %s", exc)
            return False


def _schedule_refresh(login_id: str, login_pw: str) -> None:
    global _refresh_timer
    if _refresh_timer is not None:
        _refresh_timer.cancel()

    interval = _SESSION_TTL - _REFRESH_BEFORE
    _refresh_timer = threading.Timer(interval, lambda: login_krx(login_id, login_pw))
    _refresh_timer.daemon = True
    _refresh_timer.start()
    logger.info("세션 재갱신 예약: %.0f초 후", interval)


def is_logged_in() -> bool:
    return _logged_in
