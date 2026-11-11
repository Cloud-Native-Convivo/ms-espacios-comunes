"""Consumidor de comandos contra una base real (SQLite en memoria).

Los tests con sesion simulada (test_comandos_consumer.py) no ven el problema
de fondo: un rollback() borra los cambios no confirmados, incluido el job
recien creado. Aqui cada comando se procesa con una sesion real y el job se
lee despues desde una sesion nueva, como lo hace GET /jobs/{ticket}.
"""

import datetime
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.events.comandos_consumer import procesar_comando_mutacion
from app.exception.reserva_exception import ReservaSolapamientoException
from app.model.modelos import Base, Espacio, Reserva
from app.model.solicitud_job import SolicitudJob

CONDOMINIO = 1
OTRO_CONDOMINIO = 2


@pytest_asyncio.fixture
async def fabrica():
    motor = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    await motor.dispose()


async def _sembrar_espacio(fabrica, condominio_id=CONDOMINIO, nombre="Quincho"):
    async with fabrica() as sesion:
        espacio = Espacio(
            condominio_id=condominio_id, nombre=nombre, capacidad=10, tarifa_hora=0
        )
        sesion.add(espacio)
        await sesion.commit()
        return espacio.id


async def _procesar(fabrica, comando):
    async with fabrica() as sesion:
        await procesar_comando_mutacion(sesion, comando)


async def _job(fabrica, ticket_id):
    async with fabrica() as sesion:
        return await sesion.get(SolicitudJob, ticket_id)


async def _espacio(fabrica, espacio_id):
    async with fabrica() as sesion:
        return await sesion.get(Espacio, espacio_id)


def _comando(ticket_id, accion, payload=None, **extra):
    return {
        "ticket_id": ticket_id,
        "modulo": "ESPACIOS",
        "accion": accion,
        "usuario_id": "admin-1",
        "rol": "admin",
        "payload": payload or {},
        **extra,
    }


def _error(job):
    return json.loads(job.error)


# --- El job FALLIDO debe sobrevivir al rollback ---


@pytest.mark.asyncio
async def test_accion_desconocida_deja_job_fallido_consultable(fabrica):
    await _procesar(fabrica, _comando("t-desconocida", "ACCION_QUE_NO_EXISTE"))

    job = await _job(fabrica, "t-desconocida")
    assert job is not None, "el rollback borro el job: /jobs/{ticket} daria 404"
    assert job.estado == "FALLIDO"
    assert _error(job)["codigo"] == "VALIDACION_NEGOCIO"
    assert _error(job)["status_code"] == 400


@pytest.mark.asyncio
async def test_solapamiento_deja_job_fallido_409(fabrica):
    comando = _comando(
        "t-solape",
        "CREAR_RESERVA",
        {
            "espacio_id": 1,
            "fecha_inicio": "2026-10-15T18:00:00Z",
            "fecha_fin": "2026-10-15T20:00:00Z",
        },
    )
    solape = ReservaSolapamientoException(
        1, "2026-10-15T18:00:00Z", "2026-10-15T20:00:00Z"
    )
    with patch(
        "app.events.comandos_consumer.reserva_service.crear",
        new=AsyncMock(side_effect=solape),
    ):
        await _procesar(fabrica, comando)

    job = await _job(fabrica, "t-solape")
    assert job is not None
    assert job.estado == "FALLIDO"
    assert _error(job)["codigo"] == "CONFLICTO_SOLAPAMIENTO"
    assert _error(job)["status_code"] == 409


@pytest.mark.asyncio
async def test_error_interno_deja_job_fallido_sin_filtrar_detalle(fabrica):
    comando = _comando(
        "t-interno",
        "CREAR_RESERVA",
        {
            "espacio_id": 1,
            "fecha_inicio": "2026-10-15T18:00:00Z",
            "fecha_fin": "2026-10-15T20:00:00Z",
        },
    )
    with patch(
        "app.events.comandos_consumer.reserva_service.crear",
        new=AsyncMock(side_effect=RuntimeError("ORA-12541 host=10.0.3.7")),
    ):
        await _procesar(fabrica, comando)

    job = await _job(fabrica, "t-interno")
    assert job is not None
    assert job.estado == "FALLIDO"
    assert _error(job)["codigo"] == "ERROR_INTERNO"
    assert _error(job)["status_code"] == 500
    assert "ORA-12541" not in job.error
    assert "10.0.3.7" not in job.error


