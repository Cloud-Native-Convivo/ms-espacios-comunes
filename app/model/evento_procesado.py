import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.model.modelos import Base


class EventoProcesado(Base):
    __tablename__ = "eventos_procesados"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumidor: Mapped[str] = mapped_column(String(100), primary_key=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    actualizado_en: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
