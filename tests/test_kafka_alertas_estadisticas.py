"""Alertas (espacios.alertas.v1) y proyección de estadísticas, contra SQLite real.

Técnica: tabla de decisión para cuándo nace cada alerta (quién cancela x
dueño; estado de cada reserva al entrar en mantención), valores límite para
la ventana de RESERVA_POR_EXPIRAR (dentro / fuera de los 5 minutos) y de días
de la consulta (1 y 90 válidos, 0 y 91 no), y partición de equivalencia por
tipo de evento en la proyección.
"""

import asyncio
import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.dto.esquemas import ActualizarEspacioRequest
from app.dto.kafka_eventos import (
    TOPICO_ALERTAS,
    AlertaEspacioV1,
    DatosEventoEspacio,
    EventoEspacioV1,
)
from app.events import kafka_estadisticas
from app.events.expiracion_worker import alertar_por_expirar
from app.main import app
from app.model.modelos import (
    Base,
    Espacio,
    EstadisticaEspacio,
    EstadisticaEspacioDia,
    EventoOutboxKafka,
    Reserva,
)
from app.service import espacio_service, estadisticas_service, reserva_service
from app.util.tiempo import ahora_utc

CONDOMINIO = 7


@pytest_asyncio.fixture
async def fabrica():
    motor = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with motor.begin() as conexion:
        await conexion.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(motor, class_=AsyncSession, expire_on_commit=False)
    await motor.dispose()


async def _espacio(fabrica) -> int:
    async with fabrica() as sesion:
        espacio = Espacio(condominio_id=CONDOMINIO, nombre="Quincho", capacidad=10, estado="activo")
        sesion.add(espacio)
        await sesion.commit()
        return espacio.id


async def _reserva(fabrica, espacio_id, dueno="res-1", estado="activa", dias=1, expira_min=15) -> int:
    ahora = ahora_utc()
    async with fabrica() as sesion:
        reserva = Reserva(
            espacio_id=espacio_id,
            usuario_sub=dueno,
            fecha_inicio=ahora + datetime.timedelta(days=dias),
            fecha_fin=ahora + datetime.timedelta(days=dias, hours=2),
            estado=estado,
            monto_total=0,
            expira_en=ahora + datetime.timedelta(minutes=expira_min),
        )
        sesion.add(reserva)
        await sesion.commit()
        return reserva.id


async def _filas(fabrica, topico: str) -> list[EventoOutboxKafka]:
    async with fabrica() as sesion:
        consulta = (
            select(EventoOutboxKafka)
            .where(EventoOutboxKafka.topico == topico)
            .order_by(EventoOutboxKafka.id)
        )
        return list((await sesion.execute(consulta)).scalars().all())


async def _alertas(fabrica) -> list[AlertaEspacioV1]:
    filas = await _filas(fabrica, TOPICO_ALERTAS)
    assert all(f.clave == str(CONDOMINIO) for f in filas)
    return [AlertaEspacioV1.model_validate_json(f.carga_util) for f in filas]


# --- ESPACIO_EN_MANTENCION_CON_RESERVAS ---------------------------------------


async def test_mantencion_alerta_a_cada_reserva_vigente(fabrica):
    espacio_id = await _espacio(fabrica)
    activa = await _reserva(fabrica, espacio_id, dueno="res-1")
    pendiente = await _reserva(fabrica, espacio_id, dueno="res-2", estado="pendiente_pago", dias=2)
    await _reserva(fabrica, espacio_id, dueno="res-3", estado="cancelada", dias=3)
    await _reserva(fabrica, espacio_id, dueno="res-4", estado="pendiente_pago", dias=4, expira_min=-1)
    await _reserva(fabrica, espacio_id, dueno="res-5", dias=-1)  # ya terminó

    async with fabrica() as sesion:
        await espacio_service.actualizar(
            sesion, espacio_id, CONDOMINIO, ActualizarEspacioRequest(estado="mantenimiento"),
            actor_sub="admin-1",
        )
        await sesion.commit()

    alertas = await _alertas(fabrica)
    assert sorted((a.reserva_id, a.destinatario_sub) for a in alertas) == [
        (activa, "res-1"), (pendiente, "res-2"),
    ]
    origen = [
        EventoEspacioV1.model_validate_json(f.carga_util)
        for f in await _filas(fabrica, "espacios.historial.v1")
    ][-1]
    assert origen.tipo == "ESPACIO_EN_MANTENCION"
    assert {a.origen_event_id for a in alertas} == {origen.event_id}
    assert {a.tipo for a in alertas} == {"ESPACIO_EN_MANTENCION_CON_RESERVAS"}
    assert {a.severidad for a in alertas} == {"advertencia"}


