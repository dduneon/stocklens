import { api } from '../api.js';
import { showSpinner } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { priceBadgeHtml, formatNumber, formatPct } from '../components/priceTag.js';
import { createCandlestickChart, updateCandlestickChart } from '../charts/candlestick.js';

let _chart = null;
let _finCharts = [];      // 실적 차트 인스턴스 목록
let _investorChart = null; // 투자자 수급 차트
let _ticker = null;
let _ohlcvAll = [];

const PERIODS = [
  { label: '1개월', days: 30,  unit: 'day'   },
  { label: '3개월', days: 90,  unit: 'day'   },
  { label: '6개월', days: 180, unit: 'week'  },
  { label: '1년',   days: 365, unit: 'month' },
];
let _activePeriod = 1;

const LABEL_MAP = {
  strong_buy: { text: '강력매수', color: '#f04452' },
  buy:        { text: '매수',   color: '#3182f6' },
  watch:      { text: '관심',   color: '#f59e0b' },
  hold:       { text: '보유',   color: '#8b95a1' },
};

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
    if (_investorChart) { _investorChart.destroy(); _investorChart = null; }
    _finCharts.forEach(c => c.destroy());
    _finCharts = [];
    _ohlcvAll = [];
  },
};

// ── 데이터 로드 ───────────────────────────────────────────────────────────

async function loadDetail(root, ticker) {
  try {
    const [detail, ohlcv, fundamentals] = await Promise.all([
      api.stocks.detail(ticker),
      api.stocks.ohlcv(ticker, { days: 365 }),
      api.stocks.fundamentals(ticker, { days: 365 }),
    ]);
    _ohlcvAll = ohlcv.data || [];
    const priceByDate = Object.fromEntries(_ohlcvAll.map(d => [d.x, d.c]));
    renderDetail(root, ticker, detail, fundamentals.data || [], priceByDate);

    // 실적·분석·수급 섹션은 병렬로 비동기 로드
    loadFinancials(ticker);
    loadAnalysis(ticker);
    loadInvestorFlow(ticker);
  } catch (err) {
    root.innerHTML = '';
    showError(root, `데이터 로드 실패: ${err.message}`);
  }
}

async function loadFinancials(ticker) {
  const section = document.getElementById('financialsSection');
  if (!section) return;
  try {
    const res = await api.stocks.financials(ticker);
    renderFinancials(section, res.data || []);
  } catch (err) {
    section.innerHTML = '';
  }
}

async function loadAnalysis(ticker) {
  const section = document.getElementById('analysisSection');
  if (!section) return;
  try {
    const data = await api.analysis.stock(ticker);
    renderAnalysis(section, data);
  } catch (err) {
    section.innerHTML = `<p style="color:var(--color-text-tertiary);font-size:var(--text-sm);padding:var(--space-4)">분석 데이터를 불러올 수 없습니다.</p>`;
  }
}

async function loadInvestorFlow(ticker) {
  const section = document.getElementById('investorSection');
  if (!section) return;
  try {
    const res = await api.stocks.investorTrading(ticker, 60);
    renderInvestorFlow(section, res);
  } catch (err) {
    section.innerHTML = '';
  }
}

// ── 메인 렌더 ─────────────────────────────────────────────────────────────

