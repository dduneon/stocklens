const BASE = '/api';

async function apiFetch(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v);
  });

  let lastError;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url.toString());
      if (res.status === 503) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        lastError = new Error('서버가 일시적으로 응답하지 않습니다.');
        continue;
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      return res.json();
    } catch (e) {
      if (e.message !== '서버가 일시적으로 응답하지 않습니다.') throw e;
      lastError = e;
    }
  }
  throw lastError;
}

export const api = {
  market: {
    summary:    (market = 'KOSPI') => apiFetch('/market/summary', { market }),
    indexChart: (market = 'KOSPI', days = 90) => apiFetch('/market/index-chart', { market, days }),
  },
  stocks: {
    list:            (params = {}) => apiFetch('/stocks/', params),
    detail:          (ticker) => apiFetch(`/stocks/${ticker}`),
    ohlcv:           (ticker, params = {}) => apiFetch(`/stocks/${ticker}/ohlcv`, params),
    fundamentals:    (ticker, params = {}) => apiFetch(`/stocks/${ticker}/fundamentals`, params),
    financials:      (ticker) => apiFetch(`/stocks/${ticker}/financials`),
    investorTrading: (ticker, days = 60) => apiFetch(`/stocks/${ticker}/investor-trading`, { days }),
  },
  analysis: {
    stock:       (ticker) => apiFetch(`/analysis/stocks/${ticker}`),
    indicators:  (days = 365) => apiFetch('/analysis/market/indicators', { days }),
    shorting:    (market = 'KOSPI', top_n = 20) => apiFetch('/analysis/market/shorting', { market, top_n }),
    investors:   (market = 'KOSPI', days = 1) => apiFetch('/analysis/market/investors', { market, days }),
    sectorHeat:  (market = 'KOSPI', days = 5) => apiFetch('/analysis/market/sector-heat', { market, days }),
  },
  recommendations: {
    list: (market = 'KOSPI', top_n = 20) => apiFetch('/recommendations/', { market, top_n }),
  },
  session: {
    status: () => apiFetch('/session/status'),
  },
};
