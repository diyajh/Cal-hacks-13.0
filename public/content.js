const firstJsonLd = () => {
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const value = JSON.parse(node.textContent || '')
      const items = Array.isArray(value) ? value : [value]
      const product = items.find(item => item?.['@type'] === 'Product')
      if (product) return {
        name: product.name || '',
        price: product.offers?.price ?? product.offers?.lowPrice ?? '',
        currency: product.offers?.priceCurrency || '',
      }
    } catch { /* Ignore malformed third-party metadata. */ }
  }
  return null
}

const extractContext = () => ({
  title: document.title,
  url: location.href,
  description: document.querySelector('meta[name="description"]')?.content || '',
  product: firstJsonLd(),
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'AURA_EXTRACT_PAGE') sendResponse({ context: extractContext() })
})
