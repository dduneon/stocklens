import { api } from '../api.js';
import { showSpinner } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { formatNumber } from '../components/priceTag.js';

// Module-level state
let _chart = null;
let _indicatorData = null;
let _activeIndicator = 'base_rate';
let _shortingMarket = 'KOSPI';
let _rootEl = null;

export const marketIndicatorsView = {
  mount(container) {
    _activeIndicator = 'base_rate';
    _shortingMarket = 'KOSPI';
    _indicatorData = null;

    container.innerHTML = `<div class="page-content" id="mktIndRoot"></div>`;
    _rootEl = container.querySelector('#mktIndRoot');

    renderShell(_rootEl);
    loadAll();
  },
  unmount() {
    if (_chart) { _chart.destroy(); _chart = null; }
    _rootEl = null;
    _indicatorData = null;
  },
};

// ─── Shell ────────────────────────────────────────────────────────────────────

function renderShell(root) {
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">시장지표</h1>
        <p class="page-subtitle">거시경제 및 공매도 현황</p>
      </div>
    </div>

    <!-- 거시경제 지표 -->
    <section id="macroSection" style="margin-bottom:var(--space-8)">
      <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">거시경제 지표</h2>
      <div id="macroLoader"></div>
    </section>

    <!-- 공매도 현황 -->
    <section id="shortingSection">
      <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">공매도 현황</h2>
      <div id="shortingLoader"></div>
    </section>
  `;

  showSpinner(root.querySelector('#macroLoader'));
  showSpinner(root.querySelector('#shortingLoader'));
}

// ─── Data Loading ─────────────────────────────────────────────────────────────

async function loadAll() {
  await Promise.all([loadIndicators(), loadShorting()]);
}

async function loadIndicators() {
  const section = _rootEl?.querySelector('#macroSection');
  if (!section) return;

  try {
    _indicatorData = await api.analysis.indicators(365);
    renderMacroSection(section);
  } catch (err) {
    const loader = section.querySelector('#macroLoader');
    if (loader) loader.innerHTML = '';
    showError(section, `거시경제 지표 로드 실패: ${err.message}`);
  }
}

async function loadShorting() {
  const section = _rootEl?.querySelector('#shortingSection');
  if (!section) return;

  try {
    const result = await api.analysis.shorting(_shortingMarket, 20);
    renderShortingSection(section, result);
  } catch (err) {
    const loader = section.querySelector('#shortingLoader');
    if (loader) loader.innerHTML = '';
    showError(section, `공매도 데이터 로드 실패: ${err.message}`);
  }
}

// ─── Macro Section ────────────────────────────────────────────────────────────

const INDICATORS = [
  { key: 'base_rate', label: '기준금리', unit: '%', format: v => `${v}%` },
  { key: 'usd_krw',  label: '원/달러',  unit: '원', format: v => `${Number(v).toLocaleString('ko-KR')}원` },
  { key: 'cpi',      label: 'CPI',      unit: '',   format: v => `${v}` },
];

function renderMacroSection(section) {
  const { latest = {} } = _indicatorData || {};

  // Compute change (latest vs previous)
  function getChange(key) {
    const series = _indicatorData?.[key] || [];
    if (series.length < 2) return null;
    const last = series[series.length - 1]?.value;
    const prev = series[series.length - 2]?.value;
    if (last == null || prev == null) return null;
    return last - prev;
  }

  const statCardsHtml = INDICATORS.map(({ key, label, format }) => {
    const val = latest[key];
    const change = getChange(key);
    const displayVal = val != null ? format(val) : '-';
    const changeHtml = change != null
      ? `<span style="font-size:var(--text-xs);color:${change > 0 ? 'var(--color-up)' : change < 0 ? 'var(--color-down)' : 'var(--color-text-tertiary)'}">
           ${change > 0 ? '▲' : change < 0 ? '▼' : ''} ${Math.abs(change).toFixed(key === 'usd_krw' ? 1 : 2)}
         </span>`
      : '';
    const isActive = key === _activeIndicator;
    return `
      <div class="card card--shadow ind-stat-card" data-ind="${key}" style="
        flex:1;padding:var(--space-5);cursor:pointer;
        border:2px solid ${isActive ? '#3182f6' : 'var(--color-border)'};
        transition:border-color 0.15s;
      ">
        <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-bottom:var(--space-2)">${label}</div>
        <div style="font-size:var(--text-lg);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-1);font-variant-numeric:tabular-nums">${displayVal}</div>
        <div>${changeHtml}</div>
      </div>
    `;
  }).join('');

  const tabsHtml = INDICATORS.map(({ key, label }) => `
    <button class="btn-seg ind-tab ${key === _activeIndicator ? 'active' : ''}" data-ind="${key}">${label}</button>
  `).join('');

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">거시경제 지표</h2>

    <!-- Summary cards -->
    <div style="display:flex;gap:var(--space-4);margin-bottom:var(--space-5)">
      ${statCardsHtml}
    </div>

    <!-- Chart card -->
    <div class="card card--shadow">
      <div class="card__header" style="display:flex;align-items:center;justify-content:space-between">
        <div class="btn-group">${tabsHtml}</div>
        <span id="indChartLabel" style="font-size:var(--text-xs);color:var(--color-text-tertiary)">최근 1년</span>
      </div>
      <div class="card__body">
        <div style="height:280px;position:relative">
          <canvas id="indChart"></canvas>
        </div>
      </div>
    </div>
  `;

  // Bind stat card clicks
  section.querySelectorAll('.ind-stat-card').forEach(card => {
    card.addEventListener('click', () => {
      _activeIndicator = card.dataset.ind;
      updateIndicatorActive(section);
      renderIndicatorChart(section);
    });
  });

  // Bind tab clicks
  section.querySelectorAll('.ind-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      _activeIndicator = btn.dataset.ind;
      updateIndicatorActive(section);
      renderIndicatorChart(section);
    });
  });

  renderIndicatorChart(section);
}

