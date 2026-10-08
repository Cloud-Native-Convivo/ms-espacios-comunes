import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from app.api.v1.health_router import router

app_test = FastAPI()
app_test.include_router(router)

async def test_health_direct():
    async with AsyncClient(transport=ASGITransport(app=app_test), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        assert response.json() == {"estado": "ok"}
