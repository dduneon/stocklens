export class Router {
  constructor(routes) {
    this._routes = routes;  // [{ pattern: RegExp, view, name }]
    this._current = null;
    this._container = null;

    window.addEventListener('hashchange', () => this._resolve());
    window.addEventListener('popstate', () => this._resolve());
  }

  init(container) {
    this._container = container;
    this._resolve();
  }

  navigate(hash) {
    window.location.hash = hash;
  }

  _resolve() {
    const hash = window.location.hash.replace(/^#/, '') || '/';
    for (const route of this._routes) {
      const match = hash.match(route.pattern);
      if (match) {
        const params = match.groups || {};
        this._mount(route, params);
        return;
      }
    }
    // fallback: 대시보드
    this.navigate('/');
  }

  _mount(route, params) {
    if (this._current?.view?.unmount) {
      this._current.view.unmount();
    }
    this._container.innerHTML = '';
    this._current = { route, params };
    route.view.mount(this._container, params);

    // 활성 링크 표시
    document.querySelectorAll('.navbar__link').forEach(el => {
      el.classList.toggle('active', el.dataset.route === route.name);
    });
  }
}
