chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {})
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'AURA_GET_PAGE_CONTEXT') return

  chrome.tabs.query({ active: true, lastFocusedWindow: true }, async ([tab]) => {
    if (!tab?.id) return sendResponse({ context: null })
    try {
      const response = await chrome.tabs.sendMessage(tab.id, { type: 'AURA_EXTRACT_PAGE' })
      sendResponse({ context: response?.context ?? null })
    } catch {
      sendResponse({
        context: tab.url ? { title: tab.title ?? '', url: tab.url, description: '' } : null,
      })
    }
  })
  return true
})
