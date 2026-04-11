import { api } from '../api.js';
import { store } from '../store.js';
import { showSpinner } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { priceBadgeHtml, formatNumber } from '../components/priceTag.js';
import { createIndexLineChart } from '../charts/lineChart.js';

let _chart = null;

export const dashboardView = {
  mount(container) {
    container.innerHTML = `
      <div class="page-content">
        <div id="dashContent"><div id="dashLoader"></div></div>
      </div>
    `;
    showSpinner(document.getElementById('dashLoader'));
    loadDashboard(container.querySelector('.page-content'));
  },
  unmount() {
    if (_chart) { _chart.destroy(); _chart = null; }
  },
};

async function loadDashboard(root) {
  const market = store.get('market') || 'KOSPI';
  try {
    const [summary, chartData] = await Promise.all([
      api.market.summary(market),
      api.market.indexChart(market, 90),
    ]);
    renderDashboard(root, summary, chartData, market);
  } catch (err) {
    root.innerHTML = '';
    showError(root, `데이터 로드 실패: ${err.message}`);
  }
}

function renderDashboard(root, summary, chartData, market) {
  const { stats = {}, top_gainers = [], top_losers = [], top_volume = [], date } = summary;

  root.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-6)">
      <div>
        <h1 class="page-title">${market} 시장</h1>
        <p class="page-subtitle">${date || ''} 기준</p>
      </div>
      <div style="display:flex;gap:var(--space-2)">
        <button class="btn btn-ghost market-btn ${market === 'KOSPI' ? 'btn-primary' : ''}" data-market="KOSPI">KOSPI</button>
        <button class="btn btn-ghost market-btn ${market === 'KOSDAQ' ? 'btn-primary' : ''}" data-market="KOSDAQ">KOSDAQ</button>
      </div>
    </div>

    <!-- 시장 통계 -->
    <div class="stat-grid" style="margin-bottom:var(--space-6)">
      <div class="stat-card">
        <div class="stat-card__label">전체 종목</div>
        <div class="stat-card__value">${stats.total?.toLocaleString() || '-'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card__label">상승</div>
        <div class="stat-card__value price-up">${stats.up?.toLocaleString() || '-'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card__label">하락</div>
        <div class="stat-card__value price-down">${stats.down?.toLocaleString() || '-'}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card__label">보합</div>
        <div class="stat-card__value price-flat">${stats.unchanged?.toLocaleString() || '-'}</div>
      </div>
    </div>

    <!-- 지수 차트 -->
    <div class="card card--shadow" style="margin-bottom:var(--space-6)">
      <div class="card__header">
        <span class="card__title">${market} 지수</span>
        <span style="font-size:var(--text-xs);color:var(--color-text-tertiary)">최근 90일</span>
      </div>
      <div class="card__body">
        <div class="chart-wrap" style="height:260px">
          <canvas id="indexChart"></canvas>
        </div>
      </div>
    </div>

    <!-- 상승/하락 상위 -->
    <div class="grid-2" style="margin-bottom:var(--space-6)">
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">상승 상위</span></div>
        <div id="gainers-body">${renderMoverRows(top_gainers)}</div>
      </div>
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">하락 상위</span></div>
        <div id="losers-body">${renderMoverRows(top_losers)}</div>
      </div>
    </div>

    <!-- 거래대금 상위 -->
    <div class="card card--shadow">
      <div class="card__header"><span class="card__title">거래대금 상위</span></div>
      <div id="volume-body">${renderVolumeRows(top_volume)}</div>
    </div>
  `;

  // 차트 렌더링
  const canvas = root.querySelector('#indexChart');
  if (canvas && chartData?.length) {
    _chart = createIndexLineChart(canvas, chartData);
  }

  // 시장 전환 버튼
  root.querySelectorAll('.market-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      store.set('market', btn.dataset.market);
      loadDashboard(root);
    });
  });

  // 종목 클릭 → 상세
  root.querySelectorAll('[data-ticker]').forEach(row => {
    row.addEventListener('click', () => {
      window.location.hash = `#/stocks/${row.dataset.ticker}`;
    });
  });
}

function renderMoverRows(stocks) {
  if (!stocks.length) return '<p style="padding:var(--space-4);color:var(--color-text-tertiary);font-size:var(--text-sm)">데이터 없음</p>';
  return stocks.map(s => `
    <div class="data-table" style="display:flex;align-items:center;padding:var(--space-3) var(--space-5);border-bottom:1px solid var(--color-border-light);cursor:pointer" data-ticker="${s.ticker}">
      <div style="flex:1">
        <div style="font-size:var(--text-sm);font-weight:var(--font-semibold)">${s.name || s.ticker}</div>
        <div style="font-size:var(--text-xs);color:var(--color-text-tertiary)">${s.ticker}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:var(--text-sm);font-variant-numeric:tabular-nums">${formatNumber(s.close)}</div>
        <div>${priceBadgeHtml(s.change_pct)}</div>
      </div>
    </div>
  `).join('');
}

function renderVolumeRows(stocks) {
  if (!stocks.length) return '<p style="padding:var(--space-4);color:var(--color-text-tertiary);font-size:var(--text-sm)">데이터 없음</p>';
  return stocks.map((s, i) => `
    <div style="display:flex;align-items:center;padding:var(--space-3) var(--space-5);border-bottom:1px solid var(--color-border-light);cursor:pointer;gap:var(--space-3)" data-ticker="${s.ticker}">
      <span style="width:20px;font-size:var(--text-xs);color:var(--color-text-tertiary);font-weight:var(--font-bold)">${i + 1}</span>
      <div style="flex:1">
        <div style="font-size:var(--text-sm);font-weight:var(--font-semibold)">${s.name || s.ticker}</div>
        <div style="font-size:var(--text-xs);color:var(--color-text-tertiary)">${s.ticker}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:var(--text-sm);color:var(--color-text-secondary)">${formatNumber(s.trading_value)}</div>
        ${priceBadgeHtml(s.change_pct)}
      </div>
    </div>
  `).join('');
}
