import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_health_from_main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"estado": "ok"}
