class Store {
  constructor(initial = {}) {
    this._state = { ...initial };
    this._subs = {};
  }

  get(key) { return this._state[key]; }

  set(key, value) {
    this._state[key] = value;
    (this._subs[key] || []).forEach(cb => cb(value));
  }

  subscribe(key, cb) {
    if (!this._subs[key]) this._subs[key] = [];
    this._subs[key].push(cb);
    return () => { this._subs[key] = this._subs[key].filter(f => f !== cb); };
  }
}

export const store = new Store({
  market: 'KOSPI',
  currentTicker: null,
});
