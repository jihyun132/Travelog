from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.core.exceptions import register_exception_handlers
from app.routers import auth, diaries, explore, globe, health, photos, places, trips, users

app = FastAPI(title="travelog API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(trips.router, prefix="/api/v1")
app.include_router(places.trip_places_router, prefix="/api/v1")
app.include_router(places.router, prefix="/api/v1")
app.include_router(globe.router, prefix="/api/v1")
app.include_router(photos.router, prefix="/api/v1")
app.include_router(diaries.router, prefix="/api/v1")
app.include_router(explore.router, prefix="/api/v1")

handler = Mangum(app)
