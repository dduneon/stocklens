import { Router } from './router.js';
import { renderNavbar } from './components/navbar.js';
import { dashboardView } from './views/dashboard.js';
import { stockListView } from './views/stockList.js';
import { stockDetailView } from './views/stockDetail.js';
import { recommendationsView } from './views/recommendations.js';
import { marketIndicatorsView } from './views/marketIndicators.js';

const router = new Router([
  { pattern: /^\/$/, name: 'dashboard', view: dashboardView },
  { pattern: /^\/stocks$/, name: 'stocks', view: stockListView },
  { pattern: /^\/stocks\/(?<ticker>[A-Z0-9]+)$/, name: 'stock-detail', view: stockDetailView },
  { pattern: /^\/recommendations$/, name: 'recommendations', view: recommendationsView },
  { pattern: /^\/market-indicators$/, name: 'market-indicators', view: marketIndicatorsView },
]);

function init() {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="main-layout"><div id="view-container" style="flex:1;overflow:auto"></div></div>';

  renderNavbar();

  const container = document.getElementById('view-container');
  router.init(container);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
