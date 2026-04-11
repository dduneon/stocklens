export function showSkeleton(container, rows = 8, cols = 6) {
  const html = Array.from({ length: rows }, () => `
    <div class="skeleton-row">
      <div class="skeleton" style="width:120px;height:14px;flex-shrink:0"></div>
      ${Array.from({ length: cols - 1 }, () =>
        `<div class="skeleton" style="width:${50 + Math.random() * 50 | 0}px;height:14px;margin-left:auto"></div>`
      ).join('')}
    </div>
  `).join('');
  container.innerHTML = `<div style="border:1px solid var(--color-border);border-radius:var(--radius-lg);overflow:hidden">${html}</div>`;
}

export function showCardSkeleton(container, count = 6) {
  container.innerHTML = Array.from({ length: count }, () => `
    <div class="card" style="padding:var(--space-5)">
      <div class="skeleton" style="width:60%;height:16px;margin-bottom:var(--space-3)"></div>
      <div class="skeleton" style="width:40%;height:28px;margin-bottom:var(--space-2)"></div>
      <div class="skeleton" style="width:80%;height:12px"></div>
    </div>
  `).join('');
}

export function showSpinner(container) {
  container.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;padding:80px">
      <div style="
        width:32px;height:32px;
        border:3px solid var(--color-border);
        border-top-color:var(--color-brand);
        border-radius:50%;
        animation:spin 0.7s linear infinite
      "></div>
    </div>
    <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
  `;
}
