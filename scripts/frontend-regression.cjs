// Run: node scripts/frontend-regression.cjs <directory containing react-test-renderer>
// The renderer is an optional test-only dependency; production map/network calls are mocked.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Module = require('node:module');
const frontend = path.resolve(__dirname, '../src/frontend');
const frontendRequire = Module.createRequire(path.join(frontend, 'package.json'));
const React = frontendRequire('react');
const originalLoad = Module._load;
Module._load = function (name, ...args) {
  if (name === 'react') return React;
  return originalLoad.call(this, name, ...args);
};
const rendererRequire = Module.createRequire(path.resolve(process.argv[2], 'package.json'));
const { create, act } = rendererRequire('react-test-renderer');
const ts = frontendRequire('typescript');
global.IS_REACT_ACT_ENVIRONMENT = true;
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const windowEvents = new EventTarget();
global.window = windowEvents;
window.location = { pathname: '/search', search: '?dish=pho' };
global.document = new EventTarget();
Object.defineProperty(document, 'cookie', { get() { throw new Error('HttpOnly authentication must not read document.cookie'); } });
const storage = new Map();
global.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
};
let mounts = 0, unmounts = 0, dialogs = 0;
let mapInstances = 0, mapRemovals = 0, lastMap;
global.ResizeObserver = class { observe() {} disconnect() {} };
const mapbox = {
  Map: class {
    constructor() {
      mapInstances++; lastMap = this; this.sources = {};
      this.scrollZoom = { enable() {} };
    }
    on(event, callback) { if (event === 'load') queueMicrotask(callback); }
    addControl() {}
    addSource(id, value) { this.sources[id] = { data: value.data, setData(data) { this.data = data; } }; }
    getSource(id) { return this.sources[id]; }
    addLayer() {}
    getLayer() { return null; }
    loadImage() {}
    fitBounds() {}
    resize() {}
    remove() { mapRemovals++; }
  },
  NavigationControl: class {},
  LngLatBounds: class {
    constructor() { this.empty = true; }
    extend() { this.empty = false; }
    isEmpty() { return this.empty; }
  },
};
function MapPanel(props) {
  React.useEffect(() => { mounts++; return () => { unmounts++; }; }, []);
  return React.createElement('test-map', props);
}
class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}
const requests = [];
let signedIn = true;
const api = {
  ApiError,
  me: async () => { if (!signedIn) throw new ApiError(401, 'unauthenticated', 'Login required'); return { id: 'test-user' }; },
  newSearch: (body, signal) => new Promise((resolve, reject) => requests.push({ body, signal, resolve, reject })),
};
const dictionary = {
  lang: 'en', price: value => `${value} VND`,
  search: { empty: 'No matching restaurants', count: n => `${n} results`, offline: 'Offline', error: 'Search failed', viewList: 'List', viewMap: 'Map' },
  chat: { empty: 'No results', clarify: 'Clarify' }, auth: { login: 'Log in', register: 'Register' }, errors: { unauthenticated: 'Log in', unknown: 'Failed' },
};
const componentCache = new Map();
function load(filename) {
  filename = path.resolve(filename);
  if (componentCache.has(filename)) return componentCache.get(filename).exports;
  const module = { exports: {} };
  componentCache.set(filename, module);
  const source = fs.readFileSync(filename, 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
    esModuleInterop: true,
  } }).outputText;
  function localRequire(name) {
    if (name === 'react') return React;
    if (name === 'mapbox-gl') return mapbox;
    if (name.endsWith('.css')) return {};
    if (name === '@/lib/api') return api;
    if (name.endsWith('/SearchPreferenceProvider')) return { useSearchPreferences: () => searchModel };
    if (name.endsWith('/SearchLocationProvider')) return { useSearchLocation: () => ({ selectedSearchLocation: { lat: 10.77, lon: 106.7, shortLabel: 'Test area' }, ready: true, openLocation() {} }) };
    if (name.endsWith('/LangProvider')) return { useT: () => dictionary };
    if (name === './MapPanel') return { __esModule: true, default: MapPanel };
    if (name === 'next/form') return { __esModule: true, default: props => React.createElement('form', { ...props, method: 'get' }) };
    if (name === 'next/image' || name === 'next/link') return { __esModule: true, default: props => React.createElement(name === 'next/image' ? 'img' : 'a', props) };
    if (name.startsWith('.') || name.startsWith('@/')) {
      const target = name.startsWith('@/') ? path.join(frontend, name.slice(2)) : path.resolve(path.dirname(filename), name);
      if (target.endsWith('.json') && fs.existsSync(target)) return JSON.parse(fs.readFileSync(target, 'utf8'));
      for (const ext of ['.tsx', '.ts']) if (fs.existsSync(target + ext)) return load(target + ext);
    }
    return frontendRequire(name);
  }
  vm.runInThisContext(`(function(require,module,exports){${compiled}\n})`, { filename })(localRequire, module, module.exports);
  return module.exports;
}
const SearchResult = load(path.join(frontend, 'components/search/SearchResult.tsx')).default;
const FavoriteButton = load(path.join(frontend, 'components/common/FavoriteButton.tsx')).default;
let searchModel = { preferences: { food: [], cuisine: [], hard_constraints: {}, semantic_preferences: [], negative_preferences: [], soft_preferences: {} }, edit() {}, data: null, status: 'idle', error: null, origin: { lat: 10.77, lon: 106.7 }, dirty: false, runSearch: async () => {} };
const props = { dish: 'pho', maxPrice: '50000', styles: [], kind: '', radius: '5', location: { lat: 10.77, lon: 106.7 } };
function response(id) {
  return { results: id ? [{ rank: 1, restaurant_id: id, restaurant_name: id, dish_name: 'pho', location: { lat: 10.77, lon: 106.7 }, price_vnd: 30000, space_tags: [] }] : [], warnings: [], map_places: [] };
}
async function main() {
  let tree;
  await act(async () => { tree = create(React.createElement(React.StrictMode, null, React.createElement(SearchResult))); });
  assert.equal(mounts, 0, 'Welcome must not initialize or download a map');
  assert.equal(tree.root.findByProps({ id: 'search-welcome-title' }).type, 'h1');
  for (const name of ['dish', 'maxPrice']) assert.equal(tree.root.findAllByProps({ name }).length, 1);
  const render = patch => { searchModel = { ...searchModel, ...patch }; tree.update(React.createElement(React.StrictMode, null, React.createElement(SearchResult))); };
  const mapIds = () => tree.root.findByType('test-map').props.places.map(place => place.id);
  await act(async () => render({ status: 'loading' }));
  const baseline = { mounts, unmounts };
  await act(async () => render({ status: 'idle', data: response('first') }));
  assert.deepEqual(mapIds(), ['first']);
  await act(async () => render({ status: 'loading' }));
  assert.deepEqual(mapIds(), ['first']);
  await act(async () => render({ status: 'idle', data: response('latest') }));
  assert.deepEqual(mapIds(), ['latest']);
  await act(async () => render({ data: response(null) }));
  assert.deepEqual(mapIds(), []);
  await act(async () => render({ error: new ApiError(503, 'unavailable', 'Offline') }));
  assert.ok(tree.root.findByProps({ role: 'alert' }).findAllByType('p')[0].children.includes('Offline'));
  await act(async () => render({ error: null, data: null }));
  assert.equal(mounts, baseline.mounts);
  assert.equal(unmounts, baseline.unmounts, 'Map persists across loading, success, empty, error and reset');
  await act(async () => tree.unmount());
  console.log('PASS search projection: shared results, persistent map, welcome, loading, empty/error and reset');

  let favorite;
  await act(async () => { favorite = create(React.createElement(FavoriteButton, { restaurant: { restaurant_id: 'saved', restaurant_name: 'Saved', dish_name: null, address: null, image_url: null, price_vnd: null } }), {
    createNodeMock: el => el.type === 'dialog' ? { showModal() { dialogs++; }, close() {} } : null,
  }); });
  const click = () => favorite.root.findAllByType('button')[0].props.onClick({ stopPropagation() {} });
  await act(async () => { click(); });
  assert.equal(JSON.parse(storage.get('tastly.saved-restaurants.v1')).length, 1);
  assert.equal(dialogs, 0, 'Valid HttpOnly session can save without a login dialog');
  await act(async () => { click(); });
  assert.equal(JSON.parse(storage.get('tastly.saved-restaurants.v1')).length, 0);
  signedIn = false;
  await act(async () => { click(); });
  assert.equal(dialogs, 1, 'Expired session opens login dialog');
  assert.ok(favorite.root.findAllByType('a')[0].props.href.includes('next=%2Fsearch%3Fdish%3Dpho'));
  await act(async () => { favorite.unmount(); });
  console.log('PASS favorites: HttpOnly login, save/remove, expired session and return-to-search URL');

  const MapboxView = load(path.join(frontend, 'components/search/MapboxView.tsx')).default;
  let engine;
  const mapProps = { places: [{ id: 'one', lat: 10.77, lon: 106.7, name: 'One' }], token: 'test-token', activeId: null, selectedId: null, onSelect() {} };
  await act(async () => { engine = create(React.createElement(MapboxView, mapProps), { createNodeMock: () => ({}) }); });
  assert.equal(mapInstances, 1);
  assert.equal(lastMap.sources.places.data.features[0].id, 'one');
  await act(async () => { engine.update(React.createElement(MapboxView, { ...mapProps, places: [{ id: 'two', lat: 10.78, lon: 106.7, name: 'Two' }] })); });
  assert.equal(lastMap.sources.places.data.features[0].id, 'two');
  await act(async () => { engine.update(React.createElement(MapboxView, { ...mapProps, places: [] })); });
  assert.equal(lastMap.sources.places.data.features.length, 0);
  assert.equal(mapInstances, 1, 'Mapbox updates GeoJSON without constructing another map');
  assert.equal(mapRemovals, 0);
  await act(async () => { engine.unmount(); });
  assert.equal(mapRemovals, 1);
  console.log('PASS MapboxView: one map instance, updated/cleared GeoJSON, cleanup only on page unmount');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { Module._load = originalLoad; });
