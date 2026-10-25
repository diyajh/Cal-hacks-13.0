const latestContextByTab = new Map()

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
})

const unavailableContext = (tab, reason) => ({
  title: tab?.title || '', url: tab?.url || '', retailer: '', description: '', product: null,
  extraction_quality: { status: 'unavailable', fields_found: [], missing_fields: ['name', 'price', 'currency', 'url', 'image', 'category'], reason },
})

const notifyPanel = (tabId, context) => {
  latestContextByTab.set(tabId, context)
  chrome.runtime.sendMessage({ type: 'AURA_PAGE_CONTEXT_UPDATED', tabId, context }, () => { void chrome.runtime.lastError })
}

const requestFromTab = async tab => {
  if (!tab?.id) return unavailableContext(tab, 'No active tab is available.')
  if (!/^https?:/i.test(tab.url || '')) return unavailableContext(tab, 'Chrome does not allow product detection on this page.')
  const request = () => new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tab.id, { type: 'AURA_EXTRACT_PAGE' }, response => {
      const error = chrome.runtime.lastError
      if (error) reject(new Error(error.message))
      else resolve(response)
    })
  })
  try {
    console.debug('[Aura background] content script connected', { tabId: tab.id, url: tab.url })
    return (await request())?.context || unavailableContext(tab, 'The content script returned no product context.')
  } catch (error) {
    console.debug('[Aura background] content script unavailable; injecting once', { tabId: tab.id, reason: error.message })
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] })
      return (await request())?.context || unavailableContext(tab, 'The injected content script returned no product context.')
    } catch (injectionError) {
      return unavailableContext(tab, `Could not connect to this page: ${injectionError.message}`)
    }
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'AURA_PAGE_CONTEXT') {
    const tabId = sender.tab?.id
    if (tabId != null && message.context) {
      console.debug('[Aura background] product context received', { tabId, url: message.context.url, product: message.context.product, quality: message.context.extraction_quality })
      notifyPanel(tabId, message.context)
    }
    return
  }
  if (message?.type !== 'AURA_GET_PAGE_CONTEXT') return
  chrome.tabs.query({ active: true, lastFocusedWindow: true }, async ([tab]) => {
    console.debug('[Aura background] URL received', tab?.url || '')
    const context = await requestFromTab(tab)
    if (tab?.id != null) notifyPanel(tab.id, context)
    console.debug('[Aura background] API routing destination', 'popup context; backend routing remains in React client')
    sendResponse({ context })
  })
  return true
})
