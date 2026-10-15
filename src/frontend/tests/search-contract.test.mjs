// Node's built-in runner; uses the existing TypeScript compiler, no added package.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
const load = createRequire(import.meta.url);
load.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename);
const { resultGroups, restaurantPlaces } = load('../lib/search-results.ts');
const { filterValues, buildSearchRequest, emptyPreferences } = load('../lib/conversation-state.ts');

const row = (id, group, menu) => ({ restaurant_id: id, recommendation_group: group, menu_item_id: menu,
  restaurant_name: 'KFC', dish_name: 'Phở chay', price_vnd: 55000, distance_km: 2,
  location: { lat: 10.77, lon: 106.69 } });

test('primary precedence, stable restaurant identity, and one marker', () => {
  const rows = [row('same', 'supplementary', 'other'), row('same', 'primary', 'pho'), row('second', 'supplementary', 'alt')];
  const groups = resultGroups(rows);
  assert.deepEqual(groups.primary.map(r => r.menu_item_id), ['pho']);
  assert.deepEqual(groups.supplementary.map(r => r.restaurant_id), ['second']);
  const places = restaurantPlaces(rows, [{id: 'same', name: 'old', lat: 0, lon: 0}, {id: 'same', name: 'duplicate', lat: 0, lon: 0}]);
  assert.equal(places.length, 2);
  assert.equal(places.find(p => p.id === 'same').dish, 'Phở chay');
  assert.equal(places.find(p => p.id === 'same').price_vnd, 55000);
  assert.equal(places.find(p => p.id === 'same').distance_km, 2);
});

test('synthetic labels never group two different restaurant IDs', () => {
  assert.equal(resultGroups([row('A', 'primary', 'M1'), row('B', 'primary', 'M2')]).primary.length, 2);
});

test('effective food stays exact in controlled form and chat snapshot', () => {
  const state = {...emptyPreferences(), food: ['phở chay'], hard_constraints: {vegetarian: true, budget_max: 100000, max_distance_km: 3}};
  assert.equal(filterValues(state).dish, 'phở chay');
  const req = buildSearchRequest(state, 'Tôi muốn quán yên tĩnh hơn');
  assert.equal(req.preference_state, state);
  assert.equal(req.form, undefined); // stale form values cannot overwrite chat
  const edited = {...state, food: ['phở tái']};
  assert.equal(filterValues(edited).dish, 'phở tái');
});

test('general legacy payloads are not labelled supplementary and empties stay empty', () => {
  assert.equal(resultGroups([row('A', undefined, 'M')]).primary.length, 1);
  assert.deepEqual(resultGroups([]), {primary: [], supplementary: []});
  assert.deepEqual(restaurantPlaces([]), []);
});