function renderDetail(root, ticker, detail, fundamentals, priceByDate = {}) {
  const name       = detail.name || ticker;
  const close      = detail.close;
  const cp         = detail.change_pct;
  const fund       = detail.fundamentals || {};
  const latestFund = fundamentals[fundamentals.length - 1] || fund;
  const dir        = (cp || 0) > 0 ? 'up' : (cp || 0) < 0 ? 'down' : 'flat';

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
          ${fundamentalItem('PER',    latestFund.per ? latestFund.per.toFixed(2) + '배' : '-')}
          ${fundamentalItem('PBR',    latestFund.pbr ? latestFund.pbr.toFixed(2) + '배' : '-')}
          ${fundamentalItem('EPS',    latestFund.eps ? formatNumber(latestFund.eps) + '원' : '-')}
          ${fundamentalItem('BPS',    latestFund.bps ? formatNumber(latestFund.bps) + '원' : '-')}
          ${fundamentalItem('배당수익률', latestFund.div ? formatPct(latestFund.div) : '-')}
          ${fundamentalItem('DPS',    latestFund.dps ? formatNumber(latestFund.dps) + '원' : '-')}
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

    <!-- 실적 (비동기 로드) -->
    <div id="financialsSection" style="margin-bottom:var(--space-5)">
      <div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-4);color:var(--color-text-tertiary)">
        <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
        <span style="font-size:var(--text-sm)">실적 데이터 로딩 중...</span>
      </div>
    </div>

    <!-- 투자자 수급 (비동기 로드) -->
    <div id="investorSection" style="margin-bottom:var(--space-5)">
      <div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-4);color:var(--color-text-tertiary)">
        <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
        <span style="font-size:var(--text-sm)">투자자 수급 로딩 중...</span>
      </div>
    </div>

    <!-- 종목 분석 (비동기 로드) -->
    <div id="analysisSection" style="margin-bottom:var(--space-5)">
      <div style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-5);color:var(--color-text-tertiary)">
        <div class="spinner" style="width:16px;height:16px;border-width:2px"></div>
        <span style="font-size:var(--text-sm)">종목 분석 로딩 중...</span>
      </div>
    </div>

    <!-- 펀더멘털 추이 -->
    <div class="card card--shadow">
      <div class="card__header"><span class="card__title">펀더멘털 추이</span></div>
      <div class="card__body">
        <div class="data-table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th class="left">날짜</th>
                <th>종가</th><th>EPS</th><th>BPS</th>
                <th>PER</th><th>PBR</th><th>배당수익률</th><th>DPS</th>
              </tr>
            </thead>
            <tbody>
              ${fundamentals.slice(-20).reverse().map(f => `
                <tr>
                  <td class="left" style="color:var(--color-text-tertiary)">${f.date || '-'}</td>
                  <td>${priceByDate[f.date] ? formatNumber(priceByDate[f.date]) : '-'}</td>
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

  root.querySelector('#backBtn').addEventListener('click', () => {
    window.location.hash = '#/stocks';
  });

  const canvas = root.querySelector('#candleChart');
  const periodData = filterByPeriod(_ohlcvAll, _activePeriod);
  if (canvas) {
    _chart = createCandlestickChart(canvas, periodData, PERIODS[_activePeriod].unit);
  }

  root.querySelectorAll('#periodBtns .btn-seg').forEach(btn => {
    btn.addEventListener('click', () => {
      _activePeriod = +btn.dataset.period;
      root.querySelectorAll('#periodBtns .btn-seg').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      updateCandlestickChart(_chart, filterByPeriod(_ohlcvAll, _activePeriod), PERIODS[_activePeriod].unit);
    });
  });
}

// ── 분석 섹션 렌더 ────────────────────────────────────────────────────────

function renderAnalysis(section, d) {
  const sc     = d.scoring   || {};
  const bd     = sc.breakdown || {};
  const tp     = d.target_price || {};
  const fpe    = d.forward_pe   || {};
  const timing = d.timing       || {};
  const short  = d.shorting     || {};
  const macro  = d.macro        || {};
  const discl  = d.disclosures  || [];
  const label  = LABEL_MAP[sc.label] || { text: sc.label || '-', color: '#8b95a1' };

  section.innerHTML = `
    <!-- 스코어링 -->
    <div class="card card--shadow" style="margin-bottom:var(--space-4)">
      <div class="card__header"><span class="card__title">종목 분석</span></div>
      <div class="card__body">

        <!-- 종합 점수 -->
        <div style="display:flex;align-items:center;gap:var(--space-4);margin-bottom:var(--space-5)">
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:var(--space-3);margin-bottom:var(--space-2)">
              <span style="font-size:var(--text-3xl);font-weight:var(--font-bold);color:var(--color-brand)">${sc.score ?? '-'}</span>
              <span style="font-size:var(--text-lg);color:var(--color-text-tertiary)">/100</span>
              <span style="background:${label.color};color:#fff;font-size:var(--text-xs);font-weight:var(--font-bold);padding:3px 10px;border-radius:var(--radius-full)">${label.text}</span>
            </div>
            <div style="height:8px;background:var(--color-border-light);border-radius:4px;overflow:hidden">
              <div style="height:100%;width:${sc.score ?? 0}%;background:var(--color-brand);border-radius:4px;transition:width 0.5s"></div>
            </div>
          </div>
        </div>

        <!-- 5축 점수 -->
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:var(--space-3);margin-bottom:var(--space-5)">
          ${[
            ['가치',   bd.value],
            ['수익성', bd.profitability],
            ['성장성', bd.growth],
            ['수급',   bd.flow],
            ['기술적', bd.technical],
          ].map(([lbl, val]) => axisScore(lbl, val)).join('')}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">

          <!-- 목표가 -->
          <div style="background:var(--color-surface);border-radius:var(--radius-md);padding:var(--space-4)">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
              <span style="font-size:var(--text-sm);font-weight:var(--font-semibold)">목표가 추정</span>
              ${tp.sector ? `<span style="font-size:10px;color:var(--color-text-tertiary);background:var(--color-border-light);padding:2px 6px;border-radius:var(--radius-sm)">${tp.sector} · PER ${tp.sector_per}배</span>` : ''}
            </div>
            ${targetRow(`PER 기반 (${tp.sector_per ?? 15}배)`,        tp.per_based)}
            ${targetRow(`PBR 기반 (${tp.sector_pbr ?? 1.0}배)`,       tp.pbr_based)}
            ${targetRow('Forward PER 기반', tp.forward_per_based)}
            ${targetRow('52주 가중평균',    tp.week52_mid)}
            <div style="border-top:1px solid var(--color-border);margin:var(--space-3) 0"></div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <div>
                <span style="font-size:var(--text-sm);font-weight:var(--font-bold)">컨센서스</span>
                <div style="font-size:9px;color:var(--color-text-tertiary);margin-top:1px">Forward 35% · PER 30% · 52주 20% · PBR 15%</div>
              </div>
              <div style="text-align:right">
                <div style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-brand)">
                  ${tp.consensus ? formatNumber(tp.consensus) + '원' : '-'}
                </div>
                ${tp.upside_pct != null ? `
                  <div style="font-size:var(--text-xs);color:${tp.upside_pct >= 0 ? 'var(--color-up)' : 'var(--color-down)'}">
                    ${tp.upside_pct >= 0 ? '+' : ''}${tp.upside_pct.toFixed(1)}% 상승여력
                  </div>` : ''}
              </div>
            </div>
            ${fpe.forward_pe != null ? `
              <div style="margin-top:var(--space-3);padding-top:var(--space-3);border-top:1px solid var(--color-border)">
                <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary)">
                  <span>현재 PER</span><span>${fpe.current_per?.toFixed(1) ?? '-'}배</span>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-top:2px">
                  <span>Forward PER</span><span style="color:var(--color-brand);font-weight:var(--font-semibold)">${fpe.forward_pe?.toFixed(1) ?? '-'}배</span>
                </div>
                ${fpe.eps_growth_rate != null ? `
                  <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-tertiary);margin-top:2px">
                    <span>EPS 성장률 (${fpe.growth_method ?? '추정'})</span>
                    <span style="color:${fpe.eps_growth_rate >= 0 ? 'var(--color-up)' : 'var(--color-down)'}">
                      ${fpe.eps_growth_rate >= 0 ? '+' : ''}${fpe.eps_growth_rate.toFixed(1)}%
                    </span>
                  </div>` : ''}
                ${fpe.base_period ? `
                  <div style="font-size:9px;color:var(--color-text-tertiary);margin-top:4px;text-align:right">기준: ${fpe.base_period} · 과거 실적 기반 추정</div>` : ''}
              </div>` : ''}
          </div>

          <!-- 매수 타이밍 -->
          <div style="background:var(--color-surface);border-radius:var(--radius-md);padding:var(--space-4)">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3)">
              <span style="font-size:var(--text-sm);font-weight:var(--font-semibold)">매수 타이밍</span>
              <span style="font-size:var(--text-xs);font-weight:var(--font-bold);padding:2px 8px;border-radius:var(--radius-full);background:var(--color-brand-light);color:var(--color-brand)">
                ${timing.signal || '-'}
              </span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-2);margin-bottom:var(--space-3)">
              ${miniStat('RSI',   timing.rsi != null ? timing.rsi.toFixed(1) : '-')}
              ${miniStat('MA20',  timing.ma20 ? formatNumber(timing.ma20) : '-')}
              ${miniStat('MA60',  timing.ma60 ? formatNumber(timing.ma60) : '-')}
              ${miniStat('MA120', timing.ma120 ? formatNumber(timing.ma120) : '-')}
              ${miniStat('52주 고가', timing.hi52 ? formatNumber(timing.hi52) : '-')}
              ${miniStat('52주 저가', timing.lo52 ? formatNumber(timing.lo52) : '-')}
            </div>
            <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:var(--space-2)">
              <span>지지선</span><span style="font-weight:var(--font-semibold)">${timing.support ? formatNumber(timing.support) + '원' : '-'}</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:var(--space-3)">
              <span>저항선</span><span style="font-weight:var(--font-semibold)">${timing.resistance ? formatNumber(timing.resistance) + '원' : '-'}</span>
            </div>
            ${timing.signals?.length ? `
              <div style="display:flex;flex-direction:column;gap:4px">
                ${timing.signals.map(s => `
                  <div style="font-size:10px;color:var(--color-text-secondary);display:flex;gap:4px">
                    <span style="color:var(--color-brand);flex-shrink:0">·</span>${s}
                  </div>`).join('')}
              </div>` : ''}
          </div>
        </div>
      </div>
    </div>

    <!-- 공매도 + 거시지표 -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-bottom:var(--space-4)">

      <!-- 공매도 현황 -->
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">공매도 현황 (최근 20일)</span></div>
        <div class="card__body">
          ${short.latest_ratio != null ? `
            <div style="display:flex;align-items:baseline;gap:var(--space-2);margin-bottom:var(--space-3)">
              <span style="font-size:var(--text-2xl);font-weight:var(--font-bold)">${short.latest_ratio.toFixed(2)}%</span>
              <span style="font-size:var(--text-xs);color:var(--color-text-tertiary)">최근 공매도 비율</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:4px">
              <span>평균 비율</span><span>${short.avg_ratio?.toFixed(2) ?? '-'}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary)">
              <span>추세</span>
              <span style="font-weight:var(--font-semibold);color:${
                short.trend === '급증' || short.trend === '증가' ? 'var(--color-down)' :
                short.trend === '급감' || short.trend === '감소' ? 'var(--color-up)' : 'var(--color-text-primary)'
              }">${short.trend ?? '-'}</span>
            </div>
            ${short.trend === '급증' ? `<p style="font-size:10px;color:var(--color-down);margin-top:var(--space-2)">⚠ 공매도 급증 — 하락 압력 주의</p>` : ''}
            ${short.trend === '급감' ? `<p style="font-size:10px;color:var(--color-up);margin-top:var(--space-2)">↑ 공매도 급감 — 숏커버링 반등 가능</p>` : ''}
          ` : '<p style="font-size:var(--text-sm);color:var(--color-text-tertiary)">공매도 데이터 없음</p>'}
        </div>
      </div>

      <!-- 거시지표 참고 -->
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">거시지표 참고</span></div>
        <div class="card__body">
          ${macroRow('기준금리',   macro.latest?.base_rate, '%')}
          ${macroRow('원/달러',    macro.latest?.usd_krw, '원')}
          ${macroRow('CPI',       macro.latest?.cpi, '')}
          ${macro.notes?.length ? `
            <div style="margin-top:var(--space-3);display:flex;flex-direction:column;gap:4px">
              ${macro.notes.map(n => `
                <div style="font-size:10px;color:var(--color-text-tertiary);display:flex;gap:4px">
                  <span style="color:var(--color-brand);flex-shrink:0">·</span>${n}
                </div>`).join('')}
            </div>` : ''}
        </div>
      </div>
    </div>

    <!-- 최근 공시 -->
    ${discl.length ? `
      <div class="card card--shadow" style="margin-bottom:var(--space-4)">
        <div class="card__header"><span class="card__title">최근 공시 (최근 90일)</span></div>
        <div class="card__body" style="padding:0">
          ${discl.map(r => `
            <a href="${r.url}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:var(--space-3);padding:var(--space-3) var(--space-4);border-bottom:1px solid var(--color-border-light);text-decoration:none;color:inherit;transition:background 0.15s" onmouseover="this.style.background='var(--color-surface)'" onmouseout="this.style.background=''">
              <span style="font-size:10px;background:var(--color-brand-light);color:var(--color-brand);padding:1px 6px;border-radius:var(--radius-full);white-space:nowrap;flex-shrink:0">${r.category_label}</span>
              <span style="font-size:var(--text-sm);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.title}</span>
              <span style="font-size:var(--text-xs);color:var(--color-text-tertiary);flex-shrink:0">${r.disclosed_at}</span>
            </a>
          `).join('')}
        </div>
      </div>` : ''}
  `;
}

// ── 헬퍼 ─────────────────────────────────────────────────────────────────

function axisScore(label, score) {
  if (score == null) return `
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-bottom:3px">${label}</div>
      <div style="font-size:var(--text-sm);font-weight:var(--font-bold);color:var(--color-text-tertiary)">-</div>
    </div>`;
  const color = score >= 70 ? 'var(--color-up)' : score >= 50 ? 'var(--color-brand)' : 'var(--color-flat)';
  return `
    <div style="text-align:center">
      <div style="font-size:10px;color:var(--color-text-tertiary);margin-bottom:3px">${label}</div>
      <div style="font-size:var(--text-sm);font-weight:var(--font-bold);color:${color}">${score}</div>
      <div style="height:3px;background:var(--color-border-light);border-radius:2px;margin-top:3px">
        <div style="height:3px;width:${score}%;background:${color};border-radius:2px"></div>
      </div>
    </div>`;
}

function targetRow(label, value) {
  if (value == null) return '';
  return `
    <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:4px">
      <span>${label}</span><span style="font-weight:var(--font-semibold)">${formatNumber(value)}원</span>
    </div>`;
}

function miniStat(label, value) {
  return `
    <div style="background:var(--color-border-light);border-radius:var(--radius-md);padding:var(--space-2) var(--space-3)">
      <div style="font-size:9px;color:var(--color-text-tertiary)">${label}</div>
      <div style="font-size:var(--text-xs);font-weight:var(--font-semibold)">${value}</div>
    </div>`;
}

function macroRow(label, value, unit) {
  if (value == null) return '';
  const fmt = unit === '원' ? formatNumber(Math.round(value)) : value?.toFixed?.(2) ?? value;
  return `
    <div style="display:flex;justify-content:space-between;font-size:var(--text-xs);color:var(--color-text-secondary);margin-bottom:var(--space-2)">
      <span>${label}</span>
      <span style="font-weight:var(--font-semibold)">${fmt}${unit}</span>
    </div>`;
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
    </div>`;
}

