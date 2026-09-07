import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Espacio(Base):
    __tablename__ = "espacios"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacidad: Mapped[int] = mapped_column(Integer, nullable=False)
    tarifa_hora: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0.0
    )
    ubicacion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activo")
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    actualizado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    reservas: Mapped[list["Reserva"]] = relationship(back_populates="espacio")


class Reserva(Base):
    __tablename__ = "reservas"
    __table_args__ = (
        Index("ix_reservas_espacio_fechas", "espacio_id", "fecha_inicio", "fecha_fin"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    espacio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("espacios.id"), nullable=False
    )
    usuario_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_inicio: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente_pago"
    )
    monto_total: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0.0
    )
    expira_en: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    espacio: Mapped["Espacio"] = relationship(back_populates="reservas")


class EventoOutbox(Base):
    __tablename__ = "eventos_outbox"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    tipo_evento: Mapped[str] = mapped_column(String(100), nullable=False)
    carga_util: Mapped[str] = mapped_column(Text, nullable=False)
    procesado: Mapped[bool] = mapped_column(default=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
