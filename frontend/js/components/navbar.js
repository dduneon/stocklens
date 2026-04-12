import { api } from '../api.js';

export function renderNavbar() {
  const nav = document.createElement('nav');
  nav.className = 'navbar';
  nav.innerHTML = `
    <a href="#/" class="navbar__logo">
      <svg class="navbar__logo-icon" viewBox="0 0 28 28" fill="none">
        <rect width="28" height="28" rx="8" fill="#3182f6"/>
        <polyline points="5,20 10,13 15,17 23,8" stroke="white" stroke-width="2.5"
          stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      </svg>
      StockLens
    </a>
    <div class="navbar__links">
      <a href="#/" class="navbar__link" data-route="dashboard">대시보드</a>
      <a href="#/stocks" class="navbar__link" data-route="stocks">종목 탐색</a>
      <a href="#/recommendations" class="navbar__link" data-route="recommendations">추천 종목</a>
      <a href="#/market-indicators" class="navbar__link" data-route="market-indicators">시장지표</a>
    </div>
    <div class="navbar__status">
      <span class="session-dot" id="sessionDot"></span>
      <span id="sessionText">KRX 연결 확인 중</span>
    </div>
  `;
  document.body.prepend(nav);
  checkSession();
}

async function checkSession() {
  const dot = document.getElementById('sessionDot');
  const txt = document.getElementById('sessionText');
  try {
    const { logged_in } = await api.session.status();
    if (logged_in) {
      dot.className = 'session-dot online';
      txt.textContent = 'KRX 연결됨';
    } else {
      dot.className = 'session-dot offline';
      txt.textContent = 'KRX 미연결';
    }
  } catch {
    dot.className = 'session-dot offline';
    txt.textContent = '서버 오프라인';
  }
}