// ── 실적 차트 ─────────────────────────────────────────────────────────────

function renderFinancials(section, rawData) {
  if (!rawData || !rawData.length) {
    section.innerHTML = '';
    return;
  }

  // 기간 오름차순 정렬
  const data = [...rawData].sort((a, b) => (a.period > b.period ? 1 : -1));

  // 레이블: "2023A" → "2023", "2024Q1" → "'24 Q1"
  const labels = data.map(d => {
    const p = d.period || '';
    if (p.endsWith('A')) return p.slice(0, 4);
    return `'${p.slice(2, 4)} ${p.slice(4)}`; // Q1/Q2 등
  });

  // 수치 변환 (조원, %)
  const tri = v => (v != null ? +(v / 1e12).toFixed(2) : null);
  const pct = (num, den) => (num != null && den ? +((num / den) * 100).toFixed(1) : null);

  const revenue    = data.map(d => tri(d.revenue));
  const opIncome   = data.map(d => tri(d.operating_income));
  const netIncome  = data.map(d => tri(d.net_income));
  const opMargin   = data.map(d => pct(d.operating_income, d.revenue));
  const netMargin  = data.map(d => pct(d.net_income, d.revenue));
  const roe        = data.map(d => pct(d.net_income, d.total_equity));
  const debtRatio  = data.map(d => pct(d.total_debt, d.total_equity));

  section.innerHTML = `
    <h2 style="font-size:var(--text-base);font-weight:var(--font-bold);color:var(--color-text-primary);margin-bottom:var(--space-4)">실적</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin-bottom:var(--space-4)">
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">매출액 &amp; 영업이익률</span></div>
        <div class="card__body"><div style="height:220px;position:relative"><canvas id="finChart1"></canvas></div></div>
      </div>
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">영업이익 &amp; 순이익</span></div>
        <div class="card__body"><div style="height:220px;position:relative"><canvas id="finChart2"></canvas></div></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">순이익률 &amp; 영업이익률</span></div>
        <div class="card__body"><div style="height:220px;position:relative"><canvas id="finChart3"></canvas></div></div>
      </div>
      <div class="card card--shadow">
        <div class="card__header"><span class="card__title">ROE &amp; 부채비율</span></div>
        <div class="card__body"><div style="height:220px;position:relative"><canvas id="finChart4"></canvas></div></div>
      </div>
    </div>
  `;

  const BASE_OPTS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top', labels: { boxWidth: 10, font: { size: 11 } } },
      tooltip: {
        backgroundColor: '#fff',
        borderColor: '#e5e8eb', borderWidth: 1,
        titleColor: '#8b95a1', bodyColor: '#191f28',
        titleFont: { size: 11 }, bodyFont: { size: 12, weight: '600' },
        padding: 10,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#8b95a1', font: { size: 11 } },
      },
    },
  };

  const yAxisLeft = (label, color) => ({
    type: 'linear', position: 'left',
    title: { display: true, text: label, color: '#8b95a1', font: { size: 10 } },
    grid: { color: '#f2f4f6' },
    ticks: { color: '#8b95a1', font: { size: 11 } },
  });
  const yAxisRight = (label) => ({
    type: 'linear', position: 'right',
    title: { display: true, text: label, color: '#8b95a1', font: { size: 10 } },
    grid: { drawOnChartArea: false },
    ticks: { color: '#8b95a1', font: { size: 11 },
      callback: v => v + '%' },
  });

  // ① 매출액(막대) + 영업이익률(선)
  _finCharts.push(new Chart(section.querySelector('#finChart1'), {
    data: {
      labels,
      datasets: [
        {
          type: 'bar', label: '매출액 (조원)', data: revenue,
          backgroundColor: 'rgba(49,130,246,0.15)', borderColor: '#3182f6',
          borderWidth: 1.5, borderRadius: 4, yAxisID: 'yLeft',
        },
        {
          type: 'line', label: '영업이익률 (%)', data: opMargin,
          borderColor: '#f59e0b', backgroundColor: 'transparent',
          borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#f59e0b',
          tension: 0.3, yAxisID: 'yRight',
        },
      ],
    },
    options: {
      ...BASE_OPTS,
      scales: {
        x: BASE_OPTS.scales.x,
        yLeft:  yAxisLeft('조원', '#3182f6'),
        yRight: yAxisRight('%'),
      },
    },
  }));

  // ② 영업이익(막대) + 순이익(막대)
  _finCharts.push(new Chart(section.querySelector('#finChart2'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: '영업이익 (조원)', data: opIncome,
          backgroundColor: 'rgba(49,130,246,0.7)', borderRadius: 4,
        },
        {
          label: '순이익 (조원)', data: netIncome,
          backgroundColor: 'rgba(16,185,129,0.7)', borderRadius: 4,
        },
      ],
    },
    options: {
      ...BASE_OPTS,
      scales: {
        x: BASE_OPTS.scales.x,
        y: {
          grid: { color: '#f2f4f6' },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v + '조' },
        },
      },
    },
  }));

  // ③ 순이익률 & 영업이익률 (선)
  _finCharts.push(new Chart(section.querySelector('#finChart3'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '영업이익률 (%)', data: opMargin,
          borderColor: '#3182f6', backgroundColor: 'rgba(49,130,246,0.06)',
          borderWidth: 2, pointRadius: 4, tension: 0.3, fill: true,
        },
        {
          label: '순이익률 (%)', data: netMargin,
          borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.06)',
          borderWidth: 2, pointRadius: 4, tension: 0.3, fill: true,
        },
      ],
    },
    options: {
      ...BASE_OPTS,
      scales: {
        x: BASE_OPTS.scales.x,
        y: {
          grid: { color: '#f2f4f6' },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v + '%' },
        },
      },
    },
  }));

  // ④ ROE(선) + 부채비율(막대)
  _finCharts.push(new Chart(section.querySelector('#finChart4'), {
    data: {
      labels,
      datasets: [
        {
          type: 'bar', label: '부채비율 (%)', data: debtRatio,
          backgroundColor: 'rgba(239,68,68,0.15)', borderColor: '#ef4444',
          borderWidth: 1.5, borderRadius: 4, yAxisID: 'yLeft',
        },
        {
          type: 'line', label: 'ROE (%)', data: roe,
          borderColor: '#8b5cf6', backgroundColor: 'transparent',
          borderWidth: 2, pointRadius: 4, tension: 0.3, yAxisID: 'yRight',
        },
      ],
    },
    options: {
      ...BASE_OPTS,
      scales: {
        x: BASE_OPTS.scales.x,
        yLeft: {
          type: 'linear', position: 'left',
          title: { display: true, text: '부채비율 (%)', color: '#8b95a1', font: { size: 10 } },
          grid: { color: '#f2f4f6' },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v + '%' },
        },
        yRight: {
          type: 'linear', position: 'right',
          title: { display: true, text: 'ROE (%)', color: '#8b95a1', font: { size: 10 } },
          grid: { drawOnChartArea: false },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v + '%' },
        },
      },
    },
  }));
}

