from pydantic import BaseModel
from typing import List, Optional


class Product(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    price: float
    currency: str = "USD"
    retailer: str
    image_url: Optional[str] = None
    product_url: str
    description: Optional[str] = None
    colors: List[str] = []
    tags: List[str] = []
    available: bool = True
    source: str


class ProductSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    colors: List[str] = []
    tags: List[str] = []
    max_price: Optional[float] = None
    limit: int = 20
