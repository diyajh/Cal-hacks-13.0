const { test } = require('node:test')
const assert = require('node:assert/strict')
const vm = require('node:vm')
const fs = require('node:fs')
const source = fs.readFileSync('public/content.js', 'utf8')
const url = 'https://www.nike.com/t/air-force-1-07-mens-shoes-DZejrQoC/CW2288-111'
const image = 'https://static.nike.com/a/images/test/air-force-1.jpg'
const nike = { '@type': 'Product', name: 'Nike Air Force 1 ’07 Men’s Shoes', image, sku: 'CW2288-111', offers: { price: 115, priceCurrency: 'USD' } }
function extract(product = nike, pageUrl = url, metadata = {}) {
  let capturedContext = null
  const runtime = {
    onMessage: { addListener() {} },
    sendMessage(message, callback) {
      capturedContext = message?.context || null
      if (callback) callback()
    },
  }
  const context = vm.createContext({
    URL, location: new URL(pageUrl), history: { pushState() {}, replaceState() {} }, window: { addEventListener() {} }, MutationObserver: class { observe() {} }, setTimeout: (fn) => { fn(); return 0 }, clearTimeout() {}, console: { debug() {} },
    chrome: { runtime },
    document: {
      documentElement: {},
      title: product?.name || 'Nike. Just Do It.',
      querySelectorAll(selector) { return selector.startsWith('script') && product ? [{ textContent: JSON.stringify(product) }] : [] },
      querySelector(selector) { const key = /meta\[property="([^"]+)"/.exec(selector)?.[1]; return key && metadata[key] ? { content: metadata[key] } : null },
    },
  })
  vm.runInContext(source, context)
  return capturedContext
}
test('Nike product extraction is decision-ready and preserves source values', () => {
  const result = extract()
  assert.equal(result.extraction_quality.status, 'complete')
  assert.equal(result.product.brand, 'Nike')
  assert.equal(result.product.category, 'shoes')
  assert.equal(result.product.price, 115)
  assert.equal(result.product.currency, 'USD')
  assert.equal(result.product.image, image)
  assert.equal(result.product.url, url)
  assert.equal(result.product.sku, 'CW2288-111')
  assert.equal(result.product.description, '')
})
test('homepage and search cannot qualify even with product-shaped metadata', () => {
  for (const path of ['/', '/us/', '/search?q=shoes', '/w/mens-shoes']) {
    assert.equal(extract(nike, `https://www.nike.com${path}`).extraction_quality.status, 'unavailable')
  }
  assert.equal(extract(null, 'https://www.nike.com/').extraction_quality.status, 'unavailable')
})
test('missing required fields make product unavailable', () => {
  for (const product of [
    { ...nike, offers: { priceCurrency: 'USD' } },
    { ...nike, image: '' },
    { ...nike, name: '' },
    { ...nike, offers: { price: 115 } },
    { ...nike, offers: { price: 'not a price', priceCurrency: 'USD' } },
  ]) assert.equal(extract(product).extraction_quality.status, 'partial')
})
test('missing description and brand do not gate decision readiness', () => {
  const result = extract({ ...nike, name: 'Air Force 1 Men’s Shoes' }, 'https://example.com/product/shoes')
  assert.equal(result.extraction_quality.status, 'complete')
  assert.equal(result.product.category, 'shoes')
  assert.equal(result.product.description, '')
  assert.equal(result.product.brand, '')
})
test('complete optional metadata upgrades product to enriched', () => {
  const result = extract({ ...nike, description: 'Retailer description', brand: { name: 'Nike' }, color: 'White', size: '10', aggregateRating: { ratingValue: 4.8, reviewCount: 100 } })
  assert.equal(result.extraction_quality.status, 'complete')
})