// ── 투자자 수급 ────────────────────────────────────────────────────────────

function renderInvestorFlow(section, res) {
  const flow    = res?.flow    || [];
  const summary = res?.summary || {};
  const summaryRows = summary.rows || [];

  if (!flow.length && !summaryRows.length) {
    section.innerHTML = '';
    return;
  }

  const clr = v => v > 0 ? '#e53935' : v < 0 ? '#1e88e5' : '#8b95a1';
  const fmt = v => {
    const b = v / 1e8;
    return (v > 0 ? '+' : '') + b.toFixed(0) + '억';
  };

  // 기간 합산 요약 카드
  const BIG3 = ['기관합계','외국인합계','개인'];
  const LABELS = {'기관합계':'기관','외국인합계':'외국인','개인':'개인'};
  const summaryHtml = BIG3.map(inv => {
    const r = summaryRows.find(x => x.investor === inv);
    if (!r) return '';
    return `
      <div style="flex:1;min-width:0;padding:var(--space-4);background:var(--color-bg-secondary);border-radius:var(--radius-md);text-align:center">
        <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-bottom:4px">${LABELS[inv]}</div>
        <div style="font-size:var(--text-base);font-weight:var(--font-bold);color:${clr(r.net)}">
          ${fmt(r.net)}
        </div>
        <div style="font-size:var(--text-xs);color:var(--color-text-tertiary);margin-top:2px">
          매수 ${(r.buy/1e8).toFixed(0)}억 / 매도 ${(r.sell/1e8).toFixed(0)}억
        </div>
      </div>`;
  }).join('');

  // 일별 순매수 차트 데이터
  const labels = flow.map(d => d.date.slice(5));   // MM-DD
  const instData = flow.map(d => d.institution / 1e8);
  const foreignData = flow.map(d => d.foreign / 1e8);
  const indivData = flow.map(d => d.individual / 1e8);

  section.innerHTML = `
    <div class="card card--shadow">
      <div class="card__header">
        <span class="card__title">투자자별 수급</span>
        <span style="font-size:var(--text-xs);color:var(--color-text-tertiary)">최근 60일 · 억원 기준</span>
      </div>
      <div class="card__body" style="padding:var(--space-5)">
        <div style="display:flex;gap:var(--space-3);margin-bottom:var(--space-5)">${summaryHtml}</div>
        <div class="chart-wrap" style="height:220px"><canvas id="investorChart"></canvas></div>
      </div>
    </div>
  `;

  if (_investorChart) { _investorChart.destroy(); _investorChart = null; }
  const ctx = section.querySelector('#investorChart');
  if (!ctx) return;

  _investorChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '기관', data: instData,   backgroundColor: 'rgba(251,146,60,0.7)',  borderWidth: 0 },
        { label: '외국인', data: foreignData, backgroundColor: 'rgba(59,130,246,0.7)', borderWidth: 0 },
        { label: '개인', data: indivData,  backgroundColor: 'rgba(139,149,161,0.5)', borderWidth: 0 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top', labels: { font: { size: 11 }, boxWidth: 10 } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.raw >= 0 ? '+' : ''}${ctx.raw.toFixed(0)}억`,
          },
        },
      },
      scales: {
        x: {
          stacked: false,
          ticks: { font: { size: 10 }, maxTicksLimit: 10 },
          grid: { display: false },
        },
        y: {
          ticks: { font: { size: 10 }, callback: v => v + '억' },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
      },
    },
  });
}
