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

export function createCandlestickChart(canvas, data) {
  if (!canvas || !data || !data.length) return null;

  const labels = data.map(d => d.x);

  const candleData = data.map(d => ({
    x: d.x,
    o: d.o,
    h: d.h,
    l: d.l,
    c: d.c,
  }));

  const volumeData = data.map(d => ({
    x: d.x,
    y: d.v,
  }));

  const chart = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        {
          type: 'candlestick',
          label: '주가',
          data: candleData,
          color: {
            up: COLORS.up,
            down: COLORS.down,
            unchanged: COLORS.flat,
          },
          borderColor: {
            up: COLORS.up,
            down: COLORS.down,
            unchanged: COLORS.flat,
          },
          yAxisID: 'y',
          order: 1,
        },
        {
          type: 'bar',
          label: '거래량',
          data: volumeData,
          backgroundColor: data.map(d =>
            d.c >= d.o ? 'rgba(240,68,82,0.2)' : 'rgba(30,107,220,0.2)'
          ),
          borderRadius: 2,
          yAxisID: 'yVol',
          order: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
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
          grid: { color: COLORS.grid, drawBorder: false },
          ticks: {
            color: '#8b95a1',
            font: { size: 11 },
            maxTicksLimit: 8,
          },
        },
        y: {
          position: 'right',
          grid: { color: COLORS.grid, drawBorder: false },
          ticks: {
            color: '#8b95a1',
            font: { size: 11 },
            callback: v => v.toLocaleString(),
          },
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

export function updateCandlestickChart(chart, data) {
  if (!chart) return;
  chart.data.labels = data.map(d => d.x);
  chart.data.datasets[0].data = data.map(d => ({ x: d.x, o: d.o, h: d.h, l: d.l, c: d.c }));
  chart.data.datasets[1].data = data.map(d => ({ x: d.x, y: d.v }));
  chart.data.datasets[1].backgroundColor = data.map(d =>
    d.c >= d.o ? 'rgba(240,68,82,0.2)' : 'rgba(30,107,220,0.2)'
  );
  chart.update('none');
}