async def test_mantencion_sin_reservas_no_alerta(fabrica):
    espacio_id = await _espacio(fabrica)
    async with fabrica() as sesion:
        await espacio_service.actualizar(
            sesion, espacio_id, CONDOMINIO, ActualizarEspacioRequest(estado="mantenimiento")
        )
        await sesion.commit()
    assert await _alertas(fabrica) == []


async def test_inactivar_con_reservas_no_es_alerta_de_mantencion(fabrica):
    espacio_id = await _espacio(fabrica)
    await _reserva(fabrica, espacio_id)
    async with fabrica() as sesion:
        await espacio_service.actualizar(
            sesion, espacio_id, CONDOMINIO, ActualizarEspacioRequest(estado="inactivo")
        )
        await sesion.commit()
    assert await _alertas(fabrica) == []


# --- RESERVA_CANCELADA_POR_ADMIN ----------------------------------------------


@pytest.mark.parametrize(
    ("actor", "privilegiado", "alerta"),
    [
        ("admin-1", True, True),    # admin cancela reserva ajena
        ("res-1", False, False),    # el dueño cancela la suya
        ("res-1", True, False),     # un admin cancela su propia reserva
        (None, False, False),       # la saga compensa (sin actor)
    ],
)
async def test_alerta_de_cancelacion_por_admin(fabrica, actor, privilegiado, alerta):
    espacio_id = await _espacio(fabrica)
    reserva_id = await _reserva(fabrica, espacio_id, dueno="res-1")
    async with fabrica() as sesion:
        await reserva_service.cancelar_por_id(
            sesion, reserva_id, actor_sub=actor, privilegiado=privilegiado
        )
        await sesion.commit()

    alertas = await _alertas(fabrica)
    assert len(alertas) == (1 if alerta else 0)
    if alerta:
        assert alertas[0].tipo == "RESERVA_CANCELADA_POR_ADMIN"
        assert alertas[0].destinatario_sub == "res-1"
        assert alertas[0].reserva_id == reserva_id
        assert "Quincho" in alertas[0].mensaje


async def test_cancelar_con_dueno_privilegiado_alerta_al_dueno(fabrica):
    espacio_id = await _espacio(fabrica)
    reserva_id = await _reserva(fabrica, espacio_id, dueno="res-1")
    async with fabrica() as sesion:
        await reserva_service.cancelar_con_dueno(sesion, reserva_id, "conserje-1", privilegiado=True)
        await sesion.commit()
    assert [a.tipo for a in await _alertas(fabrica)] == ["RESERVA_CANCELADA_POR_ADMIN"]


async def test_cancelar_reserva_ya_cancelada_no_alerta(fabrica):
    espacio_id = await _espacio(fabrica)
    reserva_id = await _reserva(fabrica, espacio_id, estado="cancelada")
    async with fabrica() as sesion:
        await reserva_service.cancelar_por_id(sesion, reserva_id, "admin-1", privilegiado=True)
        await sesion.commit()
    assert await _alertas(fabrica) == []


# --- RESERVA_POR_EXPIRAR ------------------------------------------------------


