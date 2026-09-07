# ms-espacios-comunes

Microservicio de gestión de espacios comunes y reservas para la plataforma Convivo.

---

## Descripción

`ms-espacios-comunes` es un microservicio del dominio de Convivo (plataforma de gestión de condominios) desarrollado en Python 3.11+ sobre FastAPI. Administra el catálogo de espacios comunes de una comunidad (quinchos, salas de eventos, piscinas, canchas) y procesa el ciclo de vida de las reservas utilizando un flujo Saga en dos fases con bloqueo temporal (TTL de 15 minutos) y tarificación por hora.

### Arquitectura y Componentes
- **Framework API**: FastAPI 0.115+ en modo asíncrono gestionado con servidor ASGI Uvicorn.
- **Persistencia**: Oracle Database Free 23ai conectada mediante SQLAlchemy 2.0 (motor asíncrono) y `oracledb` en modo thin.
- **Gestión de Esquema**: Alembic 1.14+ configurado para migraciones asíncronas sobre Oracle.
- **Mensajería y Eventos**: RabbitMQ 4 (AMQP 0-9-1) mediante `aio-pika`. Implementa el patrón Transactional Outbox para publicación confiable y un consumidor de eventos de compensación (`gasto.pago.fallido`) ante fallos en la pasarela de pagos.
- **Descubrimiento y Configuración**: Registro en Spring Cloud Netflix Eureka mediante `py-eureka-client`. Carga inicial de variables con Pydantic Settings con resolución defensiva hacia Spring Cloud Config Server sin bloqueo de arranque si el servidor remoto no responde.
- **Seguridad y Control de Acceso**: Control de acceso basado en roles (RBAC) desacoplado a través de cabeceras HTTP inyectadas por el API Gateway / BFF (`X-Usuario-Sub`, `X-Usuario-Roles`). Middleware de cabeceras de seguridad (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) y manejador global de excepciones no controladas sanitizado.

---

## Sintaxis / Interfaz

### 1. Variables de Entorno

El microservicio utiliza variables de entorno leídas por `app/config/settings.py`. Pueden definirse en un archivo `.env` en la raíz del proyecto o ser inyectadas por el orquestador de contenedores.

| Variable | Tipo | Valor por Defecto | Descripción |
|---|---|---|---|
| `DB_HOST` | `str` | `localhost` | Host o nombre del contenedor del servicio Oracle |
| `DB_PORT` | `int` | `1521` | Puerto del listener de Oracle Database |
| `DB_NAME` | `str` | `freepdb1` | Nombre del servicio o Pluggable Database (PDB) |
| `DB_USERNAME` | `str` | `admin` | Usuario de base de datos con permisos en el esquema |
| `DB_PASSWORD` | `str` | *(vacío)* | Contraseña del usuario de base de datos |
| `RABBITMQ_HOST` | `str` | `localhost` | Host o nombre del contenedor RabbitMQ |
| `RABBITMQ_PORT` | `int` | `5672` | Puerto del protocolo AMQP de RabbitMQ |
| `RABBITMQ_USUARIO` | `str` | `guest` | Usuario de autenticación en RabbitMQ |
| `RABBITMQ_CONTRASENA` | `str` | `guest` | Contraseña de autenticación en RabbitMQ |
| `EUREKA_URL` | `str` | `http://localhost:8761/eureka/` | URL base del servidor Eureka Discovery |
| `EUREKA_IP` | `str` | `127.0.0.1` | IP con la que el servicio se registra ante Eureka |
| `EUREKA_PORT` | `int` | `8082` | Puerto publicado en el registro de Eureka |
| `PUERTO` | `int` | `8082` | Puerto HTTP donde escucha la aplicación Uvicorn |
| `MODO_DEBUG` | `bool` | `false` | Habilita logs detallados si se encuentra en `true` |
| `CONFIG_SERVER_URL` | `str` | `http://localhost:8888` | URL de Spring Cloud Config Server (solo esquemas http/https) |

### 2. Cabeceras HTTP Requeridas

El microservicio delega la validación criptográfica de JWT al BFF y consume la identidad autenticada mediante cabeceras HTTP:

