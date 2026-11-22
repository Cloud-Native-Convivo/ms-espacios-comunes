from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings

# pool_pre_ping: tras un reinicio de Oracle descarta la conexión muerta del pool
# en vez de colgar la primera petición.
motor = create_async_engine(
    settings.url_base_datos, echo=settings.modo_debug, pool_pre_ping=True
)

fabrica_sesiones = async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)


async def obtener_sesion() -> AsyncGenerator[AsyncSession, None]:
    async with fabrica_sesiones.begin() as sesion:
        yield sesion
