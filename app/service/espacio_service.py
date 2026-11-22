from sqlalchemy.ext.asyncio import AsyncSession

from app.dto.esquemas import ActualizarEspacioRequest, CrearEspacioRequest
from app.events import kafka_outbox
from app.exception.espacio_exception import EspacioNoEncontradoException
from app.model.modelos import Espacio
from app.repository import espacio_repository, reserva_repository
from app.util.tiempo import ahora_utc

_CAMPOS_EDITABLES = ("nombre", "capacidad", "tarifa_hora", "descripcion", "ubicacion")


async def listar_todos(sesion: AsyncSession, condominio_id: int) -> list[Espacio]:
    return await espacio_repository.obtener_todos(sesion, condominio_id)

async def obtener_por_id(sesion: AsyncSession, espacio_id: int, condominio_id: int) -> Espacio | None:
    return await espacio_repository.obtener_por_id(sesion, espacio_id, condominio_id)

async def crear(
    sesion: AsyncSession, datos: CrearEspacioRequest, actor_sub: str | None = None
) -> Espacio:
    espacio = Espacio(
        condominio_id=datos.condominio_id,
        nombre=datos.nombre,
        capacidad=datos.capacidad,
        tarifa_hora=datos.tarifa_hora,
        descripcion=datos.descripcion,
        ubicacion=datos.ubicacion,
    )
    espacio = await espacio_repository.crear(sesion, espacio)
    kafka_outbox.registrar_evento_espacio(
        sesion, "ESPACIO_CREADO", espacio, actor_sub, estado_nuevo=espacio.estado or "activo"
    )
    return espacio

def _cambio(actual, nuevo) -> bool:
    # tarifa_hora llega de Oracle como Decimal: se compara como float.
    if isinstance(nuevo, float) and actual is not None:
        return float(actual) != nuevo
    return actual != nuevo

async def actualizar(
    sesion: AsyncSession,
    espacio_id: int,
    condominio_id: int,
    datos: ActualizarEspacioRequest,
    actor_sub: str | None = None,
) -> Espacio | None:
    espacio = await espacio_repository.obtener_por_id(sesion, espacio_id, condominio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    campos_cambiados = False
    for campo in _CAMPOS_EDITABLES:
        nuevo = getattr(datos, campo)
        if nuevo is not None and _cambio(getattr(espacio, campo), nuevo):
            setattr(espacio, campo, nuevo)
            campos_cambiados = True
    estado_anterior = espacio.estado
    estado_cambiado = datos.estado is not None and datos.estado != estado_anterior
    if estado_cambiado:
        espacio.estado = datos.estado

    if campos_cambiados:
        kafka_outbox.registrar_evento_espacio(sesion, "ESPACIO_ACTUALIZADO", espacio, actor_sub)
    if estado_cambiado:
        evento = kafka_outbox.registrar_evento_espacio(
            sesion,
            kafka_outbox.TIPO_POR_ESTADO_ESPACIO[datos.estado],
            espacio,
            actor_sub,
            estado_anterior=estado_anterior,
            estado_nuevo=datos.estado,
        )
        if datos.estado == "mantenimiento":
            await _alertar_reservas_afectadas(sesion, espacio, evento.event_id)
    return await espacio_repository.actualizar(sesion, espacio)

async def _alertar_reservas_afectadas(sesion: AsyncSession, espacio: Espacio, origen_event_id) -> None:
    """Una alerta por cada reserva vigente del espacio que entra en mantención."""
    for reserva in await reserva_repository.obtener_futuras_vigentes(sesion, espacio.id, ahora_utc()):
        kafka_outbox.registrar_alerta(
            sesion,
            "ESPACIO_EN_MANTENCION_CON_RESERVAS",
            "advertencia",
            reserva,
            espacio.condominio_id,
            f"El espacio {espacio.nombre} entró en mantención. Tu reserva #{reserva.id} "
            "podría verse afectada; revisa con la administración.",
            origen_event_id=origen_event_id,
        )

async def eliminar(
    sesion: AsyncSession, espacio_id: int, condominio_id: int, actor_sub: str | None = None
) -> str:
    espacio = await espacio_repository.obtener_por_id(sesion, espacio_id, condominio_id)
    if not espacio:
        raise EspacioNoEncontradoException(espacio_id)
    estado_anterior = espacio.estado
    reservas_count = await espacio_repository.contar_reservas_asociadas(sesion, espacio_id)
    if reservas_count > 0:
        espacio.estado = "inactivo"
        if estado_anterior != "inactivo":
            kafka_outbox.registrar_evento_espacio(
                sesion, "ESPACIO_DESHABILITADO", espacio, actor_sub,
                estado_anterior=estado_anterior, estado_nuevo="inactivo",
            )
        await espacio_repository.actualizar(sesion, espacio)
        return "inactivado"
    # "eliminado" le indica al consumidor de estadísticas que lo saque de la disponibilidad.
    kafka_outbox.registrar_evento_espacio(
        sesion, "ESPACIO_DESHABILITADO", espacio, actor_sub,
        estado_anterior=estado_anterior, estado_nuevo="eliminado",
    )
    await espacio_repository.eliminar_fisico(sesion, espacio)
    return "eliminado"