async def test_por_expirar_alerta_una_sola_vez_y_respeta_la_ventana(fabrica):
    espacio_id = await _espacio(fabrica)
    pronto = await _reserva(fabrica, espacio_id, estado="pendiente_pago", expira_min=3)
    await _reserva(fabrica, espacio_id, estado="pendiente_pago", dias=2, expira_min=10)
    await _reserva(fabrica, espacio_id, estado="activa", dias=3, expira_min=3)

    for _ in range(3):  # el worker pasa cada minuto sobre la misma reserva
        async with fabrica() as sesion:
            await alertar_por_expirar(sesion, ahora_utc())
            await sesion.commit()

    alertas = await _alertas(fabrica)
    assert [(a.tipo, a.reserva_id, a.severidad) for a in alertas] == [
        ("RESERVA_POR_EXPIRAR", pronto, "info")
    ]
    assert "expira en 3 min" in alertas[0].mensaje
    assert alertas[0].event_id == uuid.uuid5(
        uuid.NAMESPACE_URL, f"convivo:reserva-{pronto}-por-expirar"
    )


async def test_por_expirar_devuelve_cuantas_emitio(fabrica):
    espacio_id = await _espacio(fabrica)
    await _reserva(fabrica, espacio_id, estado="pendiente_pago", expira_min=1)
    async with fabrica() as sesion:
        assert await alertar_por_expirar(sesion, ahora_utc()) == 1
        await sesion.commit()
    async with fabrica() as sesion:
        assert await alertar_por_expirar(sesion, ahora_utc()) == 0


# --- Proyección de estadísticas -----------------------------------------------


def _evento(tipo, espacio_id=1, horas=None, estado_nuevo=None, cuando=None) -> EventoEspacioV1:
    inicio = datetime.datetime(2026, 11, 22, 18, tzinfo=datetime.UTC)
    return EventoEspacioV1(
        tipo=tipo,
        condominio_id=CONDOMINIO,
        espacio_id=espacio_id,
        reserva_id=1 if tipo.startswith("RESERVA") else None,
        ocurrido_en=cuando or datetime.datetime.now(datetime.UTC),
        datos=DatosEventoEspacio(
            estado_nuevo=estado_nuevo,
            fecha_inicio=inicio if horas else None,
            fecha_fin=inicio + datetime.timedelta(hours=horas) if horas else None,
        ),
    )


async def _procesar(fabrica, evento: EventoEspacioV1) -> bool:
    async with fabrica() as sesion:
        return await kafka_estadisticas.procesar_valor(sesion, evento.model_dump_json().encode())


async def _estado(fabrica, espacio_id=1) -> str:
    async with fabrica() as sesion:
        return (await sesion.get(EstadisticaEspacio, espacio_id)).estado


@pytest.mark.parametrize(
    ("eventos", "estado"),
    [
        ([("ESPACIO_CREADO", "activo")], "activo"),
        ([("ESPACIO_CREADO", "activo"), ("ESPACIO_EN_MANTENCION", None)], "mantenimiento"),
        ([("ESPACIO_EN_MANTENCION", None), ("ESPACIO_HABILITADO", None)], "activo"),
        ([("ESPACIO_DESHABILITADO", "inactivo")], "inactivo"),
        ([("ESPACIO_DESHABILITADO", "eliminado")], "eliminado"),
        ([("ESPACIO_EN_MANTENCION", None), ("ESPACIO_ACTUALIZADO", None)], "mantenimiento"),
        ([("RESERVA_CREADA", None)], "activo"),  # espacio anterior al PR 2
    ],
)
async def test_proyeccion_de_estado(fabrica, eventos, estado):
    for tipo, estado_nuevo in eventos:
        assert await _procesar(fabrica, _evento(tipo, estado_nuevo=estado_nuevo)) is True
    assert await _estado(fabrica) == estado


async def test_proyeccion_de_contadores_por_dia(fabrica):
    for evento in [
        _evento("RESERVA_CREADA"),
        _evento("RESERVA_CREADA"),
        _evento("RESERVA_CONFIRMADA", horas=2),
        _evento("RESERVA_CONFIRMADA", horas=1.5),
        _evento("RESERVA_CANCELADA"),
        _evento("RESERVA_EXPIRADA"),
    ]:
        await _procesar(fabrica, evento)

    async with fabrica() as sesion:
        hoy = datetime.datetime.now(datetime.UTC).date()
        dia = await sesion.get(EstadisticaEspacioDia, (1, hoy))
    assert (dia.reservas_creadas, dia.reservas_confirmadas) == (2, 2)
    assert (dia.reservas_canceladas, dia.reservas_expiradas) == (1, 1)
    assert Decimal(str(dia.horas_confirmadas)) == Decimal("3.5")


