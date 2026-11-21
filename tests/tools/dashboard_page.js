// Runs a dashboard page's scripts without a browser.
//
//   node dashboard_page.js <page.html> [<data.js>] [<search query>]
//
// The page's inline scripts are run in order in a bare context with a small
// stand-in for the DOM: enough for the loader and the views to do their work
// (each view writes its markup to `innerHTML`). A <script src> is satisfied
// by <data.js> when given, and left unloaded otherwise, which is what a
// browser does when the file is missing. Prints one JSON object. Used by
// test_dashboard.py; a real browser is still the proof that the page works.
'use strict';
const fs = require('fs');
const vm = require('vm');

const [pagePath, dataPath, query] = process.argv.slice(2);
const html = fs.readFileSync(pagePath, 'utf8');

function element(attrs) {
  const children = {};
  const listeners = {};
  const el = {
    attrs: attrs || {}, innerHTML: '', textContent: '', className: '', value: '', style: {},
    listeners,
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    querySelector(selector) { return children[selector] || (children[selector] = element({})); },
    child(selector) { return children[selector]; },
    fire(type, event) { (listeners[type] || []).forEach(fn => fn(event)); },
  };
  return el;
}

// Sections, as the page declares them.
const sections = [];
const tagRe = /<section\b([^>]*)>/g;
let match;
while ((match = tagRe.exec(html))) {
  const attrs = {};
  const attrRe = /([\w-]+)="([^"]*)"/g;
  let attr;
  while ((attr = attrRe.exec(match[1]))) attrs[attr[1]] = attr[2];
  if (attrs['data-view']) sections.push(element(attrs));
}
const byId = {};
const documentStub = {
  documentElement: element({}),
  getElementById(id) { return byId[id] || (byId[id] = element({ id })); },
  querySelectorAll(selector) { return selector === '[data-view]' ? sections : []; },
};
const windowStub = { localStorage: { getItem() { return null; }, setItem() {} }, matchMedia() { return { matches: false }; } };
const context = vm.createContext({ window: windowStub, document: documentStub, console });

const report = { scripts: 0, external: [], loaded: false, error: null };
const scriptRe = /<script\b([^>]*)>([\s\S]*?)<\/script>/g;
try {
  while ((match = scriptRe.exec(html))) {
    const src = /\bsrc="([^"]*)"/.exec(match[1]);
    if (src) {
      report.external.push(src[1]);
      if (dataPath) {
        // A script that does not parse or that throws stops itself, not the page.
        try {
          vm.runInContext(fs.readFileSync(dataPath, 'utf8'), context, { filename: src[1] });
          report.loaded = true;
        } catch (err) {
          report.dataError = String(err && err.message || err);
        }
      }
      continue;
    }
    report.scripts += 1;
    vm.runInContext(match[2], context, { filename: 'inline-' + report.scripts + '.js' });
  }
} catch (err) {
  report.error = String(err && err.stack || err);
}

const PKA = vm.runInContext('typeof PKA === "undefined" ? null : PKA', context);
if (PKA) {
  report.ok = PKA.ok;
  report.problem = PKA.problem;
  report.files = PKA.files.length;
  report.paths = PKA.files.map(f => f.path);
  report.titles = PKA.files.map(f => f.title);
  report.people = PKA.people.map(p => p.slug);
  report.counts = PKA.counts;
  report.mode = PKA.mode;
  report.hrefs = PKA.files.map(f => PKA.href(f.path));
  if (query) {
    const found = PKA.search(query, 50);
    report.search = { total: found.total, paths: found.hits.map(h => h.file.path), people: found.people.map(p => p.slug) };
  }
}
report.status = documentStub.getElementById('pka-status').innerHTML || documentStub.getElementById('pka-status').textContent;
report.problemShown = documentStub.getElementById('pka-problem').innerHTML;
report.title = documentStub.getElementById('pka-title').textContent;
report.views = sections.map(section => {
  const body = section.child('.pka-body');
  const parts = [];
  (function collect(el) {
    if (!el) return;
    parts.push(el.innerHTML);
    ['.pka-list', '#search-results'].forEach(sel => collect(el.child(sel)));
  })(body);
  return { id: section.attrs.id, view: section.attrs['data-view'], folder: section.attrs['data-folder'] || '', html: parts.join('\n') };
});
// Type the query into the search box, as a user would.
if (query) {
  const search = sections.filter(s => s.attrs['data-view'] === 'search')[0];
  const body = search && search.child('.pka-body');
  const box = body && body.child('#q');
  if (box) {
    box.fire('input', { target: { value: query } });
    report.searchHtml = body.child('#search-results').innerHTML;
  }
}
process.stdout.write(JSON.stringify(report));
