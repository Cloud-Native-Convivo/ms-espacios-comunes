import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.model.modelos import Base


class SolicitudJob(Base):
    __tablename__ = "solicitudes_jobs"
    __table_args__ = (
        Index("idx_jobs_usuario", "usuario_id", "creado_en"),
    )

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    modulo: Mapped[str] = mapped_column(String(30), nullable=False)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)
    usuario_id: Mapped[str] = mapped_column(String(100), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="EN_COLA"
    )  # EN_COLA, PROCESANDO, COMPLETADO, FALLIDO
    resultado: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    actualizado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
