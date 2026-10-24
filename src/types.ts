export type ProductCategory = 'top' | 'bottom' | 'dress' | 'layer' | 'shoes' | 'accessory'

export interface StyleDNA { label: string; value: number; color: string }
export interface ParsedRequest {
  destination: string; dates: string; days: number; aesthetic: string; outfits: number
  perOutfitBudget: number; totalBudget: number; required: string[]; avoid: string[]; owned: string[]
}
export interface Product {
  id: string; name: string; retailer: string; price: number; category: ProductCategory
  image: string; link: string; owned?: boolean; match: number; note?: string
}
export interface Outfit {
  id: string; day: number; title: string; setting: string; score: number
  scoreBreakdown: { style: number; color: number; occasion: number; budget: number; preference: number }
  products: Product[]; newSpend: number; whyItWorks: string; accent: string
}
export interface AgentEvent { id: string; agent: string; title: string; detail: string; status: 'done' | 'active' }
export interface StyleSession {
  session: string; parsedRequest: ParsedRequest; styleDNA: StyleDNA[]; outfits: Outfit[]
  totalCost: number; newPurchaseCost: number; ownedItems: Product[]; reusedItems: Product[]
  agentEvents: AgentEvent[]; constraintStatus: 'satisfied' | 'conflict'
}
