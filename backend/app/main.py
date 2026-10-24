from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.products import router as products_router

app = FastAPI(title="Shopping Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products_router)


@app.get("/health")
def health():
    return {"status": "ok"}