| Cabecera | Requerida | Formato | Descripción |
|---|---|---|---|
| `X-Usuario-Sub` | Sí (en reservas) | `str` (UUID o sub de Cognito/Auth) | Identificador único del usuario emisor de la petición |
| `X-Usuario-Roles` | Opcional (evaluada por RBAC) | `str` (separado por comas) | Lista de roles asignados al usuario (ej. `residente`, `admin`, `conserje`) |

### 3. Contratos de la API REST (`/api/v1`)

#### Salud del Sistema
- `GET /api/v1/health`
  - Descripción: Endpoint de verificación de operatividad para sondas Liveness/Readiness.
  - Respuesta: `200 OK` -> `{"estado": "ok"}`

#### Espacios Comunes (`/api/v1/espacios`)
- `GET /api/v1/espacios/`
  - Descripción: Retorna la lista de todos los espacios comunes registrados.
  - Respuesta: `200 OK` -> `list[EspacioResponse]`
- `GET /api/v1/espacios/{espacio_id}`
  - Descripción: Consulta los detalles de un espacio específico por su identificador numérico.
  - Parámetros: `espacio_id: int` (en ruta).
  - Respuesta: `200 OK` -> `EspacioResponse`
- `POST /api/v1/espacios/`
  - Descripción: Da de alta un nuevo espacio común.
  - Autorización: Requiere rol `admin` en `X-Usuario-Roles`.
  - Cuerpo: `CrearEspacioRequest`
    - `nombre: str` (longitud 1 a 200)
    - `capacidad: int` (entero >= 1)
    - `tarifa_hora: float` (decimal >= 0.0, valor por defecto `0.0`)
    - `descripcion: str | None` (opcional)
    - `ubicacion: str | None` (opcional)
  - Respuesta: `201 Created` -> `EspacioResponse`
- `PUT /api/v1/espacios/{espacio_id}`
  - Descripción: Actualiza los campos de un espacio común existente.
  - Autorización: Requiere rol `admin` en `X-Usuario-Roles`.
  - Cuerpo: `ActualizarEspacioRequest`
  - Respuesta: `200 OK` -> `EspacioResponse`

#### Reservas (`/api/v1/reservas`)
- `POST /api/v1/reservas/`
  - Descripción: Inicia el proceso de reserva de un espacio en estado `pendiente_pago` con ventana TTL de 15 minutos.
  - Autorización: Requiere rol `residente` o `admin`, y cabecera `X-Usuario-Sub`.
  - Cuerpo: `CrearReservaRequest`
    - `espacio_id: int`
    - `fecha_inicio: datetime` (ISO 8601 en zona UTC o local sin zona)
    - `fecha_fin: datetime` (ISO 8601, posterior a `fecha_inicio`)
  - Respuesta: `201 Created` -> `ReservaResponse`
    - `id: int`
    - `espacio_id: int`
    - `usuario_sub: str`
    - `fecha_inicio: datetime`
    - `fecha_fin: datetime`
    - `estado: str` (`"pendiente_pago"`)
    - `monto_total: float`
    - `expira_en: datetime`
    - `creado_en: datetime`
- `GET /api/v1/reservas/`
  - Descripción: Lista reservas. Si el usuario cuenta con roles `admin` o `conserje`, obtiene todas las reservas registradas. Si posee rol `residente`, retorna únicamente las reservas vinculadas a su `X-Usuario-Sub`.
  - Respuesta: `200 OK` -> `list[ReservaResponse]`
- `POST /api/v1/reservas/{reserva_id}/confirmar-pago`
  - Descripción: Confirma el pago de una reserva pendiente, transicionando su estado a `confirmada` y limpiando la expiración (`expira_en = null`).
  - Autorización: Requiere rol `admin` en `X-Usuario-Roles`.
  - Parámetros: `reserva_id: int` (en ruta).
  - Respuesta: `200 OK` -> `ReservaResponse`

### 4. Topología de Mensajería (RabbitMQ)

