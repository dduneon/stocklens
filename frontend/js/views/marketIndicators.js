import { api } from '../api.js';
import { showSpinner } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { formatNumber } from '../components/priceTag.js';

// Module-level state
let _chart = null;
let _indicatorData = null;
let _activeIndicator = 'base_rate';
let _shortingMarket = 'KOSPI';
let _investorMarket = 'KOSPI';
let _investorDays   = 1;
let _sectorMarket   = 'KOSPI';
let _sectorDays     = 5;
let _rootEl = null;

export const marketIndicatorsView = {
  mount(container) {
    _activeIndicator = 'base_rate';
    _shortingMarket  = 'KOSPI';
    _investorMarket  = 'KOSPI';
    _investorDays    = 1;
    _sectorMarket    = 'KOSPI';
    _sectorDays      = 5;
    _indicatorData   = null;

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
  const secStyle = 'margin-bottom:var(--space-10)';
  const h2Style  = 'font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)';
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">시장지표</h1>
        <p class="page-subtitle">거시경제 · 투자자 수급 · 섹터 현황</p>
      </div>
    </div>

    <!-- 거시경제 지표 -->
    <section id="macroSection" style="${secStyle}">
      <h2 style="${h2Style}">거시경제 지표</h2>
      <div id="macroLoader"></div>
    </section>

    <!-- 투자자별 수급 -->
    <section id="investorSection" style="${secStyle}">
      <h2 style="${h2Style}">투자자별 수급</h2>
      <div id="investorLoader"></div>
    </section>

    <!-- 섹터 핫 -->
    <section id="sectorHeatSection" style="${secStyle}">
      <h2 style="${h2Style}">섹터 동향</h2>
      <div id="sectorHeatLoader"></div>
    </section>

    <!-- 공매도 현황 -->
    <section id="shortingSection" style="${secStyle}">
      <h2 style="${h2Style}">공매도 현황</h2>
      <div id="shortingLoader"></div>
    </section>
  `;

  ['#macroLoader','#investorLoader','#sectorHeatLoader','#shortingLoader']
    .forEach(sel => showSpinner(root.querySelector(sel)));
}

// ─── Data Loading ─────────────────────────────────────────────────────────────

async function loadAll() {
  await Promise.all([loadIndicators(), loadInvestors(), loadSectorHeat(), loadShorting()]);
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

async function loadInvestors() {
  const section = _rootEl?.querySelector('#investorSection');
  if (!section) return;
  try {
    const result = await api.analysis.investors(_investorMarket, _investorDays);
    renderInvestorSection(section, result);
  } catch (err) {
    showError(section, `투자자 수급 로드 실패: ${err.message}`);
  }
}

async function loadSectorHeat() {
  const section = _rootEl?.querySelector('#sectorHeatSection');
  if (!section) return;
  try {
    const result = await api.analysis.sectorHeat(_sectorMarket, _sectorDays);
    renderSectorHeatSection(section, result);
  } catch (err) {
    showError(section, `섹터 동향 로드 실패: ${err.message}`);
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
  const { data = [], available = true, reason = null } = result || {};

  // 수집 불가 상태: 안내 메시지 표시
  const unavailableHtml = !available
    ? `<div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-4) var(--space-5);background:var(--color-bg-secondary);border-radius:var(--radius-md);margin-bottom:var(--space-4)">
        <span style="font-size:20px">⚠️</span>
        <div>
          <div style="font-size:var(--text-sm);font-weight:var(--font-semibold);color:var(--color-text-primary)">공매도 데이터 수집 불가</div>
          <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-top:2px">${reason || 'KRX API 구조 변경으로 인해 일시적으로 수집이 중단되었습니다.'}</div>
        </div>
      </div>`
    : '';

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
    : `<tr><td colspan="6" style="text-align:center;padding:var(--space-8);color:var(--color-text-tertiary);font-size:var(--text-sm)">${!available ? '수집 불가' : '데이터 없음'}</td></tr>`;

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">공매도 현황</h2>

    ${unavailableHtml}

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

// ─── Investor Section ─────────────────────────────────────────────────────────

function renderInvestorSection(section, result) {
  const { rows = [], date = '' } = result || {};

  const fmt  = v => {
    const t = v / 1e12;
    const sign = t >= 0 ? '+' : '';
    return `${sign}${t.toFixed(2)}조`;
  };
  const clr = v => v > 0 ? '#e53935' : v < 0 ? '#1e88e5' : 'var(--color-text-secondary)';

  // 주요 3 투자자 카드
  const BIG3 = ['기관합계', '외국인합계', '개인'];
  const LABELS = { '기관합계': '기관', '외국인합계': '외국인', '개인': '개인' };
  const big3Html = BIG3.map(inv => {
    const r = rows.find(x => x.investor === inv);
    if (!r) return '';
    const netColor = clr(r.net);
    return `
      <div class="card card--shadow" style="flex:1;min-width:0">
        <div class="card__body" style="padding:var(--space-5)">
          <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-bottom:var(--space-2)">${LABELS[inv]}</div>
          <div style="font-size:var(--text-xl);font-weight:var(--font-bold);color:${netColor};font-variant-numeric:tabular-nums">
            ${fmt(r.net)}
          </div>
          <div style="display:flex;gap:var(--space-3);margin-top:var(--space-3);font-size:var(--text-xs);color:var(--color-text-tertiary)">
            <span>매수 <b style="color:var(--color-text-primary)">${(r.buy/1e12).toFixed(1)}조</b></span>
            <span>매도 <b style="color:var(--color-text-primary)">${(r.sell/1e12).toFixed(1)}조</b></span>
          </div>
        </div>
      </div>`;
  }).join('');

  // 세부 투자자 테이블
  const DETAIL = ['금융투자','보험','투신','사모','연기금 등'];
  const detailRows = rows
    .filter(r => DETAIL.includes(r.investor))
    .map(r => `
      <tr>
        <td>${r.investor}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${(r.buy/1e8).toFixed(0)}억</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${(r.sell/1e8).toFixed(0)}억</td>
        <td style="text-align:right;font-weight:var(--font-semibold);color:${clr(r.net)};font-variant-numeric:tabular-nums">
          ${r.net > 0 ? '+' : ''}${(r.net/1e8).toFixed(0)}억
        </td>
      </tr>`).join('');

  const DAYS_OPTS = [{v:1,l:'당일'},{v:5,l:'5일'},{v:20,l:'20일'}];
  const MKT_OPTS  = ['KOSPI','KOSDAQ'];

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">투자자별 수급</h2>
    <div class="card card--shadow">
      <div class="card__header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-2)">
        <span class="card__title">기관 · 외국인 · 개인 순매수</span>
        <div style="display:flex;gap:var(--space-2)">
          <div class="btn-group">
            ${MKT_OPTS.map(m => `<button class="btn-seg inv-mkt-btn ${_investorMarket===m?'active':''}" data-market="${m}">${m}</button>`).join('')}
          </div>
          <div class="btn-group">
            ${DAYS_OPTS.map(o => `<button class="btn-seg inv-days-btn ${_investorDays===o.v?'active':''}" data-days="${o.v}">${o.l}</button>`).join('')}
          </div>
        </div>
      </div>
      <div class="card__body" style="padding:var(--space-5)">
        ${date ? `<div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-bottom:var(--space-4)">${date} 기준</div>` : ''}
        <div style="display:flex;gap:var(--space-4);margin-bottom:var(--space-6)">${big3Html}</div>
        <table class="data-table">
          <thead>
            <tr>
              <th class="left">투자자</th>
              <th style="text-align:right">매수</th>
              <th style="text-align:right">매도</th>
              <th style="text-align:right">순매수</th>
            </tr>
          </thead>
          <tbody>${detailRows || '<tr><td colspan="4" style="text-align:center;padding:var(--space-6);color:var(--color-text-tertiary)">데이터 없음</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  `;

  section.querySelectorAll('.inv-mkt-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.dataset.market === _investorMarket) return;
      _investorMarket = btn.dataset.market;
      section.querySelectorAll('.inv-mkt-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      showSpinner(section.querySelector('.card__body'));
      const res = await api.analysis.investors(_investorMarket, _investorDays).catch(() => null);
      if (res) renderInvestorSection(section, res);
    });
  });
  section.querySelectorAll('.inv-days-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const d = +btn.dataset.days;
      if (d === _investorDays) return;
      _investorDays = d;
      section.querySelectorAll('.inv-days-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      showSpinner(section.querySelector('.card__body'));
      const res = await api.analysis.investors(_investorMarket, _investorDays).catch(() => null);
      if (res) renderInvestorSection(section, res);
    });
  });
}

