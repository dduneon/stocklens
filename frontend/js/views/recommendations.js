import { api } from '../api.js';
import { store } from '../store.js';
import { showCardSkeleton } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { priceBadgeHtml, formatNumber, formatPct } from '../components/priceTag.js';

const LABEL_MAP = {
  strong_buy: '강력매수',
  buy: '매수',
  watch: '관심',
  hold: '보유',
};

export const recommendationsView = {
  mount(container) {
    container.innerHTML = `<div class="page-content" id="recRoot"></div>`;
    const root = container.querySelector('#recRoot');
    renderShell(root);
    loadRecs(root);
  },
  unmount() {},
};

function renderShell(root) {
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">추천 종목</h1>
        <p class="page-subtitle">PER·PBR·기술적 지표 복합 스코어링</p>
      </div>
      <div style="display:flex;gap:var(--space-2);align-items:center">
        <div class="btn-group" id="recMarketBtns">
          <button class="btn-seg active" data-market="KOSPI">KOSPI</button>
          <button class="btn-seg" data-market="KOSDAQ">KOSDAQ</button>
        </div>
      </div>
    </div>

    <!-- 스코어링 기준 설명 -->
    <div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-6);flex-wrap:wrap">
      ${criterionBadge('밸류에이션 40%', 'PER·PBR 기반 저평가 여부')}
      ${criterionBadge('배당 20%', '배당수익률')}
      ${criterionBadge('기술적 40%', 'RSI·이동평균 기반 추세')}
    </div>

    <div class="rec-grid" id="recGrid"></div>
    <div id="recLoader"></div>
  `;

  root.querySelectorAll('#recMarketBtns .btn-seg').forEach(btn => {
    btn.addEventListener('click', () => {
      root.querySelectorAll('#recMarketBtns .btn-seg').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      store.set('market', btn.dataset.market);
      loadRecs(root);
    });
  });

  showCardSkeleton(root.querySelector('#recLoader'), 6);
}

async function loadRecs(root) {
  const grid = root.querySelector('#recGrid');
  const loader = root.querySelector('#recLoader');
  if (!grid) return;

  grid.innerHTML = '';
  if (loader) showCardSkeleton(loader, 6);

  const market = store.get('market') || 'KOSPI';
  try {
    const data = await api.recommendations.list(market, 20);
    if (loader) loader.innerHTML = '';
    renderGrid(root, grid, data.recommendations || []);
  } catch (err) {
    if (loader) loader.innerHTML = '';
    showError(root, `추천 종목 로드 실패: ${err.message}`);
  }
}

function renderGrid(root, grid, recs) {
  if (!recs.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <p>추천 종목 데이터를 가져올 수 없습니다</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = recs.map(r => {
    const bd = r.breakdown || {};
    return `
      <div class="rec-card" data-ticker="${r.ticker}">
        <div class="rec-card__header">
          <div>
            <div class="rec-card__name">${r.name || r.ticker}</div>
            <div class="rec-card__ticker">${r.ticker}</div>
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:var(--space-1)">
            <div class="rec-card__rank">${r.rank}</div>
            <span class="label-badge ${r.label}">${LABEL_MAP[r.label] || r.label}</span>
          </div>
        </div>

        <!-- 종합 스코어 바 -->
        <div class="rec-card__score-bar-wrap">
          <div class="rec-card__score-label">
            <span>종합 점수</span>
            <span style="font-weight:var(--font-bold);color:var(--color-brand)">${r.score}</span>
          </div>
          <div class="score-bar">
            <div class="score-bar__fill" style="width:${r.score}%"></div>
          </div>
        </div>

        <!-- 세부 점수 -->
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-2);margin-bottom:var(--space-3)">
          ${miniScore('밸류', bd.value)}
          ${miniScore('배당', bd.dividend)}
          ${miniScore('기술', bd.technical)}
        </div>

        <!-- 주요 지표 -->
        <div class="rec-card__metrics">
          <div class="metric-item">
            <div class="metric-item__label">현재가</div>
            <div class="metric-item__value">${formatNumber(r.close)}</div>
          </div>
          <div class="metric-item">
            <div class="metric-item__label">PER</div>
            <div class="metric-item__value">${r.per ? r.per.toFixed(1) : '-'}</div>
          </div>
          <div class="metric-item">
            <div class="metric-item__label">PBR</div>
            <div class="metric-item__value">${r.pbr ? r.pbr.toFixed(2) : '-'}</div>
          </div>
          <div class="metric-item">
            <div class="metric-item__label">배당률</div>
            <div class="metric-item__value">${r.div ? formatPct(r.div) : '-'}</div>
          </div>
          <div class="metric-item" style="grid-column:span 2">
            <div class="metric-item__label">시가총액</div>
            <div class="metric-item__value">${formatNumber(r.market_cap)}</div>
          </div>
        </div>

        ${r.tech?.signals?.length ? `
          <div style="margin-top:var(--space-3);padding-top:var(--space-3);border-top:1px solid var(--color-border-light)">
            ${r.tech.signals.map(s => `
              <span style="font-size:10px;background:var(--color-brand-light);color:var(--color-brand);padding:2px 6px;border-radius:var(--radius-full);margin-right:4px">${s}</span>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }).join('');

  grid.querySelectorAll('.rec-card[data-ticker]').forEach(card => {
    card.addEventListener('click', () => {
      window.location.hash = `#/stocks/${card.dataset.ticker}`;
    });
  });
}

function miniScore(label, score) {
  if (score == null) return '';
  const pct = Math.min(score, 100);
  const color = pct >= 70 ? 'var(--color-up)' : pct >= 50 ? 'var(--color-brand)' : 'var(--color-flat)';
  return `
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-bottom:3px">${label}</div>
      <div style="font-size:var(--text-sm);font-weight:var(--font-bold);color:${color}">${score}</div>
    </div>
  `;
}

function criterionBadge(title, desc) {
  return `
    <div style="background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:var(--space-3) var(--space-4)">
      <div style="font-size:var(--text-xs);font-weight:var(--font-semibold);color:var(--color-brand)">${title}</div>
      <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-top:2px">${desc}</div>
    </div>
  `;
}
