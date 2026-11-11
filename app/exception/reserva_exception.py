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


class ReservaEspacioNoDisponibleException(ReservaException):
    """Se lanza cuando el espacio no está en estado activo."""

    def __init__(self, espacio_id: int, estado: str):
        self.espacio_id = espacio_id
        self.estado = estado
        super().__init__(
            f"El espacio {espacio_id} no está disponible para reservas (estado: {estado})"
        )



class ReservaNoEncontradaException(ReservaException):
    """Se lanza cuando la reserva no existe."""

    def __init__(self, reserva_id: int):
        self.reserva_id = reserva_id
        super().__init__(f"Reserva {reserva_id} no encontrada")


class ReservaNoAutorizadaException(ReservaException):
    """Se lanza cuando un residente intenta operar una reserva ajena."""

    def __init__(self, reserva_id: int):
        self.reserva_id = reserva_id
        super().__init__("No autorizado para cancelar esta reserva")
