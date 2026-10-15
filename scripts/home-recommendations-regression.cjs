// Run: node scripts/home-recommendations-regression.cjs <react-test-renderer directory>
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
const requests = [];
let pickerCalls = 0;
const context = { ready: true, selectedSearchLocation: undefined, openLocation() { pickerCalls++; } };
const api = { recommendationCategories: { noodle: { vi: 'Noodles', en: 'Noodles' } }, getTodayRecommendations: args => new Promise((resolve, reject) => requests.push({ ...args, resolve, reject })) };
const cache = new Map();
let dictionary;
function load(filename) {
  filename = path.resolve(filename);
  if (cache.has(filename)) return cache.get(filename).exports;
  const module = { exports: {} }; cache.set(filename, module);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  function localRequire(name) {
    if (name === 'react') return React;
    if (name === '@/lib/i18n-server') return { getT: async () => dictionary };
    if (name === '@/lib/today-recommendations') return api;
    if (name.endsWith('/SearchLocationProvider')) return { useSearchLocation: () => context };
    if (name.endsWith('/LangProvider')) return { useT: () => dictionary, useLang: () => dictionary.lang };
    if (name === 'next/image' || name === 'next/link') return { __esModule: true, default: props => React.createElement(name === 'next/image' ? 'img' : 'a', props) };
    if (name.startsWith('.') || name.startsWith('@/')) {
      const target = name.startsWith('@/') ? path.join(frontend, name.slice(2)) : path.resolve(path.dirname(filename), name);
      if (target.endsWith('.json') && fs.existsSync(target)) return JSON.parse(fs.readFileSync(target, 'utf8'));
      for (const ext of ['.tsx', '.ts']) if (fs.existsSync(target + ext)) return load(target + ext);
    }
    return req(name);
  }
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, { filename })(localRequire, module, module.exports);
  return module.exports;
}
dictionary = load(path.join(frontend, 'lib/locales/en.ts')).en;
const Today = load(path.join(frontend, 'components/home/TodayRecommendations.tsx')).default;
const element = () => React.createElement(React.StrictMode, null, React.createElement(Today));
const location = lat => ({ lat, lon: 106.68, shortLabel: 'Test area' });
const response = (name, count = 4) => ({ items: Array.from({ length: count }, (_, index) => ({ restaurant_id: `${name}-${index}`, restaurant_name: `${name} restaurant ${index}`, menu_item_id: `${name}-menu-${index}`, dish_id: `dish-${index}`, dish_name: `Dish ${index}`, image_url: null, rating: index === 0 ? null : 4.8, review_count: null, price: 50000, price_is_verified: false, is_synthetic: true, latitude: 10.78, longitude: 106.68, distance_km: 1.2, category: 'noodle', area: 'Another district' })), radius_km: 10, rating_fallback: true, unrated_included: true });
async function main() {
  let tree;
  await act(async () => { tree = create(element()); });
  await act(async () => { await sleep(100); });
  assert.equal(requests.length, 0, 'No origin means no recommendation request');
  assert.equal(tree.root.findAllByType('article').length, 0);
  await act(async () => tree.root.findAllByType('button').at(-1).props.onClick());
  assert.equal(pickerCalls, 1);
  context.selectedSearchLocation = location(10.78);
  await act(async () => tree.update(element()));
  assert.equal(tree.root.findAll(node => node.type === 'div' && String(node.props['aria-hidden']) === 'true').length, 4, 'Loading has four matching skeletons');
  await act(async () => { await sleep(100); });
  assert.equal(requests.length, 1, 'Strict Mode coalesces requests');
  assert.equal(requests[0].lat, 10.78); assert.equal(requests[0].limit, 4);
  await act(async () => requests[0].resolve(response('first')));
  assert.equal(tree.root.findAllByType('article').length, 4);
  assert.equal(tree.root.findAll(node => node.type === 'span' && node.props['data-food-emoji']).length, 4, 'Every card has an image or labelled illustration');
  assert.equal(JSON.stringify(tree.toJSON()).includes('(0)'), false, 'Unknown review counts must not become invented zeroes');
  assert.equal(JSON.stringify(tree.toJSON()).includes('Not yet rated'), false, 'Unknown ratings use a compact dash, not a repeated label');
  console.log('PASS missing-origin state, selector hook, four skeletons, four cards and honest missing metadata');

  context.selectedSearchLocation = location(10.79);
  await act(async () => tree.update(element()));
  assert.equal(tree.root.findAllByType('article').length, 0, 'Old-location cards are not presented as new-location results');
  await act(async () => { await sleep(100); });
  const stale = requests[1];
  context.selectedSearchLocation = location(10.80);
  await act(async () => tree.update(element()));
  await act(async () => { await sleep(100); });
  assert.equal(stale.signal.aborted, true);
  await act(async () => requests[2].resolve(response('latest')));
  await act(async () => stale.resolve(response('stale')));
  const markup = JSON.stringify(tree.toJSON());
  assert.equal(markup.includes('latest restaurant'), true); assert.equal(markup.includes('stale restaurant'), false);
  const count = requests.length;
  context.selectedSearchLocation = { ...context.selectedSearchLocation, shortLabel: 'Resolved address' };
  await act(async () => tree.update(element()));
  await act(async () => { await sleep(100); });
  assert.equal(requests.length, count, 'An address-label change does not refetch unchanged coordinates');
  console.log('PASS location refresh, cancellation, stale-response guard and stable-coordinate requests');

  context.selectedSearchLocation = location(10.81);
  await act(async () => tree.update(element()));
  await act(async () => { await sleep(100); });
  await act(async () => requests.at(-1).reject(new Error('offline')));
  const retry = tree.root.findAllByType('button').find(button => button.children.includes('Try again'));
  assert.ok(retry);
  await act(async () => retry.props.onClick());
  await act(async () => { await sleep(100); });
  await act(async () => requests.at(-1).resolve(response('empty', 0)));
  assert.equal(tree.root.findAllByType('article').length, 0);
  assert.equal(JSON.stringify(tree.toJSON()).includes(dictionary.trending.empty), true);
  context.selectedSearchLocation = location(10.82);
  await act(async () => tree.update(element()));
  await act(async () => { await sleep(100); });
  await act(async () => requests.at(-1).resolve(response('sparse', 2)));
  assert.equal(tree.root.findAllByType('article').length, 2);
  assert.equal(JSON.stringify(tree.toJSON()).includes(dictionary.trending.fewer), true);
  await act(async () => tree.unmount());
  console.log('PASS friendly errors, explicit retry, empty results and truthful sparse-data count');

  const Hero = load(path.join(frontend, 'components/home/HeroSection.tsx')).default;
  const Footer = load(path.join(frontend, 'components/layout/Footer.tsx')).default;
  await act(async () => { tree = create(await Hero()); });
  assert.equal(tree.root.findAllByType('h1').length, 1);
  assert.ok(tree.root.findByProps({ href: '/search' }));
  assert.ok(tree.root.findByProps({ href: '#today-recommendations' }));
  await act(async () => tree.unmount());
  await act(async () => { tree = create(await Footer()); });
  assert.equal(tree.root.findAllByType('h3').length, 4);
  assert.equal(tree.root.findAllByType('a').length, 16);
  await act(async () => tree.unmount());
  console.log('PASS refactored hero actions and footer rendering');

  const Spin = load(path.join(frontend, 'components/spin/SpinSection.tsx')).default;
  await act(async () => { tree = create(React.createElement(Spin)); });
  const spinButton = () => tree.root.findAllByType('button').find(button => button.children.includes(dictionary.spin.spinNow));
  const categoryButtons = () => tree.root.findAllByType('button').filter(button => button.props['aria-pressed'] !== undefined);
  assert.equal(categoryButtons().length, 7);
  assert.equal(categoryButtons().filter(button => button.props['aria-pressed']).length, 1);
  await act(async () => categoryButtons()[1].props.onClick());
  assert.equal(categoryButtons().filter(button => button.props['aria-pressed']).length, 2);
  await act(async () => spinButton().props.onClick());
  assert.equal(tree.root.findAllByType('button').filter(button => button.props.disabled).length, 2);
  await act(async () => { await sleep(1150); });
  assert.equal(spinButton().props.disabled, false);
  const selectedName = tree.root.findByType('h3').children.join('');
  const resultLink = tree.root.findByType('a').props.href;
  assert.equal(decodeURIComponent(resultLink.split('dish=')[1]), selectedName);
  await act(async () => tree.unmount());
  console.log('PASS category toggles, spin lifecycle, disabled actions and unchanged search link');

  const Mood = load(path.join(frontend, 'components/mood/MoodSection.tsx')).default;
  await act(async () => { tree = create(React.createElement(Mood)); });
  const moodButton = tree.root.findAllByType('button').find(button => button.children.includes(dictionary.mood.labels.met));
  await act(async () => moodButton.props.onClick());
  assert.equal(tree.root.findByType('h3').children.join(''), 'Chicken congee');
  assert.equal(decodeURIComponent(tree.root.findByType('a').props.href.split('dish=')[1]), 'Chicken congee');
  assert.equal(tree.root.findAllByProps({ 'aria-pressed': true }).length, 1);
  await act(async () => tree.unmount());
  console.log('PASS mood selection and matching search CTA after layout refactor');

}
main().catch(error => { console.error(error); process.exitCode = 1; });
