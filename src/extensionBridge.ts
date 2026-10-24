export type PageContext = {
  title: string
  url: string
  description?: string
  product?: { name?: string; price?: string | number; currency?: string } | null
}

export async function getActivePageContext(): Promise<PageContext | null> {
  const runtime = (globalThis as any).chrome?.runtime
  if (!runtime?.sendMessage) return null
  return new Promise(resolve => {
    runtime.sendMessage({ type: 'AURA_GET_PAGE_CONTEXT' }, (response: { context?: PageContext | null } | undefined) => {
      resolve(response?.context ?? null)
    })
  })
}

export function addPageContext(prompt: string, context: PageContext | null): string {
  if (!context) return prompt
  const page = context.product?.name
    ? `Current product: ${context.product.name}${context.product.price ? ` (${context.product.currency || '$'}${context.product.price})` : ''}.`
    : `Current page: ${context.title}.`
  return `${prompt}\n\n${page} Source: ${context.url}`
}
