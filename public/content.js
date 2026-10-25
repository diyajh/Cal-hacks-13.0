(() => {
  const asText = value => typeof value === 'string' ? value.trim() : ''
  const meta = name => document.querySelector(`meta[property="${name}"], meta[name="${name}"]`)?.content || ''
  const firstVisible = selectors => selectors.map(selector => document.querySelector(selector)).find(node => asText(node?.textContent))
  const required = ['name', 'price', 'currency', 'url', 'image', 'category']
  const optional = ['description', 'brand', 'sku', 'color', 'size', 'rating', 'review_count']
  const has = (product, field) => field === 'price'
    ? (typeof product?.price === 'number' || typeof product?.price === 'string') && String(product.price).trim() !== '' && Number.isFinite(Number(product.price)) && Number(product.price) >= 0
    : product?.[field] != null && String(product[field]).trim() !== ''
  const imageValue = value => asText(Array.isArray(value) ? value[0] : typeof value === 'object' ? value?.url : value)
  const brandValue = value => asText(typeof value === 'object' ? value?.name : value)
  const offerValue = value => {
    const offer = Array.isArray(value) ? value[0] || {} : value || {}
    const spec = Array.isArray(offer.priceSpecification) ? offer.priceSpecification[0] : offer.priceSpecification || {}
    return { price: offer.price ?? offer.lowPrice ?? spec.price ?? '', currency: asText(offer.priceCurrency || spec.priceCurrency) }
  }
  const inferCategory = text => [
    ['shoes', /\b(shoes?|sneakers?|boots?|sandals?|footwear|trainers?)\b/i], ['dress', /\b(dress|dresses)\b/i],
    ['bottom', /\b(pants|jeans|shorts|skirts?|trousers)\b/i], ['outerwear', /\b(jackets?|coats?|outerwear)\b/i],
    ['top', /\b(shirts?|tees?|tops?|blouses?|sweaters?|hoodies?)\b/i], ['accessory', /\b(bags?|hats?|belts?|accessories)\b/i],
  ].find(([, pattern]) => pattern.test(text))?.[0] || ''

  const firstJsonLd = () => {
    const candidates = []
    for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const value = JSON.parse(node.textContent || '')
        const queue = Array.isArray(value) ? [...value] : [value]
        const items = []
        while (queue.length) {
          const item = queue.shift()
          if (!item || typeof item !== 'object') continue
          if (Array.isArray(item['@graph'])) queue.push(...item['@graph'])
          if (Array.isArray(item.hasVariant)) queue.push(...item.hasVariant)
          items.push(item)
        }
        for (const product of items.filter(item => {
          const type = item?.['@type']
          return type === 'Product' || type === 'ProductGroup' || (Array.isArray(type) && type.some(entry => ['Product', 'ProductGroup'].includes(entry)))
        })) {
          const variants = Array.isArray(product.hasVariant) ? product.hasVariant : []
          const variant = variants.find(item => offerValue(item?.offers).price !== '') || variants[0] || {}
          const offer = offerValue(variant.offers ?? product.offers)
          candidates.push({
            name: asText(variant.name || product.name), price: offer.price, currency: offer.currency,
            image: imageValue(variant.image || product.image), description: asText(variant.description || product.description),
            category: asText(variant.category || product.category), brand: brandValue(variant.brand || product.brand),
            color: asText(variant.color || product.color), sku: asText(variant.sku || product.sku), size: asText(variant.size || product.size),
            rating: variant.aggregateRating?.ratingValue ?? product.aggregateRating?.ratingValue ?? '',
            review_count: variant.aggregateRating?.reviewCount ?? product.aggregateRating?.reviewCount ?? '',
            url: asText(variant.url || product.url || location.href), source: 'json-ld',
          })
        }
      } catch { /* Malformed third-party metadata is ignored. */ }
    }
    return candidates.sort((a, b) => Object.values(b).filter(Boolean).length - Object.values(a).filter(Boolean).length)[0] || null
  }

  const fallbackProduct = () => {
    const name = asText(meta('og:title')) || asText(meta('twitter:title')) || asText(meta('product:name')) || asText(firstVisible(['h1', '[itemprop="name"]'])?.textContent) || asText(document.title.split('|')[0])
    if (!name) return null
    const priceNode = firstVisible(['[itemprop="price"]', '[data-testid*="price" i]', '[class*="price" i]'])
    const rawPrice = asText(meta('product:price:amount')) || asText(meta('og:price:amount')) || asText(priceNode?.getAttribute('content')) || asText(priceNode?.textContent)
    return { name, price: rawPrice.replace(/[^0-9.,]/g, ''), currency: asText(meta('product:price:currency')) || asText(meta('og:price:currency')) || asText(document.querySelector('[itemprop="priceCurrency"]')?.getAttribute('content')) || '', image: asText(meta('og:image')) || asText(meta('twitter:image')) || document.querySelector('[itemprop="image"]')?.getAttribute('src') || '', description: asText(meta('og:description')) || asText(meta('description')), category: asText(meta('product:category')) || asText(document.querySelector('[itemprop="category"]')?.textContent), brand: asText(meta('product:brand')) || asText(document.querySelector('[itemprop="brand"]')?.textContent), color: asText(meta('product:color')) || asText(document.querySelector('[itemprop="color"]')?.textContent), url: location.href, source: 'metadata-dom' }
  }

  const extractionQuality = product => {
    const fields = [...required, ...optional].filter(field => has(product, field))
    const missing = required.filter(field => !fields.includes(field))
    const missingOptional = optional.filter(field => !fields.includes(field))
    return { status: missing.length ? (fields.length ? 'partial' : 'unavailable') : 'complete', fields_found: fields, missing_fields: missing, missing_optional_fields: missingOptional, reason: missing.length ? `Missing required fields: ${missing.join(', ')}` : 'All required product fields detected.' }
  }

  const extractContext = () => {
    const structured = firstJsonLd()
    const fallback = fallbackProduct()
    const path = location.pathname || ''
    const listing = /^\/(?:[a-z]{2}(?:-[a-z]{2})?\/?)?$/i.test(path) || /(?:^|\/)(search|w|collections|category|categories)(?:\/|$)/i.test(path)
    const product = listing ? null : structured || fallback
    if (product && fallback) for (const field of ['name', 'price', 'currency', 'image', 'brand', 'category', 'description', 'color', 'url']) if (!product[field] && fallback[field]) product[field] = fallback[field]
    if (product) {
      const breadcrumbs = Array.from(document.querySelectorAll('[aria-label*="breadcrumb" i], [class*="breadcrumb" i]')).map(node => node.textContent || '').join(' ')
      product.category = inferCategory(`${product.category} ${product.name} ${breadcrumbs}`) || product.category
      if (!product.brand && /(^|\.)nike\.com$/i.test(location.hostname)) product.brand = 'Nike'
    }
    const quality = extractionQuality(product)
    console.debug('[Aura content] extraction', { url: location.href, strategy: product?.source || 'none', fields: quality.fields_found, missing: quality.missing_fields, product })
    return { title: document.title, url: location.href, retailer: location.hostname, description: meta('description'), product, extraction_quality: quality }
  }

  let lastSignature = ''
  let retryTimers = []
  let observerTimer = 0
  const publish = context => {
    const signature = JSON.stringify({ url: context.url, product: context.product, quality: context.extraction_quality })
    if (signature === lastSignature) return context
    lastSignature = signature
    chrome.runtime.sendMessage({ type: 'AURA_PAGE_CONTEXT', context }, () => {
      const error = chrome.runtime.lastError
      if (error) console.debug('[Aura content] background unavailable', error.message)
      else console.debug('[Aura content] message sent to background', { url: context.url, quality: context.extraction_quality.status })
    })
    return context
  }
  const extractAndPublish = () => publish(extractContext())
  const scheduleExtraction = () => { retryTimers.forEach(clearTimeout); retryTimers = [0, 500, 1500, 3000].map(delay => setTimeout(extractAndPublish, delay)) }
  const onNavigation = () => { lastSignature = ''; scheduleExtraction() }
  for (const method of ['pushState', 'replaceState']) {
    const original = history[method]
    history[method] = function (...args) { const result = original.apply(this, args); onNavigation(); return result }
  }
  window.addEventListener('popstate', onNavigation)
  window.addEventListener('hashchange', onNavigation)
  new MutationObserver(() => { clearTimeout(observerTimer); observerTimer = setTimeout(() => { if (!lastSignature || extractContext().extraction_quality.status !== 'complete') scheduleExtraction() }, 700) }).observe(document.documentElement, { childList: true, subtree: true })
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== 'AURA_EXTRACT_PAGE') return
    console.debug('[Aura content] message received', { type: message.type, url: location.href })
    sendResponse({ context: extractAndPublish() })
  })
  scheduleExtraction()
})()
