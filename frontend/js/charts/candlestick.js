/**
 * Chart.js + chartjs-chart-financial 기반 캔들스틱 차트
 * 의존성: Chart.js, chartjs-chart-financial CDN 로드 필요
 */

const COLORS = {
  up:   '#f04452',
  down: '#1e6bdc',
  flat: '#8b95a1',
  volume: 'rgba(49,130,246,0.15)',
  grid: '#e5e8eb',
};

// ── 집계 ──────────────────────────────────────────────────────────────────

/**
 * 일봉 데이터를 주봉/월봉으로 집계합니다.
 * @param {Array} data - [{x, o, h, l, c, v}, ...]
 * @param {'day'|'week'|'month'} unit
 */
export function aggregateCandles(data, unit) {
  if (!data.length || unit === 'day') return data;

  const groups = new Map();

  for (const d of data) {
    const date = new Date(d.x);
    let key;

    if (unit === 'week') {
      // 해당 주의 월요일을 키로 사용
      const dow = date.getDay(); // 0=일, 1=월, ...
      const diffToMon = dow === 0 ? -6 : 1 - dow;
      const monday = new Date(date);
      monday.setDate(date.getDate() + diffToMon);
      key = monday.toISOString().slice(0, 10);
    } else {
      // 해당 월의 1일을 키로 사용
      key = d.x.slice(0, 7) + '-01';
    }

    if (!groups.has(key)) {
      groups.set(key, { x: key, o: d.o, h: d.h, l: d.l, c: d.c, v: d.v ?? 0 });
    } else {
      const g = groups.get(key);
      g.h = Math.max(g.h, d.h);
      g.l = Math.min(g.l, d.l);
      g.c = d.c;               // 마지막 거래일 종가
      g.v = (g.v ?? 0) + (d.v ?? 0);
    }
  }

  return Array.from(groups.values());
}

// ── 내부 유틸 ─────────────────────────────────────────────────────────────

function yRange(data) {
  const lows  = data.map(d => d.l).filter(v => v != null);
  const highs = data.map(d => d.h).filter(v => v != null);
  if (!lows.length) return {};
  const min = Math.min(...lows);
  const max = Math.max(...highs);
  const pad = (max - min) * 0.05;
  return { min: min - pad, max: max + pad };
}

function volumeBg(data) {
  return data.map(d =>
    d.c >= d.o ? 'rgba(240,68,82,0.2)' : 'rgba(30,107,220,0.2)'
  );
}

// ── 차트 생성 ─────────────────────────────────────────────────────────────

/**
 * @param {HTMLCanvasElement} canvas
 * @param {Array} data - [{x, o, h, l, c, v}, ...]
 * @param {'day'|'week'|'month'} unit - x축 단위
 */
export function createCandlestickChart(canvas, data, unit = 'day') {
  if (!canvas || !data || !data.length) return null;

  const agg = aggregateCandles(data, unit);
  const { min: yMin, max: yMax } = yRange(agg);

  const chart = new Chart(canvas, {
    data: {
      datasets: [
        {
          type: 'candlestick',
          label: '주가',
          data: agg.map(d => ({ x: d.x, o: d.o, h: d.h, l: d.l, c: d.c })),
          color:       { up: COLORS.up, down: COLORS.down, unchanged: COLORS.flat },
          borderColor: { up: COLORS.up, down: COLORS.down, unchanged: COLORS.flat },
          yAxisID: 'y',
          order: 1,
        },
        {
          type: 'bar',
          label: '거래량',
          data: agg.map(d => ({ x: d.x, y: d.v })),
          backgroundColor: volumeBg(agg),
          borderRadius: 2,
          yAxisID: 'yVol',
          order: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#ffffff',
          borderColor: '#e5e8eb',
          borderWidth: 1,
          titleColor: '#191f28',
          bodyColor: '#4e5968',
          padding: 12,
          callbacks: {
            label: ctx => {
              if (ctx.dataset.type === 'candlestick') {
                const d = ctx.raw;
                return [
                  `시가  ${d.o?.toLocaleString()}`,
                  `고가  ${d.h?.toLocaleString()}`,
                  `저가  ${d.l?.toLocaleString()}`,
                  `종가  ${d.c?.toLocaleString()}`,
                ];
              }
              if (ctx.dataset.label === '거래량') {
                const v = ctx.raw.y;
                if (v >= 1e8) return `거래량  ${(v / 1e8).toFixed(1)}억주`;
                if (v >= 1e4) return `거래량  ${(v / 1e4).toFixed(1)}만주`;
                return `거래량  ${v?.toLocaleString()}주`;
              }
              return '';
            },
          },
        },
      },
      scales: {
        x: {
          type: 'timeseries',
          time: {
            unit,
            displayFormats: {
              day:   'MM/dd',
              week:  'MM/dd',
              month: 'yy/MM',
            },
          },
          grid: { color: COLORS.grid, drawBorder: false },
          ticks: { color: '#8b95a1', font: { size: 11 }, maxTicksLimit: 8 },
        },
        y: {
          position: 'right',
          min: yMin,
          max: yMax,
          grid: { color: COLORS.grid, drawBorder: false },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v.toLocaleString() },
        },
        yVol: {
          position: 'left',
          grid: { display: false },
          max: ctx => {
            const vals = ctx.chart.data.datasets[1]?.data?.map(d => d.y) || [];
            return Math.max(...vals) * 5;
          },
          ticks: { display: false },
        },
      },
    },
  });

  return chart;
}

// ── 차트 업데이트 ─────────────────────────────────────────────────────────

/**
 * @param {Chart} chart
 * @param {Array} data - 필터링된 일봉 원본 데이터
 * @param {'day'|'week'|'month'} unit
 */
export function updateCandlestickChart(chart, data, unit = 'day') {
  if (!chart) return;

  const agg = aggregateCandles(data, unit);

  chart.data.datasets[0].data = agg.map(d => ({ x: d.x, o: d.o, h: d.h, l: d.l, c: d.c }));
  chart.data.datasets[1].data = agg.map(d => ({ x: d.x, y: d.v }));
  chart.data.datasets[1].backgroundColor = volumeBg(agg);

  const { min: yMin, max: yMax } = yRange(agg);
  chart.options.scales.y.min = yMin;
  chart.options.scales.y.max = yMax;
  chart.options.scales.x.time.unit = unit;

  chart.update();
}
