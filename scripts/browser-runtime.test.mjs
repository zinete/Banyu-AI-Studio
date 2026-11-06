import {test} from 'node:test';
import assert from 'node:assert/strict';
import {chromePath} from './browser-runtime.mjs';

test('macOS Chrome bundle is selected', () => {
  assert.equal(chromePath('darwin', {}, p => p.startsWith('/Applications/')), '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
});
test('Windows Chrome remains supported', () => {
  assert.equal(chromePath('win32', {}, () => true), 'C:/Program Files/Google/Chrome/Application/chrome.exe');
});
test('explicit executable is honored and missing executable fails clearly', () => {
  assert.equal(chromePath('darwin', {CHROME_PATH:'/custom/chrome'}, () => true), '/custom/chrome');
  assert.throws(() => chromePath('darwin', {}, () => false), /CHROME_PATH/);
});
