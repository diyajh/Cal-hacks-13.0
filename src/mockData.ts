import { AgentEvent, Outfit, Product, StyleSession } from './types'

const img = {
  crochet: 'https://images.unsplash.com/photo-1596755389378-c31d21fd1273?auto=format&fit=crop&w=900&q=85',
  skirt: 'https://images.unsplash.com/photo-1583496661160-fb5886a0aaaa?auto=format&fit=crop&w=900&q=85',
  linen: 'https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?auto=format&fit=crop&w=900&q=85',
  pants: 'https://images.unsplash.com/photo-1506629905607-d9f6c4d66b2f?auto=format&fit=crop&w=900&q=85',
  dress: 'https://images.unsplash.com/photo-1515372039744-b8f02a3ae446?auto=format&fit=crop&w=900&q=85',
  sneakers: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=900&q=85',
  bag: 'https://images.unsplash.com/photo-1594223274512-ad4803739b7c?auto=format&fit=crop&w=900&q=85',
}

const products: Record<string, Product> = {
  crochet: { id: 'crochet', name: 'Mira Crochet Tank', retailer: 'Reformation', price: 28, category: 'top', image: img.crochet, link: 'https://www.thereformation.com/search?q=Mira%20Crochet%20Tank', match: 97, note: 'Required detail' },
  skirt: { id: 'skirt', name: 'Linen Bias Midi Skirt', retailer: 'Everlane', price: 20, category: 'bottom', image: img.skirt, link: 'https://www.everlane.com/search?q=Linen%20Bias%20Midi%20Skirt', match: 95, note: 'Replacement found' },
  linen: { id: 'linen', name: 'Relaxed Linen Shirt', retailer: 'Quince', price: 24, category: 'top', image: img.linen, link: 'https://www.quince.com/search?q=Relaxed%20Linen%20Shirt', match: 93 },
  pants: { id: 'pants', name: 'Cream Wide-Leg Trouser', retailer: 'Abercrombie', price: 18, category: 'bottom', image: img.pants, link: 'https://www.abercrombie.com/shop/us/search?searchTerm=Cream%20Wide-Leg%20Trouser', match: 91 },
  dress: { id: 'dress', name: 'Soleil Cotton Dress', retailer: 'Faithfull', price: 38, category: 'dress', image: img.dress, link: 'https://faithfullthebrand.com/search?q=Soleil%20Cotton%20Dress', match: 94, note: 'Easy one-piece' },
  sneakers: { id: 'sneakers', name: 'White Leather Sneakers', retailer: 'Your wardrobe', price: 0, category: 'shoes', image: img.sneakers, link: '#', match: 100, owned: true, note: 'Already owned' },
  bag: { id: 'bag', name: 'Woven Market Tote', retailer: 'Madewell', price: 12, category: 'accessory', image: img.bag, link: 'https://www.madewell.com/search?q=Woven%20Market%20Tote', match: 89 },
}

const outfit = (o: Outfit): Outfit => o
export const demoSession: StyleSession = {
  session: 'aura-san-diego-001',
  parsedRequest: { destination: 'San Diego', dates: 'Aug 14 – 18', days: 5, aesthetic: 'Beachy / neutral', outfits: 5, perOutfitBudget: 50, totalBudget: 500, required: ['Crochet top + skirt'], avoid: ['Neon colors'], owned: ['White sneakers'] },
  styleDNA: [{ label: 'Minimal', value: 40, color: '#1d3530' }, { label: 'Coastal', value: 30, color: '#b7d6d1' }, { label: 'Boho', value: 20, color: '#d7a47f' }, { label: 'Classic', value: 10, color: '#ded8ce' }],
  outfits: [
    outfit({ id: 'day-1', day: 1, title: 'Salt air morning', setting: 'La Jolla · daytime', score: 94, scoreBreakdown: { style: 97, color: 96, occasion: 94, budget: 100, preference: 89 }, products: [products.crochet, products.skirt, products.sneakers], newSpend: 48, whyItWorks: 'The crochet texture brings your beachy brief to life, while the clean ivory palette feels polished without trying too hard.', accent: '#d8ebe7' }),
    outfit({ id: 'day-2', day: 2, title: 'Market to marina', setting: 'Little Italy · daytime', score: 92, scoreBreakdown: { style: 94, color: 93, occasion: 91, budget: 100, preference: 88 }, products: [products.linen, products.pants, products.sneakers], newSpend: 42, whyItWorks: 'Relaxed linen keeps you cool in the sun; a wide leg adds just enough shape for an afternoon that turns into dinner.', accent: '#f2e8d9' }),
    outfit({ id: 'day-3', day: 3, title: 'Golden hour', setting: 'Coronado · sunset', score: 96, scoreBreakdown: { style: 98, color: 96, occasion: 95, budget: 100, preference: 93 }, products: [products.dress, products.sneakers, products.bag], newSpend: 50, whyItWorks: 'A single beautiful silhouette gives you the elegant moment you asked for, with sneakers to keep the boardwalk practical.', accent: '#f5dfd1' }),
    outfit({ id: 'day-4', day: 4, title: 'Slow Sunday', setting: 'North Park · brunch', score: 91, scoreBreakdown: { style: 92, color: 95, occasion: 90, budget: 100, preference: 87 }, products: [products.linen, products.skirt], newSpend: 44, whyItWorks: 'An easy tonal pairing makes getting dressed feel effortless while still looking intentional for a long brunch.', accent: '#e9eee5' }),
    outfit({ id: 'day-5', day: 5, title: 'Last swim, late lunch', setting: 'Pacific Beach · daytime', score: 93, scoreBreakdown: { style: 95, color: 94, occasion: 92, budget: 100, preference: 90 }, products: [products.crochet, products.pants, products.sneakers], newSpend: 46, whyItWorks: 'The soft crochet layer works over swimwear, then keeps the same look going when you head straight to lunch.', accent: '#e8e6dc' }),
  ],
  totalCost: 228, newPurchaseCost: 228, ownedItems: [products.sneakers], reusedItems: [products.sneakers],
  agentEvents: [
    { id: 'e1', agent: 'UNDERSTANDING', title: 'Request parsed', detail: 'San Diego · 5 days · 5 outfits', status: 'done' },
    { id: 'e2', agent: 'STYLE AGENT', title: 'Aesthetic mapped', detail: 'Coastal neutrals with a soft boho edge', status: 'done' },
    { id: 'e3', agent: 'SEARCH AGENT', title: '74 products found', detail: 'Across 12 retailers and your wardrobe', status: 'done' },
    { id: 'e4', agent: 'BUDGET AGENT', title: 'One outfit rejected', detail: '$67 exceeded your $50 per-outfit limit', status: 'done' },
    { id: 'e5', agent: 'SEARCH AGENT', title: 'Lower-cost skirt found', detail: 'Replacement compatibility: strong', status: 'done' },
    { id: 'e6', agent: 'OUTFIT PLANNER', title: 'Trip plan ready', detail: '5 valid looks · $228 new spend', status: 'active' },
  ], constraintStatus: 'satisfied',
}
