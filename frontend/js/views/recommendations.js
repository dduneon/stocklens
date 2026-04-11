import { api } from '../api.js';
import { store } from '../store.js';
import { showCardSkeleton } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { formatNumber, formatPct } from '../components/priceTag.js';

const LABEL_MAP = {
  strong_buy: '강력매수',
  buy:        '매수',
  watch:      '관심',
  hold:       '보유',
};

const AXES = [
  {
    key: 'value', label: '가치', weight: '25%',
    desc: 'PER·PBR 기반 저평가 여부',
    details: ['PER 10 미만 → 고득점', 'PBR 0.7 미만 → 고득점', '배당률 3%↑ 보너스', 'EPS 적자 → 감점'],
  },
  {
    key: 'profitability', label: '수익성', weight: '25%',
    desc: '재무제표 기반 수익 체력',
    details: ['ROE (순이익/자기자본)', '영업이익률 (영업이익/매출)', '부채비율 낮을수록 유리'],
  },
  {
    key: 'growth', label: '성장성', weight: '15%',
    desc: '전년 대비 실적 개선 여부',
    details: ['매출 YoY 성장률', '영업이익 YoY 성장률', '2개년 연간 재무제표 비교'],
  },
  {
    key: 'flow', label: '수급', weight: '20%',
    desc: '외국인·기관 매매 동향',
    details: ['최근 30일 외국인 순매수 일수', '최근 30일 기관 순매수 일수', '동시 매수 시 강한 신호'],
  },
  {
    key: 'technical', label: '기술적', weight: '15%',
    desc: '차트·모멘텀 지표',
    details: ['RSI 과매도(30↓) → 고득점', '단기 이동평균 상승추세', '52주 저가 근접 시 보너스', '거래량 급증 감지'],
  },
];

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
        <p class="page-subtitle">가치·수익성·성장성·수급·기술적 지표 복합 스코어링</p>
      </div>
      <div style="display:flex;gap:var(--space-2);align-items:center">
        <div class="btn-group" id="recMarketBtns">
          <button class="btn-seg active" data-market="KOSPI">KOSPI</button>
          <button class="btn-seg" data-market="KOSDAQ">KOSDAQ</button>
        </div>
      </div>
    </div>

    <!-- 스코어링 축 설명 -->
    <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:var(--space-3);margin-bottom:var(--space-6)">
      ${AXES.map(a => criterionBadge(a)).join('')}
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
  const grid   = root.querySelector('#recGrid');
  const loader = root.querySelector('#recLoader');
  if (!grid) return;

  grid.innerHTML = '';
  if (loader) showCardSkeleton(loader, 6);

  const market = store.get('market') || 'KOSPI';
  try {
    const data = await api.recommendations.list(market, 20);
    if (loader) loader.innerHTML = '';
    renderGrid(grid, data.recommendations || []);
  } catch (err) {
    if (loader) loader.innerHTML = '';
    showError(root, `추천 종목 로드 실패: ${err.message}`);
  }
}

function renderGrid(grid, recs) {
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

        <!-- 헤더: 종목명 + 순위/레이블 -->
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

        <!-- 종합 점수 바 -->
        <div class="rec-card__score-bar-wrap">
          <div class="rec-card__score-label">
            <span>종합 점수</span>
            <span style="font-weight:var(--font-bold);color:var(--color-brand)">${r.score}</span>
          </div>
          <div class="score-bar">
            <div class="score-bar__fill" style="width:${r.score}%"></div>
          </div>
        </div>

        <!-- 5축 세부 점수 -->
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:var(--space-2);margin-bottom:var(--space-4)">
          ${AXES.map(a => miniScore(a.label, bd[a.key])).join('')}
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
            <div class="metric-item__value">${formatMarketCap(r.market_cap)}</div>
          </div>
        </div>

        <!-- 기술적 시그널 태그 -->
        ${r.tech?.signals?.length ? `
          <div style="margin-top:var(--space-3);padding-top:var(--space-3);border-top:1px solid var(--color-border-light);display:flex;flex-wrap:wrap;gap:4px">
            ${r.tech.signals.map(s => `
              <span style="font-size:10px;background:var(--color-brand-light);color:var(--color-brand);padding:2px 6px;border-radius:var(--radius-full)">${s}</span>
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
  if (score == null) return `
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-bottom:3px">${label}</div>
      <div style="font-size:var(--text-sm);font-weight:var(--font-bold);color:var(--color-text-tertiary)">-</div>
    </div>
  `;
  const color = score >= 70
    ? 'var(--color-up)'
    : score >= 50
      ? 'var(--color-brand)'
      : 'var(--color-flat)';
  return `
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-bottom:3px">${label}</div>
      <div style="font-size:var(--text-sm);font-weight:var(--font-bold);color:${color}">${score}</div>
      <div style="height:3px;background:var(--color-border-light);border-radius:2px;margin-top:3px">
        <div style="height:3px;width:${score}%;background:${color};border-radius:2px;transition:width 0.3s"></div>
      </div>
    </div>
  `;
}

function criterionBadge(axis) {
  return `
    <div style="background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-md);padding:var(--space-4)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-2)">
        <span style="font-size:var(--text-sm);font-weight:var(--font-bold);color:var(--color-text-primary)">${axis.label}</span>
        <span style="font-size:var(--text-xs);font-weight:var(--font-semibold);background:var(--color-brand-light);color:var(--color-brand);padding:2px 7px;border-radius:var(--radius-full)">${axis.weight}</span>
      </div>
      <div style="font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:var(--space-2)">${axis.desc}</div>
      <ul style="margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:2px">
        ${axis.details.map(d => `
          <li style="font-size:10px;color:var(--color-text-tertiary);display:flex;align-items:flex-start;gap:4px">
            <span style="color:var(--color-brand);flex-shrink:0;margin-top:1px">·</span>${d}
          </li>
        `).join('')}
      </ul>
    </div>
  `;
}

function formatMarketCap(v) {
  if (!v) return '-';
  if (v >= 1e12) return `${(v / 1e12).toFixed(1)}조`;
  if (v >= 1e8)  return `${(v / 1e8).toFixed(0)}억`;
  return formatNumber(v);
}
