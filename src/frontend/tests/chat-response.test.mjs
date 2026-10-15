import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Module, { createRequire } from 'node:module';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const load = createRequire(import.meta.url);
for (const extension of ['.ts', '.tsx']) load.extensions[extension] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText, filename);
const { searchReply } = load('../lib/chat-response.ts');
const { vi } = load('../lib/locales/vi.ts');
const { en } = load('../lib/locales/en.ts');
const row = (id, group) => ({restaurant_id: id, menu_item_id: id, rank: 1, score: 1, recommendation_group: group});
const response = (extra = {}) => ({intent: 'search', results: [], clarification_required: false, warnings: [], ...extra});

for (const [lang, chat] of [['vi', vi.chat], ['en', en.chat]]) {
  test(`${lang}: actual unique primary count wins over stale assistant text`, () => {
    const reply = searchReply(response({results: [row('A', 'primary'), row('A', 'primary'), row('B', 'supplementary')], assistant_message: 'Found 999 restaurants'}), chat);
    assert.equal(reply, chat.searchFound(1));
    assert.match(reply, lang === 'vi' ? /danh mục minh họa/ : /demo catalog/);
  });
  test(`${lang}: only qualified alternatives use actual restaurant count`, () => {
    assert.equal(searchReply(response({results: [row('A', 'supplementary'), row('A', 'supplementary'), row('B', 'supplementary')]}), chat), chat.searchAlternatives(2));
  });
  test(`${lang}: empty, clarification and deferred retrieval remain distinct`, () => {
    assert.equal(searchReply(response(), chat), chat.searchEmpty);
    assert.equal(searchReply(response({clarification_required: true, results: [row('old', 'primary')]}), chat), chat.searchClarification);
    assert.equal(searchReply(response({intent: 'clarification'}), chat), chat.searchClarification);
    assert.equal(searchReply(response({retrieval_deferred: true}), chat), chat.searchDeferred);
  });
  test(`${lang}: general/legacy recommendation does not claim an exact dish match`, () => {
    assert.equal(searchReply(response({results: [row('A', 'general'), row('B', undefined)]}), chat), chat.searchFoundGeneral(2));
  });
  for (const intent of ['conversation', 'informational']) test(`${lang}: ${intent} keeps the generated AI2 reply`, () => {
    assert.equal(searchReply(response({intent, assistant_message: 'Phở thường có sợi dẹt.', warnings: ['old warning']}), chat), 'Phở thường có sợi dẹt.');
  });
}

test('important unverified-side warnings survive while repetitive technical warnings stay on results page', () => {
  const warning = 'Chưa xác minh quán có phục vụ món kèm: chén trứng. Bạn nên hỏi lại quán.';
  const reply = searchReply(response({warnings: [warning, warning, 'Chưa có dữ liệu xác minh cho một số kết quả: quiet.', 'Khoảng cách là khoảng cách địa lý, chưa tính quãng đường di chuyển thực tế.']}), vi.chat);
  assert.equal(reply, vi.chat.searchEmpty + '\n' + warning);
});

test('allergy/actionable warnings are preserved and long messages bounded', () => {
  const warning = 'Chưa có dữ liệu xác minh cho một số kết quả: dị ứng sữa.';
  assert.ok(searchReply(response({warnings: [warning]}), vi.chat).includes(warning));
  assert.ok(searchReply(response({warnings: ['Unverified requirement '.repeat(100)]}), en.chat).length < 550);
  assert.ok(searchReply(response({warnings: ['Other notice', 'Another notice', warning]}), vi.chat).includes(warning));
});

// Render the real card layout, stubbing only map/action/image infrastructure.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const originalResolve = Module._resolveFilename;
const originalLoad = Module._load;
Module._resolveFilename = function (request, parent, ...args) {
  return originalResolve.call(this, request.startsWith('@/') ? path.join(root, request.slice(2)) : request, parent, ...args);
};
Module._load = function (request, parent, ...args) {
  if (request === './MapPanel' && parent?.filename.endsWith('ResultExplorer.tsx')) return function MapStub() { return React.createElement('div', null, 'map'); };
  if (request === '@/components/common/FavoriteButton') return function FavoriteStub() { return React.createElement('button', null, 'favorite'); };
  if (request === 'next/image') return function ImageStub() { return React.createElement('span', null, 'image'); };
  return originalLoad.call(this, request, parent, ...args);
};
const ResultExplorer = load('../components/search/ResultExplorer.tsx').default;
Module._resolveFilename = originalResolve;
Module._load = originalLoad;

test('real restaurant cards keep groups/actions/menu details and render no legacy explanation paragraphs', () => {
  const html = renderToStaticMarkup(React.createElement(ResultExplorer, {namedQuery: true, results: [
    {...row('A', 'primary'), restaurant_name: 'KFC', dish_name: 'Phở chay', price_vnd: 55000, explanation: 'OBSOLETE EXPLANATION TEXT',
      eligible_menu_items: [{menu_item_id: 'other', dish_name: 'Phở nấm chay', price: 60000, reason_features: {}}]},
    {...row('B', 'supplementary'), restaurant_name: 'B', dish_name: 'Phở bò', explanation: 'OBSOLETE ALTERNATIVE TEXT'},
  ]}));
  assert.ok(!html.includes('OBSOLETE'));
  assert.ok(html.includes('Kết quả phù hợp') && html.includes('Gợi ý thêm'));
  assert.ok(html.includes('Phở nấm chay') && html.includes('favorite'));
});