async def test_proyeccion_es_idempotente_por_event_id(fabrica):
    evento = _evento("RESERVA_CONFIRMADA", horas=2)
    assert await _procesar(fabrica, evento) is True
    assert await _procesar(fabrica, evento) is False

    async with fabrica() as sesion:
        dias = (await sesion.execute(select(EstadisticaEspacioDia))).scalars().all()
    assert [(d.reservas_confirmadas, float(d.horas_confirmadas)) for d in dias] == [(1, 2.0)]


async def test_mensaje_fuera_de_contrato_se_omite(fabrica):
    async with fabrica() as sesion:
        assert await kafka_estadisticas.procesar_valor(sesion, b'{"tipo":"X"}') is False
        assert (await sesion.execute(select(EstadisticaEspacio))).first() is None


async def test_consumidor_confirma_offset_despues_de_cada_mensaje(fabrica):
    mensajes = [MagicMock(value=_evento("ESPACIO_CREADO", estado_nuevo="activo").model_dump_json().encode())]
    consumidor = MagicMock()
    consumidor.start = AsyncMock()
    consumidor.stop = AsyncMock()
    consumidor.commit = AsyncMock()

    async def _iterar():
        for mensaje in mensajes:
            yield mensaje
        raise asyncio.CancelledError

    consumidor.__aiter__ = lambda _self: _iterar()
    with (
        patch.object(kafka_estadisticas, "AIOKafkaConsumer", return_value=consumidor) as clase,
        patch.object(kafka_estadisticas, "fabrica_sesiones", fabrica),
    ):
        with pytest.raises(asyncio.CancelledError):
            await kafka_estadisticas.consumidor_estadisticas.__wrapped__()

    assert clase.call_args.kwargs["enable_auto_commit"] is False
    assert clase.call_args.kwargs["group_id"] == kafka_estadisticas.GRUPO_ESTADISTICAS
    consumidor.commit.assert_awaited_once()
    consumidor.stop.assert_awaited_once()
    assert await _estado(fabrica) == "activo"


# --- Consultas de estadísticas ------------------------------------------------


async def _sembrar(fabrica):
    """3 espacios: el 1 y el 2 empatan en confirmadas (2 gana por horas), el 3 sin
    confirmadas; además una fila vieja (40 días) del espacio 3 fuera de la ventana."""
    hoy = datetime.datetime.now(datetime.UTC).date()
    ahora = datetime.datetime(2026, 11, 21)
    async with fabrica() as sesion:
        for espacio_id, estado in [(1, "activo"), (2, "mantenimiento"), (3, "eliminado")]:
            sesion.add(EstadisticaEspacio(
                espacio_id=espacio_id, condominio_id=CONDOMINIO, estado=estado, actualizado_en=ahora
            ))
        sesion.add(EstadisticaEspacio(espacio_id=9, condominio_id=99, estado="activo", actualizado_en=ahora))
        filas = [
            (1, hoy, 3, 2, 1, 0, "4"),
            (2, hoy, 2, 1, 0, 0, "5"),
            (2, hoy - datetime.timedelta(days=29), 1, 1, 0, 1, "1"),
            (3, hoy, 1, 0, 1, 0, "0"),
            (3, hoy - datetime.timedelta(days=40), 9, 9, 0, 0, "99"),
            (9, hoy, 5, 5, 0, 0, "50"),
        ]
        for espacio_id, fecha, creadas, confirmadas, canceladas, expiradas, horas in filas:
            sesion.add(EstadisticaEspacioDia(
                espacio_id=espacio_id, fecha=fecha,
                condominio_id=99 if espacio_id == 9 else CONDOMINIO,
                reservas_creadas=creadas, reservas_confirmadas=confirmadas,
                reservas_canceladas=canceladas, reservas_expiradas=expiradas,
                horas_confirmadas=Decimal(horas),
            ))
        await sesion.commit()


