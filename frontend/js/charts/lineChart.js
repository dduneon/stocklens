export function createIndexLineChart(canvas, data) {
  if (!canvas || !data?.length) return null;

  const labels = data.map(d => d.x);
  const closes = data.map(d => d.c);
  const last = closes[closes.length - 1];
  const first = closes[0];
  const isUp = last >= first;

  const color = isUp ? '#f04452' : '#1e6bdc';
  const bgColor = isUp ? 'rgba(240,68,82,0.08)' : 'rgba(30,107,220,0.08)';

  return new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: closes,
        borderColor: color,
        backgroundColor: bgColor,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
        tension: 0.3,
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
          titleColor: '#191f28',
          bodyColor: '#4e5968',
          callbacks: {
            label: ctx => `${ctx.parsed.y.toLocaleString()}pt`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#8b95a1', font: { size: 11 }, maxTicksLimit: 6 },
        },
        y: {
          position: 'right',
          grid: { color: '#e5e8eb', drawBorder: false },
          ticks: { color: '#8b95a1', font: { size: 11 }, callback: v => v.toLocaleString() },
        },
      },
    },
  });
}
