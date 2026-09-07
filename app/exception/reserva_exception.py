class ReservaException(Exception):
    """Excepción base para errores de reservas."""
    pass


class ReservaSolapamientoException(ReservaException):
    """Se lanza cuando hay solapamiento de fechas."""

    def __init__(self, espacio_id: int, fecha_inicio: str, fecha_fin: str):
        self.espacio_id = espacio_id
        self.fecha_inicio = fecha_inicio
        self.fecha_fin = fecha_fin
        super().__init__(
            f"El espacio {espacio_id} ya está reservado en el rango {fecha_inicio} - {fecha_fin}"
        )


class ReservaFechaInvalidaException(ReservaException):
    """Se lanza cuando las fechas son inválidas."""

    def __init__(self, mensaje: str = "La fecha de fin debe ser posterior a la de inicio"):
        super().__init__(mensaje)

