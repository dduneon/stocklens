import { api } from '../api.js';
import { store } from '../store.js';
import { showSkeleton } from '../components/loader.js';
import { showError } from '../components/errorBanner.js';
import { priceBadgeHtml, formatNumber, formatPct } from '../components/priceTag.js';

let _sortKey = 'market_cap';
let _sortAsc = false;
let _page = 1;
let _total = 0;
let _perPage = 50;
let _search = '';
let _market = 'KOSPI';
let _allData = [];
let _rootEl = null;

export const stockListView = {
  mount(container) {
    _page = 1; _search = ''; _market = store.get('market') || 'KOSPI';
    container.innerHTML = `<div class="page-content" id="stockListRoot"></div>`;
    _rootEl = container.querySelector('#stockListRoot');
    renderShell(_rootEl);
    loadData();
  },
  unmount() { _rootEl = null; },
};

function renderShell(root) {
  root.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">종목 탐색</h1>
        <p class="page-subtitle" id="stockSubtitle">불러오는 중...</p>
      </div>
      <div style="display:flex;gap:var(--space-3);align-items:center">
        <div class="btn-group">
          <button class="btn-seg ${_market === 'KOSPI' ? 'active' : ''}" data-market="KOSPI">KOSPI</button>
          <button class="btn-seg ${_market === 'KOSDAQ' ? 'active' : ''}" data-market="KOSDAQ">KOSDAQ</button>
        </div>
        <div class="search-input-wrap">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="7" cy="7" r="5"/><line x1="11" y1="11" x2="15" y2="15"/>
          </svg>
          <input class="search-input" id="stockSearch" placeholder="종목명 / 코드 검색" value="${_search}">
        </div>
      </div>
    </div>

    <div class="data-table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th class="left">종목명</th>
            <th data-sort="close">현재가</th>
            <th data-sort="change_pct">등락률</th>
            <th data-sort="volume">거래량</th>
            <th data-sort="trading_value">거래대금</th>
            <th data-sort="market_cap">시가총액</th>
            <th data-sort="per">PER</th>
            <th data-sort="pbr">PBR</th>
            <th data-sort="div">배당률</th>
          </tr>
        </thead>
        <tbody id="stockTableBody"></tbody>
      </table>
      <div id="tableLoader" style="padding:var(--space-6)"></div>
    </div>

    <div id="pagination" style="display:flex;justify-content:center;align-items:center;gap:var(--space-3);padding:var(--space-5)"></div>
  `;

  // 시장 전환
  root.querySelectorAll('.btn-seg[data-market]').forEach(btn => {
    btn.addEventListener('click', () => {
      _market = btn.dataset.market;
      store.set('market', _market);
      _page = 1;
      root.querySelectorAll('.btn-seg').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadData();
    });
  });

  // 검색
  let searchTimer;
  root.querySelector('#stockSearch').addEventListener('input', e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      _search = e.target.value.trim();
      _page = 1;
      loadData();
    }, 300);
  });

  // 정렬
  root.querySelectorAll('th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (_sortKey === key) _sortAsc = !_sortAsc;
      else { _sortKey = key; _sortAsc = false; }
      renderTable();
      renderSortIcons(root);
    });
  });

  showSkeleton(root.querySelector('#tableLoader'));
}

async function loadData() {
  const tbody = _rootEl?.querySelector('#stockTableBody');
  const loader = _rootEl?.querySelector('#tableLoader');
  if (!_rootEl) return;

  if (tbody) tbody.innerHTML = '';
  if (loader) showSkeleton(loader);

  try {
    const data = await api.stocks.list({
      market: _market,
      search: _search || undefined,
      per_page: 500,
    });
    _allData = data.stocks || [];
    _total = _allData.length;
    if (loader) loader.innerHTML = '';
    renderTable();
  } catch (err) {
    showError(_rootEl, `종목 목록 로드 실패: ${err.message}`);
    if (loader) loader.innerHTML = '';
  }
}

function renderTable() {
  if (!_rootEl) return;

  // 정렬
  const sorted = [..._allData].sort((a, b) => {
    const av = a[_sortKey] ?? -Infinity;
    const bv = b[_sortKey] ?? -Infinity;
    return _sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  // 페이지네이션
  _perPage = 50;
  const start = (_page - 1) * _perPage;
  const pageData = sorted.slice(start, start + _perPage);

  const tbody = _rootEl.querySelector('#stockTableBody');
  if (!tbody) return;

  const subtitle = _rootEl.querySelector('#stockSubtitle');
  if (subtitle) subtitle.textContent = `${_market} 전체 ${_total.toLocaleString()}개 종목`;

  if (!pageData.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="left" style="padding:var(--space-8);color:var(--color-text-tertiary);text-align:center">검색 결과가 없습니다</td></tr>`;
    return;
  }

  tbody.innerHTML = pageData.map(s => {
    const dir = (s.change_pct || 0) > 0 ? 'up' : (s.change_pct || 0) < 0 ? 'down' : 'flat';
    return `
      <tr data-ticker="${s.ticker}" style="cursor:pointer">
        <td class="left">
          <div style="font-weight:var(--font-semibold)">${s.name || '-'}</div>
          <div class="ticker-col">${s.ticker}</div>
        </td>
        <td class="price-${dir}">${formatNumber(s.close)}</td>
        <td>${priceBadgeHtml(s.change_pct)}</td>
        <td>${formatNumber(s.volume)}</td>
        <td>${formatNumber(s.trading_value)}</td>
        <td>${formatNumber(s.market_cap)}</td>
        <td>${s.per ? s.per.toFixed(1) : '-'}</td>
        <td>${s.pbr ? s.pbr.toFixed(2) : '-'}</td>
        <td>${s.div ? formatPct(s.div) : '-'}</td>
      </tr>
    `;
  }).join('');

  // 클릭 이벤트
  tbody.querySelectorAll('tr[data-ticker]').forEach(row => {
    row.addEventListener('click', () => {
      window.location.hash = `#/stocks/${row.dataset.ticker}`;
    });
  });

  renderPagination(Math.ceil(_total / _perPage));
}

function renderPagination(totalPages) {
  const el = _rootEl?.querySelector('#pagination');
  if (!el) return;

  if (totalPages <= 1) { el.innerHTML = ''; return; }

  const pages = [];
  const range = 2;
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= _page - range && i <= _page + range)) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...');
    }
  }

  el.innerHTML = pages.map(p =>
    p === '...'
      ? `<span style="color:var(--color-text-tertiary)">...</span>`
      : `<button class="btn ${p === _page ? 'btn-primary' : 'btn-ghost'}" style="min-width:36px;padding:var(--space-1)" data-page="${p}">${p}</button>`
  ).join('');

  el.querySelectorAll('[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      _page = +btn.dataset.page;
      renderTable();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  });
}

function renderSortIcons(root) {
  root.querySelectorAll('th[data-sort]').forEach(th => {
    th.classList.toggle('sorted', th.dataset.sort === _sortKey);
    const icon = th.querySelector('.sort-icon') || (() => {
      const s = document.createElement('span');
      s.className = 'sort-icon';
      th.appendChild(s);
      return s;
    })();
    icon.textContent = th.dataset.sort === _sortKey ? (_sortAsc ? '↑' : '↓') : '↕';
  });
}
