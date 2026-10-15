// Run: node scripts/location-regression.cjs <directory containing react-test-renderer>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Module = require('node:module');
const frontend = path.resolve(__dirname, '../src/frontend');
const req = Module.createRequire(path.join(frontend, 'package.json'));
const React = req('react');
const originalLoad = Module._load;
Module._load = function(name, ...args) { return name === 'react' ? React : originalLoad.call(this, name, ...args); };
const { act, create } = Module.createRequire(path.resolve(process.argv[2], 'package.json'))('react-test-renderer');
const ts = req('typescript');
global.IS_REACT_ACT_ENVIRONMENT = true;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const storage = new Map();
global.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
global.document = Object.assign(new EventTarget(), { cookie: '' });
global.window = { matchMedia: () => ({ matches: false }) };
const gps = [], searches = [], lookups = [], chatRequests = [];
Object.defineProperty(global, 'navigator', { configurable: true, value: { geolocation: { getCurrentPosition: (ok, fail, options) => gps.push({ ok, fail, options }) } } });
const api = {
  ApiError: class extends Error {},
  newSearch: (body, signal) => new Promise(resolve => searches.push({ body, signal, resolve })),
  searchDishes: async body => { chatRequests.push(body); return { results: [], clarification_required: false }; },
};
const dictionary = { searchBar: { dish: 'Dish', maxPrice: 'Price', submit: 'Search', categories: 'Categories' }, lang: 'en', price: String, search: { count: String }, chat: { empty: 'Empty', found: String, thinking: 'Thinking', placeholder: 'Ask', send: 'Send', open: 'Chat', close: 'Close' } };
const cache = new Map();
function load(filename) {
  filename = path.resolve(filename);
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} }; cache.set(filename, module);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const localRequire = name => {
    if (name === 'react') return React;
    if (name === '@/lib/api') return api;
    if (name.endsWith('/LangProvider')) return { useT: () => dictionary, useLang: () => 'en' };
    if (name === './ResultExplorer') return { __esModule: true, default: props => React.createElement('result-explorer', props) };
    if (name === './SearchWelcome' || name === './SearchLoading') return { __esModule: true, default: () => null };
    if (name === 'next/image') return { __esModule: true, default: props => React.createElement('img', props) };
    if (name === 'next/link') return { __esModule: true, default: props => React.createElement('a', props) };
    if (name === 'next/form') return { __esModule: true, default: props => React.createElement('form', props) };
    if (name.startsWith('.') || name.startsWith('@/')) {
      const target = name.startsWith('@/') ? path.join(frontend, name.slice(2)) : path.resolve(path.dirname(filename), name);
      if (target.endsWith('.json') && fs.existsSync(target)) return JSON.parse(fs.readFileSync(target, 'utf8'));
      for (const ext of ['.tsx', '.ts']) if (fs.existsSync(target + ext)) return load(target + ext);
    }
    return req(name);
  };
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, { filename })(localRequire, module, module.exports);
  return module.exports;
}
const locations = load(path.join(frontend, 'lib/search-location.ts'));
locations.geocodeLocation = (query, signal) => new Promise(resolve => lookups.push({ query, signal, resolve }));
const { SearchLocationProvider: Provider, useSearchLocation } = load(path.join(frontend, 'components/location/SearchLocationProvider.tsx'));
const LocationPicker = load(path.join(frontend, 'components/layout/LocationPicker.tsx')).default;
dictionary.chat = load(path.join(frontend, 'lib/locales/en.ts')).en.chat;
let state;
function Probe() { state = useSearchLocation(); return null; }
const manual = { lat: 10.734, lon: 106.7216, address: 'Test address', shortLabel: 'Test area', source: 'manual' };
const second = { ...manual, lat: 21.0285, lon: 105.8542, address: 'Another address', shortLabel: 'Another area' };
const props = { enabled: true, intentKey: 'first', dish: 'pho', maxPrice: '50000', styles: [], kind: '', radius: '5' };
function app(children, initialLocation) { return React.createElement(React.StrictMode, null, React.createElement(Provider, { initialLocation }, React.createElement(Probe), children)); }
async function mount(children, initial) { let tree; await act(async () => { tree = create(app(children, initial), { createNodeMock: element => element.type === 'dialog' ? { open: false, showModal() { this.open = true; }, close() { this.open = false; } } : element.type === 'input' || element.type === 'button' ? { focus() {} } : null }); }); return tree; }
const unmount = async tree => act(async () => tree.unmount());
async function main() {
  for (const value of [null, {}, { ...manual, lat: NaN }, { ...manual, lon: 200 }, { ...manual, source: 'fake' }, { ...manual, address: '' }]) assert.equal(locations.isSearchLocation(value), false);
  assert.equal(locations.parseLocationCookie('%invalid'), undefined);
  assert.equal(locations.parseLocationCookie('current||'), undefined);
  assert.equal(locations.parseLocationCookie('hcm|unknown'), undefined);
  assert.equal(locations.parseLocationCookie('hcm|Qu%E1%BA%ADn%203').source, 'manual');
  assert.deepEqual(locations.parseLocationCookie(encodeURIComponent(JSON.stringify(manual))), manual);
  console.log('PASS location validation, malformed storage values and legacy-cookie migration');

  let tree = await mount(null);
  assert.equal(gps.length, 1, 'First visit requests GPS exactly once in Strict Mode');
  assert.equal(gps[0].options.timeout, 12000);
  await act(async () => gps[0].fail({ code: 1 }));
  assert.equal(state.modalOpen, true); assert.equal(state.gpsFailed, true);
  assert.equal(state.selectedSearchLocation, undefined);
  await act(async () => state.selectLocation(manual));
  assert.deepEqual(state.selectedSearchLocation, manual); assert.equal(state.modalOpen, false);
  assert.equal(searches.length, 0);
  await unmount(tree);
  const beforeReload = gps.length;
  tree = await mount(null);
  assert.deepEqual(state.selectedSearchLocation, manual);
  assert.equal(gps.length, beforeReload + 1, 'Reload refreshes GPS even with a saved manual origin');
  assert.equal(gps.at(-1).options.maximumAge, 0, 'Request a fresh device position');
  await act(async () => gps.at(-1).fail({ code: 1 }));
  assert.deepEqual(state.selectedSearchLocation, manual, 'GPS denial preserves the saved fallback');
  assert.equal(state.gpsFailed, true);
  const history = Array.from({ length: 6 }, (_, i) => ({ ...manual, lat: manual.lat + i * 0.01, address: `Recent place ${i}`, shortLabel: `Recent ${i}` }));
  for (const place of history) await act(async () => state.selectLocation(place));
  assert.equal(state.recentLocations.length, 3);
  assert.deepEqual(state.recentLocations.map(place => place.shortLabel), ['Recent 5', 'Recent 4', 'Recent 3']);
  await act(async () => state.selectLocation(history[3]));
  assert.deepEqual(state.recentLocations.map(place => place.shortLabel), ['Recent 3', 'Recent 5', 'Recent 4']);
  assert.equal(JSON.parse(storage.get(locations.LOCATION_STORAGE_KEY)).recent.length, 3);
  await unmount(tree);
  storage.set(locations.LOCATION_STORAGE_KEY, JSON.stringify({ selected: manual, recent: history }));
  tree = await mount(null);
  assert.equal(state.recentLocations.length, 3, 'Overlong saved history is trimmed on restore');
  assert.equal(JSON.parse(storage.get(locations.LOCATION_STORAGE_KEY)).recent.length, 3);
  await unmount(tree);
  console.log('PASS first visit, GPS fallback, persistence, three-place MRU cap, deduplication and old-history migration');

  tree = await mount(null, second);
  await act(async () => { gps.at(-1).ok({ coords: { latitude: 10.838, longitude: 106.665 } }); });
  assert.equal(state.selectedSearchLocation.lat, 10.838, 'Fresh GPS replaces the persisted origin on reload');
  assert.equal(state.selectedSearchLocation.source, 'gps');
  assert.equal(JSON.parse(storage.get(locations.LOCATION_STORAGE_KEY)).selected.lat, 10.838);
  await unmount(tree);

  tree = await mount(null);
  const pendingGps = gps.at(-1);
  await act(async () => state.openLocation());
  await act(async () => state.selectLocation(manual));
  await act(async () => pendingGps.ok({ coords: { latitude: 21.03, longitude: 105.85 } }));
  assert.deepEqual(state.selectedSearchLocation, manual, 'Manual choice beats a delayed startup GPS response');
  await act(async () => pendingGps.fail({ code: 1 }));
  assert.equal(state.gpsFailed, false, 'Stale GPS failure does not reopen the picker');
  await unmount(tree);
  console.log('PASS startup GPS refresh, persistence and manual override of delayed GPS');

  storage.clear(); document.cookie = '';
  tree = await mount(null);
  await act(async () => { gps.at(-1).ok({ coords: { latitude: 10.838, longitude: 106.665 } }); });
  assert.equal(state.currentDeviceLocation.source, 'gps');
  assert.equal(state.selectedSearchLocation.lat, 10.838);
  await act(async () => state.selectLocation(manual));
  await act(async () => lookups.at(-1).resolve([{ ...second, source: 'gps' }]));
  assert.deepEqual(state.selectedSearchLocation, manual, 'Late reverse geocoding cannot replace a manual selection');
  assert.equal(state.currentDeviceLocation.lat, 10.838, 'Device location stays separate from search origin');
  assert.equal(state.currentDeviceLocation.shortLabel, second.shortLabel, 'Device address can finish resolving without replacing the manual search origin');
  await unmount(tree);
  console.log('PASS GPS coordinates, device/search separation and late reverse-geocode protection');

  // Shared search/chat/location flows are covered by search-state-regression.cjs.
  tree = await mount(React.createElement(LocationPicker));
  await act(async () => state.openLocation());
  assert.equal(state.modalOpen, true);
  assert.equal(tree.root.findByType('dialog').props['aria-labelledby'].length > 0, true);
  const addressInput = () => tree.root.findByProps({ role: 'combobox' });
  await act(async () => addressInput().props.onChange({ target: { value: 'Xuan Hoa' } }));
  assert.equal(tree.root.findAllByProps({ role: 'option' }).length > 0, true);
  await act(async () => addressInput().props.onKeyDown({ key: 'ArrowDown', preventDefault() {} }));
  assert.equal(addressInput().props['aria-activedescendant'].endsWith('option-0'), true);
  const priorSearches = searches.length;
  await act(async () => addressInput().props.onKeyDown({ key: 'Enter', preventDefault() {} }));
  assert.equal(state.modalOpen, false);
  assert.equal(state.selectedSearchLocation.source, 'manual');
  assert.equal(searches.length, priorSearches);
  await act(async () => state.openLocation());
  await act(async () => tree.root.findAllByType('button').find(button => button.children.includes('TP. H\u1ed3 Ch\u00ed Minh')).props.onClick());
  assert.equal(state.selectedSearchLocation.shortLabel, locations.CITY_LOCATIONS[0].shortLabel, 'City button immediately updates the shared location');
  assert.equal(state.modalOpen, true, 'City selection keeps the ward picker available');
  assert.equal(searches.length, priorSearches, 'City selection does not start a food search');
  const wardInput = () => tree.root.findAllByProps({ role: 'combobox' }).at(-1);
  await act(async () => wardInput().props.onFocus());
  assert.equal(tree.root.findAllByProps({ role: 'option' }).length, 168);
  await act(async () => tree.root.findAllByType('button').find(button => button.children.includes('H\u00e0 N\u1ed9i')).props.onClick());
  assert.equal(state.selectedSearchLocation.shortLabel, locations.CITY_LOCATIONS[1].shortLabel, 'The outside header/filter now follows the newly selected city');
  assert.equal(state.modalOpen, true);
  assert.equal(wardInput().props['aria-expanded'], false, 'Changing city clears the previous dropdown/filter');
  await act(async () => wardInput().props.onFocus());
  assert.equal(tree.root.findAllByProps({ role: 'option' }).length, 126);
  await act(async () => wardInput().props.onChange({ target: { value: 'Hoan Kiem' } }));
  assert.equal(tree.root.findAllByProps({ role: 'option' }).length, 1, 'Ward search ignores Vietnamese accents');
  assert.ok(tree.root.findAllByProps({ role: 'option' })[0].findAllByType('span').some(node => node.children.includes('H\u00e0 N\u1ed9i')));
  await act(async () => wardInput().props.onChange({ target: { value: 'no such ward zzz' } }));
  assert.equal(tree.root.findAllByProps({ role: 'option' }).length, 0);
  await act(async () => wardInput().props.onKeyDown({ key: 'Enter', preventDefault() {} }));
  assert.equal(state.modalOpen, true, 'Empty results cannot select a fabricated ward');
  await act(async () => wardInput().props.onChange({ target: { value: '' } }));
  await act(async () => wardInput().props.onKeyDown({ key: 'ArrowUp', preventDefault() {} }));
  assert.ok(wardInput().props['aria-activedescendant']);
  let escapeConsumed = false;
  await act(async () => wardInput().props.onKeyDown({ key: 'Escape', preventDefault() { escapeConsumed = true; }, stopPropagation() {} }));
  assert.equal(escapeConsumed, true);
  assert.equal(state.modalOpen, true, 'Escape closes the inner dropdown first');
  assert.equal(wardInput().props['aria-expanded'], false);
  await act(async () => wardInput().props.onKeyDown({ key: 'ArrowDown', preventDefault() {} }));
  const activeId = wardInput().props['aria-activedescendant'];
  const chosen = tree.root.findByProps({ id: activeId });
  assert.equal(chosen.props['data-active'], true);
  await act(async () => wardInput().props.onKeyDown({ key: 'Enter', preventDefault() {} }));
  assert.equal(state.modalOpen, false);
  assert.equal(searches.length, priorSearches, 'Ward selection must not issue a food search');
  await act(async () => state.openLocation());
  await act(async () => tree.root.findByType('dialog').props.onCancel());
  assert.equal(state.modalOpen, false);
  await unmount(tree);
  console.log('PASS modal semantics, accent-insensitive suggestions, arrow/Enter selection and ESC close handler');

  const legacyGps = { lat: 10.723, lon: 106.626, address: '10.72300, 106.62600', shortLabel: 'GPS · 10.723, 106.626', source: 'gps' };
  storage.set(locations.LOCATION_STORAGE_KEY, JSON.stringify({ selected: legacyGps, recent: [] }));
  const gpsBeforeRestore = gps.length;
  tree = await mount(null);
  assert.equal(gps.length, gpsBeforeRestore + 1, 'Saved GPS origins also request a fresh fix');
  assert.equal(locations.needsGpsAddress(state.selectedSearchLocation), true);
  assert.ok(!state.selectedSearchLocation.shortLabel.includes('10.723'), 'Raw coordinates are not the header label');
  await act(async () => gps.at(-1).fail({ code: 1 }));
  await act(async () => state.openLocation());
  assert.deepEqual(lookups.at(-1).query, { lat: legacyGps.lat, lon: legacyGps.lon });
  await act(async () => lookups.at(-1).resolve([]));
  const beforeRetry = lookups.length;
  await act(async () => state.openLocation());
  assert.equal(lookups.length, beforeRetry + 1, 'Opening picker retries an unresolved saved GPS address');
  const lateAddress = lookups.at(-1);
  await act(async () => state.selectLocation(manual));
  await act(async () => lateAddress.resolve([{ ...second, source: 'gps' }]));
  assert.deepEqual(state.selectedSearchLocation, manual, 'Manual ward/city selection beats a late address retry');
  await unmount(tree);
  storage.set(locations.LOCATION_STORAGE_KEY, JSON.stringify({ selected: legacyGps, recent: [] }));
  tree = await mount(null);
  await act(async () => gps.at(-1).fail({ code: 1 }));
  await act(async () => state.openLocation());
  await act(async () => lookups.at(-1).resolve([{ ...second, shortLabel: 'Resolved ward, Test city', address: 'Resolved address' }]));
  assert.equal(state.selectedSearchLocation.shortLabel, 'Resolved ward, Test city');
  assert.equal(state.selectedSearchLocation.source, 'gps');
  assert.equal(state.selectedSearchLocation.lat, legacyGps.lat, 'Geocoding cannot replace the exact search coordinates');
  assert.equal(state.selectedSearchLocation.lon, legacyGps.lon);
  assert.equal(JSON.parse(storage.get(locations.LOCATION_STORAGE_KEY)).selected.shortLabel, 'Resolved ward, Test city');
  await unmount(tree);
  const beforeNamedRestore = lookups.length;
  tree = await mount(null);
  assert.equal(lookups.length, beforeNamedRestore, 'A named saved location does not repeat geocoding on load');
  await unmount(tree);
  console.log('PASS legacy GPS labels, saved-origin enrichment, failure/retry, exact-coordinate preservation and manual override');

}
main().catch(error => { console.error(error); process.exitCode = 1; });
