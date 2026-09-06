import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Espacio(Base):
    __tablename__ = "espacios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    capacidad: Mapped[int] = mapped_column(Integer, nullable=False)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espacio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("espacios.id"), nullable=False
    )
    usuario_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_inicio: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="activa")
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    espacio: Mapped["Espacio"] = relationship(back_populates="reservas")


class EventoOutbox(Base):
    __tablename__ = "eventos_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_evento: Mapped[str] = mapped_column(String(100), nullable=False)
    carga_util: Mapped[str] = mapped_column(Text, nullable=False)
    procesado: Mapped[bool] = mapped_column(default=False)
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
