const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('static/theme.js', 'utf8');

function setup(saved, blocked = false) {
  const events = {}, buttons = [];
  let stored = saved;
  const root = {dataset: {}};
  const context = vm.createContext({
    document: {documentElement: root, querySelectorAll: () => buttons,
      addEventListener: (name, fn) => { events[name] = fn; }},
    window: {addEventListener: (name, fn) => { events[name] = fn; }},
    localStorage: {getItem: () => { if (blocked) throw Error('blocked'); return stored; },
      setItem: (_, value) => { if (blocked) throw Error('blocked'); stored = value; }},
  });
  vm.runInContext(source, context);
  return {root, events, buttons, api: context.window.ACETheme, stored: () => stored,
    click: () => events.click({target: {closest: () => true}})};
}

const light = setup(null);
assert.equal(light.root.dataset.theme, 'light');
assert.match(light.api.control(), /aria-pressed="false"/);
const attrs = {};
light.buttons.push({setAttribute: (key, value) => { attrs[key] = value; }});
light.click();
assert.equal(light.root.dataset.theme, 'dark');
assert.equal(light.stored(), 'dark');
assert.equal(attrs['aria-pressed'], 'true');
assert.equal(setup(light.stored()).root.dataset.theme, 'dark');
assert.match(light.api.control(), /aria-pressed="true"/); // Rerenders preserve the control state.
light.click();
assert.equal(light.root.dataset.theme, 'light');
assert.equal(light.stored(), 'light');
light.events.storage({key: 'acetime-theme', newValue: 'dark'});
assert.equal(light.root.dataset.theme, 'dark');
light.events.storage({key: 'unrelated', newValue: 'light'});
assert.equal(light.root.dataset.theme, 'dark');
light.events.storage({key: null});
assert.equal(light.root.dataset.theme, 'light');
const blocked = setup(null, true);
blocked.click();assert.equal(blocked.root.dataset.theme, 'dark');
blocked.click();assert.equal(blocked.root.dataset.theme, 'light');
assert.equal(setup('invalid').root.dataset.theme, 'light');
const html = fs.readFileSync('static/index.html', 'utf8');
assert.ok(html.indexOf('src="/theme.js"') < html.indexOf('href="/style.css"'));
console.log('Theme persistence, restored controls, cross-tab changes, blocked storage, and early loading checks passed.');
