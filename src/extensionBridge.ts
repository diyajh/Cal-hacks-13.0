export type PageContext = {
  title: string
  url: string
  retailer?: string
  description?: string
  extraction_quality?: {
    status: 'complete' | 'partial' | 'decision_ready' | 'enriched' | 'unavailable'
    fields_found: string[]
    missing_fields: string[]
    missing_optional_fields?: string[]
    reason?: string
  }
  product?: {
    url?: string
    sku?: string
    size?: string
    rating?: string | number
    review_count?: string | number
    name?: string
    price?: string | number
    currency?: string
    image?: string
    description?: string
    category?: string
    brand?: string
    color?: string
  } | null
}

export async function getActivePageContext(): Promise<PageContext | null> {
  const runtime = (globalThis as any).chrome?.runtime
  if (!runtime?.sendMessage) return null
  return new Promise((resolve, reject) => {
    runtime.sendMessage({ type: 'AURA_GET_PAGE_CONTEXT' }, (response: { context?: PageContext | null } | undefined) => {
      const error = runtime.lastError
      if (error) {
        console.warn('[Aura popup] active-tab context request failed', error.message)
        reject(new Error(error.message))
        return
      }
      resolve(response?.context ?? null)
    })
  })
}

export function subscribeToPageContext(listener: (context: PageContext) => void): () => void {
  const runtime = (globalThis as any).chrome?.runtime
  if (!runtime?.onMessage?.addListener) return () => {}
  const handler = (message: { type?: string; context?: PageContext }) => {
    if (message?.type === 'AURA_PAGE_CONTEXT_UPDATED' && message.context) listener(message.context)
  }
  runtime.onMessage.addListener(handler)
  return () => runtime.onMessage.removeListener(handler)
}

export function addPageContext(prompt: string, context: PageContext | null): string {
  if (!context) return prompt
  const page = context.product?.name
    ? `Current product on the active shopping page: ${context.product.name}${context.product.brand ? ` by ${context.product.brand}` : ''}${context.product.price ? ` (${context.product.currency || '$'}${context.product.price})` : ''}${context.product.category ? `, category ${context.product.category}` : ''}. Product URL: ${context.url}`
    : `Current page: ${context.title}.`
  return `${prompt}\n\n${page} Source: ${context.url}`
}
