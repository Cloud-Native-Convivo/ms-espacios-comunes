from sqlalchemy.ext.asyncio import AsyncSession

from app.exception.espacio_exception import EspacioNoEncontradoException
from app.model.modelos import Espacio
from app.repository import espacio_repository
from app.dto.esquemas import ActualizarEspacioRequest, CrearEspacioRequest


async def listar_todos(sesion: AsyncSession) -> list[Espacio]:
    return await espacio_repository.obtener_todos(sesion)

async def obtener_por_id(sesion: AsyncSession, espacio_id: int) -> Espacio | None:
    return await espacio_repository.obtener_por_id(sesion, espacio_id)

async def crear(sesion: AsyncSession, datos: CrearEspacioRequest) -> Espacio:
    espacio = Espacio(
        nombre=datos.nombre,
        capacidad=datos.capacidad,
        tarifa_hora=datos.tarifa_hora,
        descripcion=datos.descripcion,
        ubicacion=datos.ubicacion,
    )
    return await espacio_repository.crear(sesion, espacio)

async def actualizar(
    sesion: AsyncSession,
    espacio_id: int,
    datos: ActualizarEspacioRequest,
) -> Espacio | None:
    espacio = await espacio_repository.obtener_por_id(sesion, espacio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    if datos.nombre is not None:
        espacio.nombre = datos.nombre
    if datos.capacidad is not None:
        espacio.capacidad = datos.capacidad
    if datos.tarifa_hora is not None:
        espacio.tarifa_hora = datos.tarifa_hora
    if datos.descripcion is not None:
        espacio.descripcion = datos.descripcion
    if datos.ubicacion is not None:
        espacio.ubicacion = datos.ubicacion
    if datos.estado is not None:
        espacio.estado = datos.estado
    return await espacio_repository.actualizar(sesion, espacio)

async def eliminar(sesion: AsyncSession, espacio_id: int) -> str:
    espacio = await espacio_repository.obtener_por_id(sesion, espacio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    reservas_count = await espacio_repository.contar_reservas_asociadas(sesion, espacio_id)
    if reservas_count > 0:
        espacio.estado = "inactivo"
        await espacio_repository.actualizar(sesion, espacio)
        return "inactivado"
    else:
        await espacio_repository.eliminar_fisico(sesion, espacio)
        return "eliminado"
