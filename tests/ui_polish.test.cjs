const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')

const source = fs.readFileSync('src/App.tsx', 'utf8')
const extensionShell = source.split('if (extensionRuntime) return')[1].split('return <div className="app-shell">')[0]

test('judge-facing shell uses human copy and settings-gated diagnostics', () => {
  assert.match(extensionShell, /Aura is ready/)
  assert.match(extensionShell, /YOUR TRIP PLAN/)
  assert.match(extensionShell, /Live product result/)
  assert.match(extensionShell, /Why Aura chose this/)
  assert.match(extensionShell, /Good addition to your wardrobe/)
  assert.match(extensionShell, /You already own something similar/)
  assert.match(extensionShell, /We need one more detail about your saved wardrobe/)
  assert.match(extensionShell, /developerDetails &&/)
  assert.doesNotMatch(extensionShell, /className="extension-live-data"/)
  assert.doesNotMatch(extensionShell, /className="extension-reset"/)
  assert.doesNotMatch(extensionShell, /className="extension-clear-memory"/)
  assert.doesNotMatch(extensionShell, /APIFY CANDIDATE/)
  assert.doesNotMatch(source, /INSUFFICIENT_WARDROBE_DATA/)
})

test('plan summary keeps requested look count and wardrobe reuse visible', () => {
  assert.match(extensionShell, /\{session\.outfits\.length\} looks/)
  assert.match(extensionShell, /wardrobe pieces reused/)
  assert.match(extensionShell, /\{purchaseItems\.length\} new products purchased/)
  assert.match(extensionShell, /placeholder="Replace the skirt in outfit 3…"/)
})

test('clearing the last wardrobe item cannot retain a duplicate decision', () => {
  assert.match(source, /if \(next\.length\) void refreshProductDecision\(next\)/)
  assert.match(source, /decisionRequestRef\.current \+= 1/)
  assert.match(source, /setProductDecision\(null\)/)
  assert.match(extensionShell, /Add wardrobe items to check for duplicates\./)
})