async def test_listar_respeta_ventana_y_condominio(fabrica):
    await _sembrar(fabrica)
    async with fabrica() as sesion:
        resultado = await estadisticas_service.listar(sesion, CONDOMINIO, 30)
    por_id = {r.espacio_id: r for r in resultado}
    assert sorted(por_id) == [1, 2, 3]
    assert (por_id[1].disponible, por_id[2].disponible, por_id[3].disponible) == (True, False, False)
    assert (por_id[2].reservas_confirmadas, por_id[2].horas_confirmadas) == (2, 6.0)
    assert por_id[3].reservas_creadas == 1  # la fila de hace 40 días no entra


async def test_ventana_de_un_dia_excluye_dias_anteriores(fabrica):
    await _sembrar(fabrica)
    async with fabrica() as sesion:
        resultado = await estadisticas_service.listar(sesion, CONDOMINIO, 1)
    assert {r.espacio_id: r.reservas_confirmadas for r in resultado} == {1: 2, 2: 1, 3: 0}


async def test_preferidos_por_confirmadas_con_desempate_por_horas(fabrica):
    await _sembrar(fabrica)
    async with fabrica() as sesion:
        ranking = await estadisticas_service.preferidos(sesion, CONDOMINIO, 30, 5)
        top1 = await estadisticas_service.preferidos(sesion, CONDOMINIO, 30, 1)
    assert [(r.espacio_id, r.reservas_confirmadas, r.horas_confirmadas) for r in ranking] == [
        (2, 2, 6.0), (1, 2, 4.0),
    ]
    assert [r.espacio_id for r in top1] == [2]


def test_desde_incluye_hoy():
    hoy = datetime.date(2026, 11, 21)
    assert estadisticas_service._desde(1, hoy) == hoy
    assert estadisticas_service._desde(30, hoy) == datetime.date(2026, 10, 23)


# --- Endpoints ----------------------------------------------------------------


@pytest_asyncio.fixture
async def cliente():
    servicio = AsyncMock()
    servicio.listar.return_value = []
    servicio.preferidos.return_value = []
    with patch("app.api.v1.estadisticas_router.estadisticas_service", servicio):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, servicio


@pytest.mark.parametrize("rol", ["admin", "conserje", "residente"])
async def test_endpoint_permite_los_tres_roles(cliente, rol):
    c, servicio = cliente
    r = await c.get(
        "/api/v1/estadisticas/espacios",
        params={"condominio_id": CONDOMINIO},
        headers={"X-Usuario-Roles": rol},
    )
    assert r.status_code == 200
    assert servicio.listar.await_args.args[1:] == (CONDOMINIO, 30)


async def test_endpoint_sin_rol_es_403(cliente):
    c, _ = cliente
    r = await c.get("/api/v1/estadisticas/espacios", params={"condominio_id": CONDOMINIO})
    assert r.status_code == 403


@pytest.mark.parametrize(("dias", "codigo"), [(0, 422), (1, 200), (90, 200), (91, 422)])
async def test_endpoint_limites_de_ventana(cliente, dias, codigo):
    c, _ = cliente
    r = await c.get(
        "/api/v1/estadisticas/espacios/preferidos",
        params={"condominio_id": CONDOMINIO, "dias": dias},
        headers={"X-Usuario-Roles": "admin"},
    )
    assert r.status_code == codigo


async def test_endpoint_preferidos_pasa_limite(cliente):
    c, servicio = cliente
    r = await c.get(
        "/api/v1/estadisticas/espacios/preferidos",
        params={"condominio_id": CONDOMINIO, "limite": 3},
        headers={"X-Usuario-Roles": "residente"},
    )
    assert r.status_code == 200
    assert servicio.preferidos.await_args.args[1:] == (CONDOMINIO, 30, 3)
