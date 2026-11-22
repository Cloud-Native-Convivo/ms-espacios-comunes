class KafkaAdminException(Exception):
    """Error de una operación de administración de Kafka, con su código HTTP."""

    def __init__(self, estado: int, mensaje: str):
        self.estado = estado
        super().__init__(mensaje)