- **Exchange**: `convivo.eventos` (Direct / Topic).
- **Evento emitido**: `reserva.creada`
  - Carga útil JSON:
    ```json
    {
      "reserva_id": 1,
      "espacio_id": 10,
      "usuario_sub": "auth0|123456",
      "fecha_inicio": "2026-10-15T18:00:00",
      "fecha_fin": "2026-10-15T22:00:00",
      "monto_total": 40000.0,
      "expira_en": "2026-10-15T01:15:00"
    }
    ```
- **Cola de consumo de compensación**: `ms-espacios-comunes.compensacion`
  - Routing key de escucha: `gasto.pago.fallido`
  - Efecto: cancela la reserva asociada y libera el cupo de horario.

---

## Ejemplo de uso

### Requisitos Previos
1. Git instalado.
2. Docker Engine 24+ y Docker Compose v2+.
3. Python 3.11 o 3.12 (en caso de ejecución nativa fuera de contenedor).

---

### Opción A: Inicialización con Docker Compose (Recomendada)

Docker Compose orquesta el microservicio junto a Oracle Database 23ai Free y RabbitMQ en una red puente externa compartida (`convivo-network`).

1. **Crear la red externa compartida de Docker (si no existe)**:
   ```bash
   docker network create convivo-network
   ```

2. **Verificar o crear el archivo de variables `.env`**:
   ```bash
   cp .env.example .env
   ```
   Asegurar que los valores coincidan con los nombres de servicio en `docker-compose.yml`:
   ```properties
   DB_HOST=oracle-espacios
   DB_PORT=1521
   DB_NAME=freepdb1
   DB_USERNAME=system
   DB_PASSWORD=oracle123
   RABBITMQ_HOST=rabbitmq-espacios
   RABBITMQ_PORT=5672
   RABBITMQ_USUARIO=guest
   RABBITMQ_CONTRASENA=guest
   PUERTO=8082
   ```

3. **Construir y levantar todos los servicios**:
   ```bash
   docker compose up --build -d
   ```

4. **Verificar el estado de salud de los contenedores**:
   ```bash
   docker compose ps
   ```
   *Nota: Oracle 23ai demora entre 30 y 60 segundos en reportar estado `healthy` durante su inicialización inicial.*

5. **Revisar logs en tiempo real**:
   ```bash
   docker compose logs -f ms-espacios-comunes
   ```

6. **Detener los servicios**:
   ```bash
   docker compose down
   ```
   *(Para remover volúmenes de datos: `docker compose down -v`)*

---

### Opción B: Inicialización Local para Desarrollo

Permite ejecutar el código de FastAPI directamente en la máquina anfitriona mientras las dependencias de infraestructura (Oracle y RabbitMQ) corren en Docker.

1. **Levantar únicamente la infraestructura**:
   ```bash
   docker compose up -d oracle-espacios rabbitmq
   ```

2. **Crear y activar un entorno virtual de Python**:
   - En Linux/macOS:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   - En Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

3. **Instalar dependencias del proyecto y de pruebas**:
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

4. **Configurar el archivo `.env` local**:
   Asegurar que `DB_HOST=localhost` y `RABBITMQ_HOST=localhost`.

5. **Aplicar migraciones de base de datos con Alembic**:
   ```bash
   alembic upgrade head
   ```

6. **Iniciar el servidor Uvicorn con recarga en caliente**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload
   ```

---

### Ejecución de Pruebas Automatizadas

El proyecto cuenta con una suite integral de 31 pruebas unitarias y de integración que cubren validaciones horarias, tarificación, bloqueos pesimistas, tareas en segundo plano y RBAC:

```bash
# Ejecutar todas las pruebas con salida detallada
pytest tests/ -v

# Ejecutar una suite específica
pytest tests/test_reserva_rutas.py -v

# Validar formato y calidad de código con Ruff
ruff check .
```

---

### Ejemplos de Consumo con `curl`

#### 1. Verificar estado del servicio (Health Check)
```bash
curl -X GET http://localhost:8082/api/v1/health
```
Respuesta esperada:
```json
{"estado": "ok"}
```

#### 2. Crear un espacio común (Requiere rol `admin`)
```bash
curl -X POST http://localhost:8082/api/v1/espacios/ \
  -H "Content-Type: application/json" \
  -H "X-Usuario-Roles: admin" \
  -d '{
    "nombre": "Quincho Principal",
    "capacidad": 25,
    "tarifa_hora": 10000.00,
    "descripcion": "Parrilla completa y refrigerador",
    "ubicacion": "Azotea Torre A"
  }'
