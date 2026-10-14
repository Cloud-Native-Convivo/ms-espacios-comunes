import os

# Valores por defecto para ejecución de tests aislada (CI sin archivo .env)
os.environ.setdefault("DB_USERNAME", "test_user")
os.environ.setdefault("DB_PASSWORD", "test_pass")
os.environ.setdefault("RABBITMQ_USUARIO", "test_user")
os.environ.setdefault("RABBITMQ_CONTRASENA", "test_pass")
