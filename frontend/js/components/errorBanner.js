export function showError(container, message, prepend = true) {
  const el = document.createElement('div');
  el.className = 'error-banner';
  el.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3.5a.75.75 0 01.75.75v3a.75.75 0 01-1.5 0v-3A.75.75 0 018 4.5zm0 7a1 1 0 110-2 1 1 0 010 2z"/>
    </svg>
    <span>${message}</span>
    <button onclick="this.parentElement.remove()" style="margin-left:auto;opacity:0.6">✕</button>
  `;
  if (prepend) container.prepend(el);
  else container.append(el);
}
