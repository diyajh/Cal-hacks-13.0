from pydantic import BaseModel


class Product(BaseModel):
    id: str
    name: str
    category: str | None = None
    price: float
    currency: str = "USD"
    retailer: str
    image_url: str | None = None
    product_url: str
    description: str | None = None
    colors: list[str] = []
    tags: list[str] = []
    available: bool = True
    source: str


class ProductSearchRequest(BaseModel):
    query: str
    category: str | None = None
    colors: list[str] = []
    tags: list[str] = []
    max_price: float | None = None
    limit: int = 20