// ─── Sector Heat Section ──────────────────────────────────────────────────────

function renderSectorHeatSection(section, result) {
  const { sectors = [], date = '', days = 5 } = result || {};

  const fmtNet = v => {
    if (!v) return '-';
    const b = v / 1e8;
    return (v > 0 ? '+' : '') + b.toFixed(0) + '억';
  };
  const clrNet = v => v > 0 ? '#e53935' : v < 0 ? '#1e88e5' : 'var(--color-text-secondary)';
  const clrChg = v => v > 0 ? '#e53935' : v < 0 ? '#1e88e5' : 'var(--color-text-secondary)';
  const fmtMkt = v => (v / 1e12).toFixed(0) + '조';

  const rowsHtml = sectors.map((s, i) => `
    <tr>
      <td style="text-align:center;color:var(--color-text-tertiary)">${i + 1}</td>
      <td style="font-weight:var(--font-semibold)">${s.krx_name}</td>
      <td style="font-size:var(--text-xs);color:var(--color-text-tertiary)">${s.sector}</td>
      <td style="text-align:right;color:${clrChg(s.avg_change)};font-weight:var(--font-semibold)">
        ${s.avg_change > 0 ? '+' : ''}${s.avg_change.toFixed(2)}%
      </td>
      <td style="text-align:right;color:${clrNet(s.foreign_net)};font-weight:var(--font-semibold);font-variant-numeric:tabular-nums">
        ${fmtNet(s.foreign_net)}
      </td>
      <td style="text-align:right;color:${clrNet(s.institution_net)};font-variant-numeric:tabular-nums">
        ${fmtNet(s.institution_net)}
      </td>
      <td style="text-align:right;color:var(--color-text-tertiary);font-size:var(--text-xs)">${fmtMkt(s.total_mktcap)}</td>
      <td style="text-align:right;color:var(--color-text-tertiary);font-size:var(--text-xs)">${s.stock_count}개</td>
    </tr>`).join('');

  const MKT_OPTS  = ['KOSPI','KOSDAQ'];
  const DAYS_OPTS = [{v:1,l:'당일'},{v:5,l:'5일'},{v:20,l:'20일'}];

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">섹터 동향</h2>
    <div class="card card--shadow">
      <div class="card__header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-2)">
        <span class="card__title">업종별 등락 · 외국인/기관 순매수</span>
        <div style="display:flex;gap:var(--space-2)">
          <div class="btn-group">
            ${MKT_OPTS.map(m => `<button class="btn-seg sec-mkt-btn ${_sectorMarket===m?'active':''}" data-market="${m}">${m}</button>`).join('')}
          </div>
          <div class="btn-group">
            ${DAYS_OPTS.map(o => `<button class="btn-seg sec-days-btn ${_sectorDays===o.v?'active':''}" data-days="${o.v}">${o.l}</button>`).join('')}
          </div>
        </div>
      </div>
      <div class="card__body" style="padding:0">
        ${date ? `<div style="padding:var(--space-3) var(--space-4);font-size:var(--text-xs);color:var(--color-text-tertiary)">${date} 기준 · 외국인 순매수 순</div>` : ''}
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:36px;text-align:center">순위</th>
                <th class="left">업종</th>
                <th class="left">섹터</th>
                <th style="text-align:right">평균등락률</th>
                <th style="text-align:right">외국인순매수</th>
                <th style="text-align:right">기관순매수</th>
                <th style="text-align:right">시가총액</th>
                <th style="text-align:right">종목수</th>
              </tr>
            </thead>
            <tbody>${rowsHtml || '<tr><td colspan="8" style="text-align:center;padding:var(--space-8);color:var(--color-text-tertiary)">데이터 없음</td></tr>'}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  section.querySelectorAll('.sec-mkt-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.dataset.market === _sectorMarket) return;
      _sectorMarket = btn.dataset.market;
      section.querySelectorAll('.sec-mkt-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      showSpinner(section.querySelector('.card__body'));
      const res = await api.analysis.sectorHeat(_sectorMarket, _sectorDays).catch(() => null);
      if (res) renderSectorHeatSection(section, res);
    });
  });
  section.querySelectorAll('.sec-days-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const d = +btn.dataset.days;
      if (d === _sectorDays) return;
      _sectorDays = d;
      section.querySelectorAll('.sec-days-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      showSpinner(section.querySelector('.card__body'));
      const res = await api.analysis.sectorHeat(_sectorMarket, _sectorDays).catch(() => null);
      if (res) renderSectorHeatSection(section, res);
    });
  });
}