```

#### 3. Consultar catálogo de espacios comunes
```bash
curl -X GET http://localhost:8082/api/v1/espacios/
```

#### 4. Crear una reserva (Rol `residente`, dos fases, TTL 15 minutos)
```bash
curl -X POST http://localhost:8082/api/v1/reservas/ \
  -H "Content-Type: application/json" \
  -H "X-Usuario-Sub: usr-residente-42" \
  -H "X-Usuario-Roles: residente" \
  -d '{
    "espacio_id": 1,
    "fecha_inicio": "2026-11-20T19:00:00",
    "fecha_fin": "2026-11-20T23:00:00"
  }'
```
Respuesta esperada (`201 Created`):
```json
{
  "id": 1,
  "espacio_id": 1,
  "usuario_sub": "usr-residente-42",
  "fecha_inicio": "2026-11-20T19:00:00",
  "fecha_fin": "2026-11-20T23:00:00",
  "estado": "pendiente_pago",
  "monto_total": 40000.0,
  "expira_en": "2026-09-07T02:05:00",
  "creado_en": "2026-09-07T01:50:00"
}
```

#### 5. Confirmar pago de una reserva (Requiere rol `admin`)
```bash
curl -X POST http://localhost:8082/api/v1/reservas/1/confirmar-pago \
  -H "X-Usuario-Roles: admin"
```

---

## Errores, Excepciones y Efectos Secundarios

### Catálogo de Errores HTTP

| Código HTTP | Motivo | Detalle en Payload |
|---|---|---|
| `400 Bad Request` | Parámetros de reserva inválidos | `fecha_fin debe ser posterior a fecha_inicio`, `No se pueden realizar reservas en el pasado`, o `La duración de la reserva no puede exceder 24 horas` |
| `403 Forbidden` | Control RBAC insatisfecho | `Acceso denegado: se requiere uno de los siguientes roles: ['admin']` |
| `404 Not Found` | Recurso no encontrado | `Espacio con ID {id} no encontrado` o `Reserva no encontrada` |
| `409 Conflict` | Solapamiento de horario | `El espacio ya se encuentra reservado en el horario seleccionado` |
| `422 Unprocessable Entity` | Error de validación Pydantic | Lista de campos que no satisfacen tipos o restricciones |
| `500 Internal Server Error` | Excepción interna no controlada | `{"detalle": "Error interno del servidor"}` (sin filtración de trazas) |

### Efectos Secundarios en Segundo Plano

1. **Relay de Outbox Transaccional (`relay_outbox`)**:
   - Tarea asíncrona iniciada en el arranque de la aplicación (`lifespan`).
   - Sondea la tabla `eventos_outbox` cada 2 segundos.
   - Si existen eventos pendientes, se conecta a RabbitMQ y los publica al exchange `convivo.eventos` con política de reintentos exponenciales gestionada por Tenacity.
   - Tras la confirmación del broker, marca el evento con estado `procesado` en base de datos.

2. **Worker de Expiración de Cupos (`worker_expiracion`)**:
   - Tarea asíncrona iniciada en el arranque de la aplicación (`lifespan`).
   - Ejecuta un barrido cada 60 segundos sobre la tabla `reservas`.
   - Identifica todas las reservas con estado `pendiente_pago` cuya fecha `expira_en` sea anterior al tiempo actual (`datetime.now(timezone.utc)`).
   - Transiciona automáticamente dichas reservas a estado `cancelada`, liberando el cupo horario para otros residentes.

3. **Consumidor de Compensación de Fallos (`consumidor_compensacion`)**:
   - Tarea asíncrona iniciada en el arranque de la aplicación (`lifespan`).
   - Mantiene una suscripción activa sobre la cola `ms-espacios-comunes.compensacion`.
   - Procesa eventos `gasto.pago.fallido` emitidos por el microservicio de pagos y cancela la reserva asociada de forma transaccional.