@pytest.mark.asyncio
async def test_fallo_no_deja_cambios_de_la_accion_pero_si_el_job(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    comando = _comando(
        "t-parcial",
        "ACTUALIZAR_ESPACIO",
        {"nombre": "Nuevo", "estado": "valor-invalido"},
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    assert (await _espacio(fabrica, espacio_id)).nombre == "Quincho"
    assert (await _job(fabrica, "t-parcial")).estado == "FALLIDO"


@pytest.mark.asyncio
async def test_job_exitoso_queda_completado_con_resultado(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    comando = _comando(
        "t-ok",
        "ACTUALIZAR_ESPACIO",
        {"nombre": "Quincho norte"},
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    job = await _job(fabrica, "t-ok")
    assert job.estado == "COMPLETADO"
    assert job.error is None
    assert json.loads(job.resultado) == {"id": espacio_id, "nombre": "Quincho norte"}


# --- Editar y eliminar espacios: ids desde el comando ---


@pytest.mark.asyncio
async def test_actualizar_espacio_usa_ids_del_comando(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    comando = _comando(
        "t-put",
        "ACTUALIZAR_ESPACIO",
        {"nombre": "Sala de eventos", "capacidad": 40},
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    espacio = await _espacio(fabrica, espacio_id)
    assert (espacio.nombre, espacio.capacidad) == ("Sala de eventos", 40)
    assert (await _job(fabrica, "t-put")).estado == "COMPLETADO"


@pytest.mark.asyncio
async def test_espacio_id_del_payload_no_pisa_al_del_comando(fabrica):
    propio = await _sembrar_espacio(fabrica, nombre="Propio")
    ajeno = await _sembrar_espacio(fabrica, nombre="Ajeno")
    comando = _comando(
        "t-pisa",
        "ACTUALIZAR_ESPACIO",
        {"nombre": "Cambiado", "espacio_id": ajeno},
        espacio_id=propio,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    assert (await _espacio(fabrica, propio)).nombre == "Cambiado"
    assert (await _espacio(fabrica, ajeno)).nombre == "Ajeno"


@pytest.mark.asyncio
async def test_modificar_espacio_aplica_solo_los_campos_enviados(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    comando = _comando(
        "t-patch",
        "MODIFICAR_ESPACIO",
        {"estado": "mantenimiento"},
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    espacio = await _espacio(fabrica, espacio_id)
    assert espacio.estado == "mantenimiento"
    assert (espacio.nombre, espacio.capacidad) == ("Quincho", 10)
    assert (await _job(fabrica, "t-patch")).estado == "COMPLETADO"


@pytest.mark.asyncio
async def test_actualizar_espacio_de_otro_condominio_falla_404(fabrica):
    espacio_id = await _sembrar_espacio(fabrica, condominio_id=OTRO_CONDOMINIO)
    comando = _comando(
        "t-ajeno",
        "ACTUALIZAR_ESPACIO",
        {"nombre": "Robado"},
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    assert (await _espacio(fabrica, espacio_id)).nombre == "Quincho"
    job = await _job(fabrica, "t-ajeno")
    assert job.estado == "FALLIDO"
    assert _error(job)["codigo"] == "NO_ENCONTRADO"
    assert _error(job)["status_code"] == 404


@pytest.mark.asyncio
async def test_eliminar_espacio_sin_reservas_lo_borra(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    comando = _comando(
        "t-del",
        "ELIMINAR_ESPACIO",
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    assert await _espacio(fabrica, espacio_id) is None
    job = await _job(fabrica, "t-del")
    assert job.estado == "COMPLETADO"
    assert json.loads(job.resultado) == {
        "espacio_id": espacio_id,
        "eliminado": True,
        "resultado": "eliminado",
    }


@pytest.mark.asyncio
async def test_eliminar_espacio_con_reservas_lo_inactiva_y_lo_informa(fabrica):
    espacio_id = await _sembrar_espacio(fabrica)
    async with fabrica() as sesion:
        sesion.add(
            Reserva(
                espacio_id=espacio_id,
                usuario_sub="res-1",
                fecha_inicio=datetime.datetime(2026, 10, 15, 18),
                fecha_fin=datetime.datetime(2026, 10, 15, 20),
            )
        )
        await sesion.commit()
    comando = _comando(
        "t-inact",
        "ELIMINAR_ESPACIO",
        espacio_id=espacio_id,
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    assert (await _espacio(fabrica, espacio_id)).estado == "inactivo"
    resultado = json.loads((await _job(fabrica, "t-inact")).resultado)
    assert resultado["eliminado"] is False
    assert resultado["resultado"] == "inactivado"


@pytest.mark.asyncio
@pytest.mark.parametrize("accion", ["ACTUALIZAR_ESPACIO", "MODIFICAR_ESPACIO", "ELIMINAR_ESPACIO"])
@pytest.mark.parametrize(
    "ids",
    [
        {},
        {"espacio_id": 1},
        {"condominio_id": CONDOMINIO},
        {"espacio_id": 0, "condominio_id": CONDOMINIO},
        {"espacio_id": "1", "condominio_id": CONDOMINIO},
        {"espacio_id": 1, "condominio_id": -3},
    ],
)
async def test_ids_faltantes_o_invalidos_dejan_job_fallido_400(fabrica, accion, ids):
    comando = _comando("t-ids", accion, {"nombre": "X"}, **ids)

    await _procesar(fabrica, comando)

    job = await _job(fabrica, "t-ids")
    assert job is not None
    assert job.estado == "FALLIDO"
    assert _error(job)["codigo"] == "VALIDACION_NEGOCIO"


# --- Crear espacio: el condominio del comando manda sobre el del payload ---


@pytest.mark.asyncio
async def test_crear_espacio_usa_condominio_del_comando(fabrica):
    comando = _comando(
        "t-crear",
        "CREAR_ESPACIO",
        {"nombre": "Piscina", "capacidad": 20, "condominio_id": OTRO_CONDOMINIO},
        condominio_id=CONDOMINIO,
    )

    await _procesar(fabrica, comando)

    async with fabrica() as sesion:
        espacios = (await sesion.execute(select(Espacio))).scalars().all()
    assert [(e.nombre, e.condominio_id) for e in espacios] == [("Piscina", CONDOMINIO)]
    assert (await _job(fabrica, "t-crear")).estado == "COMPLETADO"


@pytest.mark.asyncio
async def test_crear_espacio_sin_condominio_en_el_comando_usa_el_del_payload(fabrica):
    comando = _comando(
        "t-crear-legacy",
        "CREAR_ESPACIO",
        {"nombre": "Gimnasio", "capacidad": 15, "condominio_id": OTRO_CONDOMINIO},
    )

    await _procesar(fabrica, comando)

    async with fabrica() as sesion:
        espacio = (await sesion.execute(select(Espacio))).scalar_one()
    assert espacio.condominio_id == OTRO_CONDOMINIO
