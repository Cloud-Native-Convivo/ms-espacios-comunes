class EspacioException(Exception):
    """Excepción base para errores de espacios."""
    pass


class EspacioNoEncontradoException(EspacioException):
    """Se lanza cuando no se encuentra un espacio."""

    def __init__(self, espacio_id: int):
        self.espacio_id = espacio_id
        super().__init__(f"Espacio {espacio_id} no encontrado")
