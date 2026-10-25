export type ProductCategory = 'top' | 'bottom' | 'dress' | 'layer' | 'outerwear' | 'shoes' | 'accessory'

export interface StyleDNA { label: string; value: number; color: string }
export interface ParsedRequest {
  destination: string; dates: string; days: number; aesthetic: string; outfits: number
  perOutfitBudget: number; totalBudget: number; required: string[]; avoid: string[]; owned: string[]
}
export interface Product {
  id: string; name: string; retailer: string; price: number; category: ProductCategory
  image: string; link: string; owned?: boolean; match: number; note?: string
  source?: 'wardrobe' | 'candidate'; decision?: ProductDecision
}
export interface Outfit {
  id: string; day: number; title: string; setting: string; score: number
  scoreBreakdown: { style: number; color: number; occasion: number; budget: number; preference: number }
  products: Product[]; newSpend: number; whyItWorks: string; accent: string
}
export interface AgentEvent { id: string; agent: string; title: string; detail: string; status: 'done' | 'active' }
export interface SessionConflict { status: 'needs_user_input' | string; message: string; conflictingConstraints: string[]; options: Array<string | { label?: string; value?: string; message?: string }> }
export interface StyleSession {
  session: string; parsedRequest: ParsedRequest; styleDNA: StyleDNA[]; outfits: Outfit[]
  totalCost: number; newPurchaseCost: number; ownedItems: Product[]; reusedItems: Product[]
  agentEvents: AgentEvent[]; constraintStatus: 'satisfied' | 'conflict'; conflict?: SessionConflict
  wardrobeReusedCount?: number; candidateReusedCount?: number; uniquePurchaseCount?: number; purchasesAvoided?: number; wardrobeValueAvoided?: number
}
export interface WardrobeItem {
  category: string; subcategory: string; color: string; pattern: string; material: string
  subtype?: string; style: string; formality: string; confidence: number
  id?: string; name?: string; image?: string; image_url?: string; source?: 'wardrobe'
  memory_type?: 'temporary' | 'remembered'; expires_at?: string | null
}
export interface ProductDecision {
  verdict: 'BUY' | 'SKIP' | 'INSUFFICIENT_WARDROBE_DATA' | string
  confidence: number; duplication_score: number; outfits_unlocked: number
  budget_impact: number | null; reason: string; matched_items: WardrobeItem[]; missing_information: string[]
}
export interface LiveStatus {
  vision: boolean; apify: boolean; cartesia: boolean; fetch: boolean
}
export interface StyleProfile {
  shopping_fit: 'mens' | 'womens' | 'unisex' | 'prefer_not_to_say' | null
  preferred_styles: string[]; preferred_colors: string[]; avoided_colors: string[]
  usual_size: string; default_budget_per_outfit: number | null
  preference_tags: string[]
}
