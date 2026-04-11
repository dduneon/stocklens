import { api } from '../api.js';
import { showSpinner } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { priceBadgeHtml, formatNumber, formatPct } from '../components/priceTag.js';
import { createCandlestickChart, updateCandlestickChart } from '../charts/candlestick.js';

let _chart = null;
let _ticker = null;
let _ohlcvAll = [];

const PERIODS = [
  { label: '1개월', days: 30 },
  { label: '3개월', days: 90 },
  { label: '6개월', days: 180 },
  { label: '1년', days: 365 },
];
let _activePeriod = 1; // 기본 3개월

export const stockDetailView = {
  mount(container, params) {
    _ticker = params.ticker;
    if (!_ticker) { window.location.hash = '#/stocks'; return; }

    container.innerHTML = `<div class="page-content" id="detailRoot"></div>`;
    const root = container.querySelector('#detailRoot');
    showSpinner(root);
    loadDetail(root, _ticker);
  },
  unmount() {
    if (_chart) { _chart.destroy(); _chart = null; }
    _ohlcvAll = [];
  },
};

async function loadDetail(root, ticker) {
  try {
    const [detail, ohlcv, fundamentals] = await Promise.all([
      api.stocks.detail(ticker),
      api.stocks.ohlcv(ticker, { days: 365 }),
      api.stocks.fundamentals(ticker, { days: 365 }),
    ]);
    _ohlcvAll = ohlcv.data || [];
    renderDetail(root, ticker, detail, fundamentals.data || []);
  } catch (err) {
    root.innerHTML = '';
    showError(root, `데이터 로드 실패: ${err.message}`);
  }
}

function renderDetail(root, ticker, detail, fundamentals) {
  const name = detail.name || ticker;
  const close = detail.close;
  const cp = detail.change_pct;
  const fund = detail.fundamentals || {};
  const latestFund = fundamentals[fundamentals.length - 1] || fund;

  const dir = (cp || 0) > 0 ? 'up' : (cp || 0) < 0 ? 'down' : 'flat';

  root.innerHTML = `
    <!-- 헤더 -->
    <div class="page-header">
      <button class="page-header__back" id="backBtn">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="10,2 4,8 10,14"/>
        </svg>
        종목 목록
      </button>
    </div>

    <!-- 종목 기본 정보 -->
    <div class="card card--shadow" style="margin-bottom:var(--space-5)">
      <div class="card__body" style="display:flex;align-items:flex-start;gap:var(--space-6)">
        <div style="flex:1">
          <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-bottom:var(--space-1)">${ticker}</div>
          <div style="font-size:var(--text-2xl);font-weight:var(--font-bold);letter-spacing:-0.03em;margin-bottom:var(--space-2)">${name}</div>
          <div style="display:flex;align-items:baseline;gap:var(--space-3)">
            <span class="price-${dir}" style="font-size:var(--text-3xl);font-weight:var(--font-bold);font-variant-numeric:tabular-nums;letter-spacing:-0.04em">${formatNumber(close)}</span>
            <span style="font-size:var(--text-lg);color:var(--color-text-secondary)">원</span>
            ${priceBadgeHtml(cp)}
          </div>
        </div>
        <div class="fundamental-grid" style="flex:2">
          ${fundamentalItem('PER', latestFund.per ? latestFund.per.toFixed(2) + '배' : '-')}
          ${fundamentalItem('PBR', latestFund.pbr ? latestFund.pbr.toFixed(2) + '배' : '-')}
          ${fundamentalItem('EPS', latestFund.eps ? formatNumber(latestFund.eps) + '원' : '-')}
          ${fundamentalItem('BPS', latestFund.bps ? formatNumber(latestFund.bps) + '원' : '-')}
          ${fundamentalItem('배당수익률', latestFund.div ? formatPct(latestFund.div) : '-')}
          ${fundamentalItem('DPS', latestFund.dps ? formatNumber(latestFund.dps) + '원' : '-')}
        </div>
      </div>
    </div>

    <!-- 차트 -->
    <div class="card card--shadow" style="margin-bottom:var(--space-5)">
      <div class="card__header">
        <span class="card__title">주가 차트</span>
        <div class="btn-group" id="periodBtns">
          ${PERIODS.map((p, i) => `
            <button class="btn-seg ${i === _activePeriod ? 'active' : ''}" data-period="${i}">${p.label}</button>
          `).join('')}
        </div>
      </div>
      <div class="card__body">
        <div class="chart-wrap" style="height:360px">
          <canvas id="candleChart"></canvas>
        </div>
      </div>
    </div>

    <!-- 펀더멘털 추이 -->
    <div class="card card--shadow">
      <div class="card__header"><span class="card__title">펀더멘털 추이 (최근 데이터)</span></div>
      <div class="card__body">
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="left">날짜</th>
                <th>종가</th>
                <th>EPS</th>
                <th>BPS</th>
                <th>PER</th>
                <th>PBR</th>
                <th>배당수익률</th>
                <th>DPS</th>
              </tr>
            </thead>
            <tbody>
              ${fundamentals.slice(-20).reverse().map(f => `
                <tr>
                  <td class="left" style="color:var(--color-text-tertiary)">${f.date || '-'}</td>
                  <td>-</td>
                  <td>${f.eps ? formatNumber(f.eps) : '-'}</td>
                  <td>${f.bps ? formatNumber(f.bps) : '-'}</td>
                  <td>${f.per ? f.per.toFixed(2) : '-'}</td>
                  <td>${f.pbr ? f.pbr.toFixed(2) : '-'}</td>
                  <td>${f.div ? formatPct(f.div) : '-'}</td>
                  <td>${f.dps ? formatNumber(f.dps) : '-'}</td>
                </tr>
              `).join('') || '<tr><td colspan="8" style="text-align:center;padding:var(--space-6);color:var(--color-text-tertiary)">데이터 없음</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // 뒤로가기
  root.querySelector('#backBtn').addEventListener('click', () => {
    window.location.hash = '#/stocks';
  });

  // 캔들차트 초기화
  const canvas = root.querySelector('#candleChart');
  const periodData = filterByPeriod(_ohlcvAll, _activePeriod);
  if (canvas) {
    _chart = createCandlestickChart(canvas, periodData);
  }

  // 기간 전환
  root.querySelectorAll('#periodBtns .btn-seg').forEach(btn => {
    btn.addEventListener('click', () => {
      _activePeriod = +btn.dataset.period;
      root.querySelectorAll('#periodBtns .btn-seg').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const data = filterByPeriod(_ohlcvAll, _activePeriod);
      updateCandlestickChart(_chart, data);
    });
  });
}

function filterByPeriod(data, periodIdx) {
  const days = PERIODS[periodIdx].days;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return data.filter(d => new Date(d.x) >= cutoff);
}

function fundamentalItem(label, value) {
  return `
    <div class="fundamental-item">
      <div class="fundamental-item__label">${label}</div>
      <div class="fundamental-item__value">${value}</div>
    </div>
  `;
}
