from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import devices, quotes, stores
from app.api.v1.admin import auth as admin_auth
from app.api.v1.admin import competitor_prices as admin_competitor_prices
from app.api.v1.admin import devices as admin_devices
from app.api.v1.admin import payouts as admin_payouts
from app.api.v1.admin import price_sync as admin_price_sync
from app.api.v1.admin import questionnaire as admin_questionnaire
from app.api.v1.admin import quotes as admin_quotes
from app.core.config import settings

app = FastAPI(title="Phone Trade-In Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(devices.router, prefix="/api/v1")
app.include_router(quotes.router, prefix="/api/v1")
app.include_router(stores.router, prefix="/api/v1")

ADMIN_PREFIX = "/api/v1/admin"
app.include_router(admin_auth.router, prefix=ADMIN_PREFIX)
app.include_router(admin_devices.router, prefix=ADMIN_PREFIX)
app.include_router(admin_questionnaire.router, prefix=ADMIN_PREFIX)
app.include_router(admin_quotes.router, prefix=ADMIN_PREFIX)
app.include_router(admin_payouts.router, prefix=ADMIN_PREFIX)
app.include_router(admin_competitor_prices.router, prefix=ADMIN_PREFIX)
app.include_router(admin_price_sync.router, prefix=ADMIN_PREFIX)
