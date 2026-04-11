/**
 * 한국 증권 관례: 상승 = 빨강(▲), 하락 = 파랑(▼)
 */
export function priceDirection(changePct) {
  if (changePct == null) return 'flat';
  return changePct > 0 ? 'up' : changePct < 0 ? 'down' : 'flat';
}

export function priceBadgeHtml(changePct, { showArrow = true, suffix = '%' } = {}) {
  if (changePct == null) return '<span class="badge flat">-</span>';
  const dir = priceDirection(changePct);
  const arrow = showArrow ? (dir === 'up' ? '▲' : dir === 'down' ? '▼' : '') : '';
  const sign = changePct > 0 ? '+' : '';
  return `<span class="badge ${dir}">${arrow}${sign}${Math.abs(changePct).toFixed(2)}${suffix}</span>`;
}

export function priceHtml(price, changePct) {
  const dir = priceDirection(changePct);
  return `<span class="price-${dir}">${formatNumber(price)}</span>`;
}

export function formatNumber(n, decimals = 0) {
  if (n == null || isNaN(n)) return '-';
  if (Math.abs(n) >= 1e12) return (n / 1e12).toFixed(1) + '조';
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(1) + '억';
  return n.toLocaleString('ko-KR', { maximumFractionDigits: decimals });
}

export function formatPct(n, decimals = 2) {
  if (n == null || isNaN(n)) return '-';
  return n.toFixed(decimals) + '%';
}