function updateIndicatorActive(section) {
  section.querySelectorAll('.ind-stat-card').forEach(card => {
    const isActive = card.dataset.ind === _activeIndicator;
    card.style.borderColor = isActive ? '#3182f6' : 'var(--color-border)';
  });
  section.querySelectorAll('.ind-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.ind === _activeIndicator);
  });
}

function renderIndicatorChart(section) {
  const canvas = section.querySelector('#indChart');
  if (!canvas) return;

  const series = _indicatorData?.[_activeIndicator] || [];
  const ind = INDICATORS.find(i => i.key === _activeIndicator);
  const label = ind?.label || '';
  const unit = ind?.unit || '';

  const chartData = series.map(d => ({ x: d.date, y: d.value }));

  if (_chart) { _chart.destroy(); _chart = null; }

  if (!chartData.length) {
    canvas.parentElement.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:280px;color:var(--color-text-tertiary);font-size:var(--text-sm)">데이터 없음</div>
    `;
    return;
  }

  _chart = new Chart(canvas, {
    type: 'line',
    data: {
      datasets: [{
        label,
        data: chartData,
        borderColor: '#3182f6',
        backgroundColor: 'rgba(49,130,246,0.06)',
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: '#3182f6',
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#fff',
          borderColor: '#e5e8eb',
          borderWidth: 1,
          titleColor: '#8b95a1',
          bodyColor: '#191f28',
          titleFont: { size: 11 },
          bodyFont: { size: 13, weight: '600' },
          padding: 10,
          callbacks: {
            title: items => items[0]?.label || '',
            label: item => {
              const v = item.raw.y;
              if (v == null) return '-';
              if (_activeIndicator === 'usd_krw') return `${Number(v).toLocaleString('ko-KR')}${unit}`;
              return `${v}${unit}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          adapters: { date: { locale: 'ko' } },
          time: {
            displayFormats: { day: 'yy/MM/dd', month: 'yy/MM' },
          },
          grid: { color: '#e5e8eb', drawBorder: false },
          ticks: {
            color: '#8b95a1',
            font: { size: 11 },
            maxRotation: 0,
            maxTicksLimit: 8,
          },
        },
        y: {
          position: 'right',
          grid: { color: '#e5e8eb', drawBorder: false },
          ticks: {
            color: '#8b95a1',
            font: { size: 11 },
            callback: v => {
              if (_activeIndicator === 'usd_krw') return Number(v).toLocaleString('ko-KR');
              return v;
            },
          },
        },
      },
    },
  });
}

// ─── Shorting Section ─────────────────────────────────────────────────────────

function renderShortingSection(section, result) {
  const { data = [] } = result || {};

  const rowsHtml = data.length
    ? data.map((row, i) => `
        <tr>
          <td style="color:var(--color-text-tertiary);text-align:center">${i + 1}</td>
          <td style="font-size:var(--text-xs);color:var(--color-text-tertiary)">${row.ticker}</td>
          <td style="font-weight:var(--font-semibold)">${row.name || row.ticker}</td>
          <td style="text-align:right;color:#3182f6;font-weight:var(--font-semibold)">
            ${row.shorting_ratio != null ? row.shorting_ratio.toFixed(2) + '%' : '-'}
          </td>
          <td style="text-align:right;font-variant-numeric:tabular-nums">${formatNumber(row.shorting_volume)}</td>
          <td style="text-align:right;font-variant-numeric:tabular-nums;color:var(--color-text-secondary)">${formatNumber(row.total_volume)}</td>
        </tr>
      `).join('')
    : `<tr><td colspan="6" style="text-align:center;padding:var(--space-8);color:var(--color-text-tertiary);font-size:var(--text-sm)">데이터 없음</td></tr>`;

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">공매도 현황</h2>

    <div class="card card--shadow">
      <div class="card__header" style="display:flex;align-items:center;justify-content:space-between">
        <span class="card__title">공매도 비율 상위 20</span>
        <div class="btn-group">
          <button class="btn-seg short-mkt-btn ${_shortingMarket === 'KOSPI' ? 'active' : ''}" data-market="KOSPI">KOSPI</button>
          <button class="btn-seg short-mkt-btn ${_shortingMarket === 'KOSDAQ' ? 'active' : ''}" data-market="KOSDAQ">KOSDAQ</button>
        </div>
      </div>
      <div class="card__body" style="padding:0">
        <div id="shortingTableWrap" class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:40px;text-align:center">순위</th>
                <th style="width:72px">코드</th>
                <th class="left">종목명</th>
                <th style="text-align:right">공매도비율</th>
                <th style="text-align:right">공매도수량</th>
                <th style="text-align:right">총거래량</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  section.querySelectorAll('.short-mkt-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.dataset.market === _shortingMarket) return;
      _shortingMarket = btn.dataset.market;

      // Update active state immediately
      section.querySelectorAll('.short-mkt-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const wrap = section.querySelector('#shortingTableWrap');
      if (wrap) showSpinner(wrap);

      try {
        const result = await api.analysis.shorting(_shortingMarket, 20);
        renderShortingSection(section, result);
      } catch (err) {
        showError(section, `공매도 데이터 로드 실패: ${err.message}`);
      }
    });
  });
}
