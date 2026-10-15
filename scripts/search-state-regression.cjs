// Run: node scripts/search-state-regression.cjs <directory containing react-test-renderer>
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
global.document = new EventTarget();
global.window = new EventTarget();
window.matchMedia = () => ({ matches: false });
window.innerHeight = 800;
window.visualViewport = Object.assign(new EventTarget(), { height: 800, offsetTop: 0 });
let dictionary, navigate;
const routes = [];
const router = { push(url) { routes.push(url); navigate(url.split('?')[1] || ''); } };
const storage = new Map();
global.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
Object.defineProperty(global, 'navigator', { configurable: true, value: {} });
const pending = [], calls = [];
global.fetch = (url, options) => new Promise(resolve => {
  const request = { url, ...options, body: options.body && JSON.parse(options.body), resolve: (data, status = 200) => resolve({ ok: status < 400, status, json: async () => data }) };
  pending.push(request); calls.push(request);
});
const cache = new Map();
function load(filename) {
  filename = path.resolve(filename);
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} }; cache.set(filename, module);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  const localRequire = name => {
    if (name === 'react') return React;
    if (name.endsWith('/LangProvider')) return { useT: () => dictionary };
    if (name === 'next/navigation') return { useRouter: () => router };
    if (name === './ResultExplorer') return { __esModule: true, default: props => { React.useEffect(() => { mapMounts++; return () => mapUnmounts++; }, []); return React.createElement('result-explorer', props); } };
    if (name === './SearchLoading') return { __esModule: true, default: () => React.createElement('loading') };
    if (name === 'next/image') return { __esModule: true, default: props => React.createElement('img', props) };
    if (name === 'next/link') return { __esModule: true, default: props => React.createElement('a', props) };
    if (name === 'next/form') return { __esModule: true, default: props => React.createElement('form', props) };
    if (name.startsWith('.') || name.startsWith('@/')) {
      const target = name.startsWith('@/') ? path.join(frontend, name.slice(2)) : path.resolve(path.dirname(filename), name);
      if (target.endsWith('.json')) return JSON.parse(fs.readFileSync(target, 'utf8'));
      for (const ext of ['.tsx', '.ts']) if (fs.existsSync(target + ext)) return load(target + ext);
    }
    return req(name);
  };
  vm.runInThisContext('(function(require,module,exports){' + code + '\n})', { filename })(localRequire, module, module.exports);
  return module.exports;
}
dictionary = load(path.join(frontend, 'lib/locales/vi.ts')).vi;
const { SearchLocationProvider, useSearchLocation } = load(path.join(frontend, 'components/location/SearchLocationProvider.tsx'));
const { SearchPreferenceProvider, useSearchPreferences } = load(path.join(frontend, 'components/search/SearchPreferenceProvider.tsx'));
const Page = load(path.join(frontend, 'components/search/SearchPageContent.tsx')).default;
const Chat = load(path.join(frontend, 'components/chat/ChatWidget.tsx')).default;
const { changedConstraint, emptyPreferences, buildSearchRequest, preferencesFromQuery } = load(path.join(frontend, 'lib/conversation-state.ts'));
const c = dictionary.chat;
const origin = { lat: 10.838, lon: 106.665, shortLabel: 'Gò Vấp', address: 'Gò Vấp, TP.HCM', source: 'manual' };
const other = { lat: 21.0285, lon: 105.8542, shortLabel: 'Hà Nội', address: 'Hà Nội', source: 'manual' };
let state, locationState, tree, mapMounts = 0, mapUnmounts = 0, pageQuery, initialQuery = null;
function Probe() { state = useSearchPreferences(); locationState = useSearchLocation(); return null; }
function Shell() {
  const [query, setQuery] = React.useState(initialQuery);
  pageQuery = query;
  navigate = setQuery;
  return React.createElement(SearchLocationProvider, { initialLocation: storage.size ? undefined : origin },
    React.createElement(SearchPreferenceProvider, null, React.createElement(Probe),
      React.createElement(Chat), query !== null && React.createElement(Page, { query })));
}
const button = label => tree.root.findAllByType('button').find(node => node.props['aria-label'] === label);
const field = name => tree.root.findAllByType('input').find(node => node.props.name === name);
async function mount() {
  await act(async () => { tree = create(React.createElement(React.StrictMode, null, React.createElement(Shell)), {
    createNodeMock: () => ({ style: {}, scrollHeight: 300, scrollTop: 0, focus() {}, scrollTo() {} }),
  }); });
}
async function enter(value) { await act(async () => tree.root.findByType('textarea').props.onChange({ target: { value } })); }
async function send(value) {
  await enter(value);
  await act(async () => tree.root.findByType('textarea').props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: {}, preventDefault() {} }));
}
async function reply(patch = {}, results = [{ restaurant_id: 'real-id', restaurant_name: 'Real place', dish_name: 'Phở', rank: 1 }], clarification = false) {
  const request = pending.shift();
  const snapshot = request.body.preference_state;
  const normalized = { ...emptyPreferences(), ...snapshot, ...patch, session_id: 'cookie-session' };
  await act(async () => request.resolve({ session_id: 'cookie-session', state: normalized, results, clarification_required: clarification, map_places: [], warnings: [] }));
  return request;
}
const resultId = () => tree.root.findByType('result-explorer').props.results[0]?.restaurant_id;
async function main() {
  await mount();
  assert.equal(calls.length, 0);
  assert.deepEqual(locationState.selectedSearchLocation, origin);
  await act(async () => button(c.open).props.onClick());
  window.visualViewport.height = 350;
  await act(async () => window.visualViewport.dispatchEvent(new Event('resize')));
  assert.ok(tree.root.findByType('section').props.style.maxHeight <= 238);
  window.visualViewport.height = 800;
  await act(async () => window.visualViewport.dispatchEvent(new Event('resize')));
  // Case 2: chat response navigates with the same results; no second search.
  await send('phở dưới 100k trong 5km');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'POST');
  assert.deepEqual(calls[0].body.preference_state.location, { lat: origin.lat, lon: origin.lon });
  assert.equal(calls[0].body.form, undefined, 'No stale form overrides');
  await reply({ food: ['phở'], hard_constraints: { budget_max: 100000, max_distance_km: 5 }, semantic_preferences: ['yên tĩnh'] });
  assert.equal(calls.length, 1, 'Chat-to-search navigation reuses the response');
  assert.ok(pageQuery.startsWith('intent='));
  assert.equal(field('dish').props.value, 'phở');
  assert.equal(field('maxPrice').props.value, '100000');
  assert.equal(field('radius').props.value, '5');
  assert.equal(resultId(), 'real-id');
  const firstRoute = pageQuery;
  await act(async () => button(c.close).props.onClick());
  await act(async () => button(c.open).props.onClick());
  assert.ok(JSON.stringify(tree.toJSON()).includes('phở dưới 100k trong 5km'), 'Closing the panel retains conversation');
  assert.deepEqual(locationState.selectedSearchLocation, origin);
  // Case 3: manual edit is shared even before Apply, including future NLP context.
  await act(async () => field('maxPrice').props.onChange({ target: { value: '150000' } }));
  assert.equal(state.preferences.hard_constraints.budget_max, 150000);
  assert.ok(JSON.stringify(tree.toJSON()).includes('150.000'));
  await send('gần hơn');
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.budget_max, 150000);
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.max_distance_km, 5);
  assert.deepEqual(calls.at(-1).body.preference_state.semantic_preferences, ['yên tĩnh']);
  await reply({ hard_constraints: { budget_max: 150000, max_distance_km: 3 } });
  assert.equal(field('maxPrice').props.value, '150000');
  assert.equal(field('radius').props.value, '3');
  const secondRoute = pageQuery;
  // Cases 1/4: removing a chip clears the backend baseline without DELETE.
  const budgetChip = tree.root.findAllByType('button').find(node => node.props['aria-label']?.startsWith('Bỏ ≤'));
  await act(async () => budgetChip.props.onClick());
  assert.equal(state.preferences.hard_constraints.budget_max, undefined);
  await act(async () => tree.root.findAllByType('form').find(node => node.props.action === '/search').props.onSubmit({ preventDefault() {} }));
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.budget_max, undefined);
  assert.deepEqual(calls.at(-1).body.preference_state.semantic_preferences, ['yên tĩnh']);
  await reply();
  assert.ok(calls.every(call => call.method === 'POST'), 'Ordinary searches never reset conversation');
  assert.equal(field('maxPrice').props.value, '');
  // Case 9: back/forward restores coherent preference/result snapshots, no fetch.
  const count = calls.length;
  await act(async () => navigate(firstRoute));
  assert.equal(field('maxPrice').props.value, '100000');
  assert.equal(field('radius').props.value, '5');
  await act(async () => navigate(secondRoute));
  assert.equal(field('maxPrice').props.value, '150000');
  assert.equal(field('radius').props.value, '3');
  assert.equal(calls.length, count);
  // Case 5: manual location changes do not unsolicitedly search or reset filters.
  await act(async () => locationState.selectLocation(other));
  assert.equal(calls.length, count);
  assert.equal(field('maxPrice').props.value, '150000');
  await send('quán yên tĩnh');
  assert.deepEqual(calls.at(-1).body.preference_state.location, { lat: other.lat, lon: other.lon });
  await reply();
  assert.deepEqual(locationState.selectedSearchLocation, other);
  // Case 6: only an explicitly resolved backend coordinate can move the selector.
  await send('tìm quanh địa chỉ mới');
  await reply({ location: { lat: 10.75, lon: 106.7 } });
  assert.equal(locationState.selectedSearchLocation.lat, 10.75);
  assert.equal(state.preferences.location.lat, 10.75);
  // A newer manual edit must win over a late response.
  await send('ramen dưới 120k');
  const stale = pending.shift();
  await act(async () => field('maxPrice').props.onChange({ target: { value: '180000' } }));
  await act(async () => stale.resolve({ state: { ...emptyPreferences(), food: ['stale'], hard_constraints: { budget_max: 120000 } }, results: [], clarification_required: false }));
  assert.equal(field('maxPrice').props.value, '180000');
  assert.notDeepEqual(state.preferences.food, ['stale']);
  // Case 10: full normalized snapshots retain untouched preferences across turns.
  await send('ramen dưới 150k');
  await reply({ food: ['ramen'], hard_constraints: { budget_max: 150000, max_distance_km: 5 } });
  await send('gần hơn');
  await reply({ hard_constraints: { budget_max: 150000, max_distance_km: 3 } });
  await send('quán yên tĩnh');
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.budget_max, 150000);
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.max_distance_km, 3);
  assert.deepEqual(calls.at(-1).body.preference_state.food, ['ramen']);
  await reply({ semantic_preferences: ['yên tĩnh'] });
  // Reset failure preserves context; confirmed success clears filters/results/history.
  await act(async () => button(c.reset).props.onClick());
  await act(async () => tree.root.findAllByType('button').find(node => node.children.includes(c.cancel)).props.onClick());
  assert.deepEqual(state.preferences.food, ['ramen']);
  await act(async () => button(c.reset).props.onClick());
  await act(async () => tree.root.findAllByType('button').find(node => node.children.includes(c.reset)).props.onClick());
  await act(async () => pending.shift().resolve({ error: { code: 'unavailable', message: 'offline' } }, 503));
  assert.deepEqual(state.preferences.food, ['ramen']);
  await act(async () => tree.root.findAllByType('button').find(node => node.children.includes(c.reset)).props.onClick());
  assert.equal(pending[0].method, 'DELETE');
  await act(async () => pending.shift().resolve(null, 204));
  assert.deepEqual(state.preferences.food, []);
  assert.deepEqual(state.preferences.hard_constraints, {});
  assert.deepEqual(state.preferences.semantic_preferences, []);
  assert.equal(state.data, null);
  assert.equal(state.preferences.location.lat, 10.75);
  await act(async () => navigate(firstRoute));
  assert.equal(state.data, null, 'Reset invalidates obsolete history tokens');
  // Search welcome suggestions edit the same state and preserve Vietnamese accents.
  const beforeWelcome = calls.length;
  await act(async () => tree.root.findAllByType('button').find(node => node.children.includes('Phở')).props.onClick());
  assert.equal(calls.length, beforeWelcome + 1);
  assert.deepEqual(calls.at(-1).body.preference_state.food, ['Phở']);
  assert.equal(calls.at(-1).body.preference_state.location.lat, 10.75);
  await reply();
  assert.equal(field('dish').props.value, 'Phở');
  // Result list stays mounted through response updates and reset.
  assert.equal(mapUnmounts, 1, 'Only Strict Mode simulated teardown occurred');
  await act(async () => tree.unmount());
  // Case 7: actual location provider starts empty, original request resumes once.
  storage.clear();
  storage.set('not-a-location', 'force missing initial location');
  await mount();
  await act(async () => button(c.open).props.onClick());
  const beforeLocation = calls.length;
  await send('phở trong 3km');
  assert.equal(calls.length, beforeLocation);
  assert.equal(state.status, 'location');
  assert.equal(locationState.modalOpen, true);
  assert.ok(JSON.stringify(tree.toJSON()).includes(c.locationRequired));
  await act(async () => locationState.selectLocation(origin));
  assert.equal(calls.length, beforeLocation + 1);
  assert.equal(calls.at(-1).body.message, 'phở trong 3km');
  await reply({ food: ['phở'], hard_constraints: { max_distance_km: 3 } });
  assert.equal(field('radius').props.value, '3');
  // Empty/clarification messages don't fabricate a search-intent flag or navigate.
  const navigations = routes.length;
  await send('chào bạn');
  await reply({}, [], true);
  assert.equal(routes.length, navigations);
  // Legacy links merge only explicit fields and preserve location/cuisine/context.
  const baseline = { ...emptyPreferences(), cuisine: ['Nhật'], semantic_preferences: ['quiet'], hard_constraints: { budget_max: 90000 } };
  const merged = preferencesFromQuery(baseline, new URLSearchParams('dish=Ph%E1%BB%9F&radius=9'));
  assert.equal(merged.hard_constraints.budget_max, 90000);
  assert.deepEqual(merged.cuisine, ['Nhật']);
  assert.deepEqual(merged.food, ['Phở']);
  assert.equal(buildSearchRequest(merged, '100k thôi').form, undefined);
  await act(async () => tree.unmount());
  // Direct URL entry on first Strict Mode mount performs exactly one search.
  initialQuery = 'dish=Ph%E1%BB%9F&radius=9';
  storage.clear();
  const beforeDirectEntry = calls.length;
  await mount();
  assert.equal(calls.length, beforeDirectEntry + 1);
  assert.equal(calls.at(-1).signal.aborted, false);
  assert.deepEqual(calls.at(-1).body.preference_state.food, ['Phở']);
  assert.equal(calls.at(-1).body.preference_state.hard_constraints.max_distance_km, 9);
  await reply();
  assert.equal(field('radius').props.value, '9');
  await act(async () => tree.unmount());
  console.log('PASS all 10 shared search cases: manual/chat edits, canonical request snapshots, no duplicate navigation search, removals, stable/resolved location, missing-location resume, reset, back/forward, stale replies and multi-turn context');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
