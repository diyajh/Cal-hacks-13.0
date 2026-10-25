const assert = require('node:assert/strict')
const fs = require('node:fs')

const source = fs.readFileSync('src/App.tsx', 'utf8')

assert.match(source, /const planWithinBudget = session\.outfits\.length > 0/)
assert.match(source, /planWithinBudget \? '✓ Within constraints'/)
assert.match(source, /const countLabel = \(count: number, singular: string\)/)
assert.match(source, /countLabel\(briefDays, 'day'\)/)
assert.match(source, /countLabel\(request\.outfits \|\| session\.outfits\.length, 'look'\)/)

console.log('planner budget UI regression checks passed')
