from app.exception.espacio_exception import EspacioNoEncontradoException
from app.model.modelos import Espacio
from app.repository.espacio_repository import EspacioRepository


class EspacioService:
    def __init__(self, repo: EspacioRepository):
        self._repo = repo

    async def listar_todos(self) -> list[Espacio]:
        return await self._repo.obtener_todos()

    async def obtener_por_id(self, espacio_id: int) -> Espacio | None:
        return await self._repo.obtener_por_id(espacio_id)

    async def crear(
        self,
        nombre: str,
        capacidad: int,
        tarifa_hora: float = 0.0,
        descripcion: str | None = None,
        ubicacion: str | None = None,
    ) -> Espacio:
        espacio = Espacio(
            nombre=nombre,
            capacidad=capacidad,
            tarifa_hora=tarifa_hora,
            descripcion=descripcion,
            ubicacion=ubicacion,
        )
        return await self._repo.crear(espacio)

    async def actualizar(
        self,
        espacio_id: int,
        nombre: str | None = None,
        capacidad: int | None = None,
        tarifa_hora: float | None = None,
        descripcion: str | None = None,
        ubicacion: str | None = None,
        estado: str | None = None,
    ) -> Espacio | None:
        espacio = await self._repo.obtener_por_id(espacio_id)
        if not espacio:
            raise EspacioNoEncontradoException(espacio_id)
        if nombre is not None:
            espacio.nombre = nombre
        if capacidad is not None:
            espacio.capacidad = capacidad
        if tarifa_hora is not None:
            espacio.tarifa_hora = tarifa_hora
        if descripcion is not None:
            espacio.descripcion = descripcion
        if ubicacion is not None:
            espacio.ubicacion = ubicacion
        if estado is not None:
            espacio.estado = estado
        return await self._repo.actualizar(espacio)
