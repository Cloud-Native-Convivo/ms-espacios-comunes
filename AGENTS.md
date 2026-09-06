# AGENTS.md — ms-espacios-comunes

Microservicio de espacios comunes y reservas para Convivo. API REST en Python/FastAPI con Oracle DB y publicación de eventos vía RabbitMQ (Outbox pattern).

**Para el agente que trabaje en este microservicio:**

- Sin emojis en código, PR, docs generadas ni output — usar solo como último recurso si no existe alternativa real.
- En commits rige Gitmoji (§11.2) — ahí el emoji es obligatorio por convención.
- Nada de solución genérica de tutorial. Cada decisión responde a Convivo y al ERS/MVP.
- Todo en español: funciones, variables, archivos, comentarios, mensajes de error.

## 0. Jerarquía de reglas

1. Seguridad y corrección — nunca se sacrifican por ninguna otra regla.
2. Convenciones del proyecto (stack, estilo, arquitectura) — se siguen salvo instrucción explícita en contrario.
3. Minimalismo (Ponytail) — se aplica solo después de satisfacer 1 y 2.

## 1. Resumen del proyecto

`ms-espacios-comunes` es un microservicio del dominio de Convivo (plataforma de gestión de condominios en Chile). Expone una API REST para CRUD de espacios comunes (salas, quinchos, piscinas, etc.) y gestión de reservas con validación de overlap temporal. Publica eventos de dominio vía RabbitMQ usando el patrón Outbox para garantizar entrega at-least-once. Se registra en Eureka para descubrimiento de servicios.

Roles: residente (reserva), admin (gestiona espacios), conserje (consulta). La validación de JWT y resolución de roles la hace el BFF — este servicio solo recibe `X-Usuario-Sub` como header.

## 2. Stack técnico

- Lenguaje: Python 3.11
- Framework: FastAPI 0.115+ (con Uvicorn)
- ORM: SQLAlchemy 2.0 (async) + oracledb (thin mode)
- Base de datos: Oracle Database Free 23ai (`espacios_db`)
- Mensajería: aio-pika 10.x (RabbitMQ 4, patrón Outbox)
- Descubrimiento: py-eureka-client
- Configuración: pydantic-settings (env vars/`.env`) + fetch best-effort a Spring Cloud Config al arrancar (`app/config/settings.py:cargar_configuracion_remota`) — completa solo variables ausentes localmente, config-server caído no bloquea el arranque
- Tests: pytest + pytest-asyncio
- Contenedores: Docker + docker-compose

## 3. Estructura del proyecto

```text
app/
  main.py                  # FastAPI app + lifespan (Eureka, background tasks)
  api/
    router.py              # Agregador de routers v1
    v1/
      espacio_router.py    # Endpoints de espacios
      reserva_router.py    # Endpoints de reservas
      health_router.py     # Endpoint de health check
  config/
    settings.py            # Pydantic Settings (env vars) + fetch best-effort a config-server
    database.py            # Session factory async (SQLAlchemy + oracledb)
  dto/
    request/
      espacio_request.py   # Esquemas de entrada para espacios
      reserva_request.py   # Esquemas de entrada para reservas
    response/
      espacio_response.py  # Esquemas de salida para espacios
      reserva_response.py  # Esquemas de salida para reservas
  model/
    modelos.py             # Modelos SQLAlchemy (Espacio, Reserva, EventoOutbox)
  repository/
    interfaces/
      espacio_repository_interface.py  # Interfaz abstracta
      reserva_repository_interface.py
    espacio_repository.py  # Acceso a DB
    reserva_repository.py
  service/
    espacio_service.py     # Lógica de negocio
    reserva_service.py
  exception/
    reserva_exception.py   # Excepciones de reservas
    espacio_exception.py   # Excepciones de espacios
  handler/
    exception_handler.py   # Manejadores FastAPI
  events/
    outbox_event.py        # Relay Outbox → RabbitMQ
    compensacion_consumer.py  # Consumidor de compensación
    steps/
      publicar_evento.py
      compensar_reserva.py
  middleware/
    logging_middleware.py   # Logging de requests
tests/
  unit/
    test_reserva_service.py
  integration/
    test_reserva_routes.py
  e2e/
```

## 4. Comandos

```bash
# instalar dependencias (incluye dev)
pip install -e ".[dev]"

# test completo
pytest tests/ -v

# test acotado a un archivo
pytest tests/test_reserva_servicio.py -v

# levantar local (sin dependencias externas)
uvicorn app.main:app --host 0.0.0.0 --port 8082 --reload

# levantar con docker-compose (Oracle + RabbitMQ + servicio)
docker compose up --build

# verificar build Docker
docker build -t ms-espacios-comunes .
```

## 5. Estilo de código

**Todo en español**: nombres de funciones (`crear_reserva`, `obtener_espacio_por_id`), variables (`fecha_inicio`, `espacio_id`), archivos (`espacio_repositorio.py`), mensajes de error, comentarios.

Patrones obligatorios:

```python
# async/await en toda la capa de servicios y repositorios
async def crear_reserva(db: AsyncSession, reserva: ReservaCrear) -> Reserva:
    overlap = await reserva_repositorio.verificar_overlap(db, reserva)
    if overlap:
        raise ValueError("El espacio ya está reservado en ese horario")
    return await reserva_repositorio.crear(db, reserva)

# Queries parametrizadas — nunca concatenar input de usuario
stmt = select(Espacio).where(Espacio.id == espacio_id)
resultado = await db.execute(stmt)
```

- Snake_case para todo (funciones, variables, archivos).
- Type hints en todas las funciones públicas.
- Docstrings en español en servicios y repositorios (qué hace, no cómo).
- Sin clases de más: Router → Service → Repository, no MVC.
- Imports ordenados: stdlib → third-party → locale. Ruff I001 (isort) como regla mínima.

## 6. Disciplina anti-sobreingeniería (Ponytail)

Configuración global del agente — no duplicar aquí. Aplica a código nuevo a escribir, no autoriza podar documentación existente.

## 7. Pruebas

Cobertura mínima: 60% (del EDT). Framework: pytest + pytest-asyncio. Ubicación: `tests/` con estructura espejo del código fuente.

Cobertura por tipo:

| Tipo     | Qué garantiza                        | Cuándo exigirla                          |
| -------- | ------------------------------------ | ---------------------------------------- |
| Línea    | la línea se ejecutó                  | piso mínimo                              |
| Rama     | cada rama de condicional se tomó     | default para lógica con `if`/`switch`    |
| Mutación | el test falla si se altera la lógica | solo en núcleo crítico (overlap, outbox) |

Tests existentes (8/8 pasando):
- `test_reserva_servicio.py`: 3 tests (creación, overlap, espacio inexistente)
- `test_reserva_rutas.py`: 2 tests (POST /reservas/, GET /reservas/)
- `test_config_server.py`: 3 tests (esquema no permitido rechazado sin request, config-server caído no lanza excepción, solo completa variables ausentes sin pisar `.env`)

Tests inestables: política — arreglar inmediato, no "correr de nuevo hasta que pase".

```python
# Ejemplo: test de overlap
async def test_crear_reserva_con_overlap(db_mock):
    await crear_reserva(db_mock, reserva_1)
    with pytest.raises(ValueError, match="ya está reservado"):
        await crear_reserva(db_mock, reserva_2)
```

## 8. Métricas de claridad

`(no aplica: microservicio CRUD, sin lógica compleja que justifique métricas formales)`

## 9. Procedimientos QA

Checklist pre-entrega: tests en verde, linter limpio, type checking sin errores, sin secrets hardcodeados, queries parametrizadas, documentación actualizada.

| Severidad | Acción                   |
| --------- | ------------------------ |
| Crítico   | bloquea el merge         |
| Mayor     | corregir antes del merge |
| Menor     | issue post-merge         |

## 10. Seguridad

Secretos en variables de entorno (`.env` para local, Secrets Manager en prod). Nunca en código ni en logs.

**OWASP Top 10:2025 — alcance real en este proyecto:**

- **A01 Control de acceso roto (SSRF)**: `CONFIG_SERVER_URL` (env var) determina a qué host se hace el fetch de configuración al arrancar — se valida que el esquema sea `http`/`https` antes de la petición (`cargar_configuracion_remota`, rechaza `file://` y similares), pero no se valida el host: alguien con control sobre esa env var podría apuntar a otro destino HTTP/HTTPS interno. Riesgo acotado (env var, no input de request), documentado por transparencia. Aparte, la autorización de negocio la resuelve el BFF: este servicio valida que `X-Usuario-Sub` exista y lo usa para ownership de reservas. No confiar en el cliente para autorización.
- **A02 Configuración insegura**: sin debug en prod, CORS configurado por el BFF, sin headers de seguridad ausentes.
- **A03 Fallos de cadena de suministro**: dependencias con lockfile (`requirements.txt` o `pyproject.toml`), sin CVEs conocidos.
- **A04 Fallos criptográficos**: sin crypto propia, secretos en env vars.
- **A05 Inyección**: queries parametrizadas siempre (SQLAlchemy ORM), nunca concatenar input de usuario.
- **A06 Diseño inseguro**: threat model básico cubierto por ERS/MVP (§4.6 Auth dual).
- **A07 Fallos de autenticación**: delegado al BFF + Cognito/Entra ID. Sin passwords en este servicio.
- **A08 Fallos de integridad**: sin deserialización de input no confiable más allá de Pydantic.
- **A09 Fallos de logging**: eventos de seguridad loggeados (intentos no autorizados), sin datos sensibles en log.
- **A10 Condiciones excepcionales**: errores no filtran stack trace al cliente, HTTP 500 genérico.

`(no aplica: sin superficie LLM)`

## 11. Commits y PR

Conventional Commits v1.0.0 + Gitmoji. Formato: `:emoji: <tipo>(<alcance>)?(!)?: <sujeto>`.

- Idioma: sujeto/cuerpo/footer en español; tipo siempre en inglés (estándar commitlint).
- Sujeto: imperativo presente, minúsculas, sin punto final, ≤72 chars (ideal ≤50). Detalle en el cuerpo.
- Alcance opcional, kebab-case del área tocada: `espacios`, `reservas`, `eventos`, `api`, `db`, `docker`, `deps`, `ci` — omitir si es transversal.
- Cuerpo: tras línea en blanco, qué y por qué, no cómo.
- Footer: tras línea en blanco; `Closes #N`/`Fixes #N`; breaking con `BREAKING CHANGE:` o sufijo `!`.
- Nunca agregar `Co-Authored-By`, firma de agente/IA, ni enlaces de sesión a un commit o PR, salvo pedido explícito del usuario para ese commit puntual.

### 11.0 Reglas de la spec (MUST)

- Header: tipo + alcance opcional + `:` + espacio + sujeto.
- `feat` para funcionalidad nueva, `fix` para corrección de bug.
- Cuerpo: qué y por qué, nunca cómo.
- Footer: `Closes #N` / `Fixes #N` para issues.
- Breaking change: footer `BREAKING CHANGE:` o `!` antes de `:`.

### 11.1 Reglas del proyecto

- Sujeto/cuerpo en español, tipo en inglés.
- Sujeto: imperativo presente, minúsculas, sin punto, ≤72 chars.
- Alcance: lista cerrada — `espacios`, `reservas`, `eventos`, `api`, `db`, `docker`, `deps`, `ci`.
- Enforcement: sin commitlint instalado — el agente valida manualmente.

### 11.2 Gitmoji (adoptado)

Formato: `:emoji: <tipo>(<alcance>)?: <sujeto>`

**Prioridad de selección de emoji (menor a mayor):**

1. **Por defecto según tipo** (gitmoji.dev):

| Tipo       | Emoji |
| ---------- | ----- |
| `feat`     | ✨     |
| `fix`      | 🐛     |
| `docs`     | 📝     |
| `style`    | 🎨     |
| `refactor` | ♻️     |
| `perf`     | ⚡️     |
| `test`     | ✅     |
| `build`    | 📦️     |
| `ci`       | 👷     |
| `chore`    | 🔧     |
| `revert`   | ⏪️     |

2. **Específico del catálogo** si encaja mejor: 💥 breaking, 🎉 inicio proyecto, 🔥 quitar código, 💫 animaciones/transiciones, 💄 UI, 🔒️ seguridad, 🚀 deploy, ⬆️/⬇️ dependencias, 🙈 gitignore.

3. **Personalizado libre** si el significado no es ambiguo.

**Versionado semántico:** `feat` → MINOR, `fix` → PATCH. Breaking en cualquier tipo → MAJOR (footer `BREAKING CHANGE:` o `!` antes de `:`).

**Ejemplos:**
```
:bug: fix(a11y): agrega track de captions al audio de fondo
:recycle: refactor(ts): migra el proyecto de JavaScript a TypeScript
:sparkles: feat(a11y): reemplaza emojis por iconos lucide-react en JSX y toasts
```

### 11.3 Ramas (Git Flow completo — modelo Driessen)

```
main    ●─────●───────────●───────●──────────●───►
         ▲(tag v1.0) ▲(tag v1.0.1)      ▲(tag v1.1.0)
         │  merge    │ merge             │  merge
  release/1.0.0          │        release/1.1.0
       ▲                 │             ▲
       │  merge          │hotfix/1.0.1 │  merge
develop ●──●───●───●──────●─────●───────●───●───►
          \   \   \            \       /
      feature/a  feature/b   feature/c
```

**Ramas permanentes:** `main` (producción, siempre tagueada), `develop` (integración).

**Ramas de soporte:**

| Tipo        | Nace de   | Mergea a           | Naming                      |
| ----------- | --------- | ------------------ | --------------------------- |
| `feature/*` | `develop` | `develop`          | `feature/descripcion-corta` |
| `release/*` | `develop` | `main` + `develop` | `release/x.y.z`             |
| `hotfix/*`  | `main`    | `main` + `develop` | `hotfix/descripcion-corta`  |
| `support/*` | tag vieja | solo a sí misma    | `support/1.x`               |

`--no-ff` siempre. Sin force-push a `main`/`develop`. Sin commit directo a `main`/`develop`.

## 12. Límites del agente

**Siempre** (sin pedir permiso): editar código, tests, docs dentro del repo; crear commits locales.

**Preguntar primero**: force-push, `git reset --hard`, agregar/actualizar dependencias, deploy a staging.

**Nunca sin aprobación explícita**:
- Migraciones de DB aplicadas.
- Configuración de CI/CD.
- Archivos de secretos o `.env`.
- Deploy a producción.
- Borrado de datos: `DROP`, `TRUNCATE`, `DELETE` sin `WHERE`.

## 13. Deploy

```bash
# local con docker-compose (Oracle + RabbitMQ + servicio)
docker compose up --build

# producción (ECS Fargate via Terraform)
# ver despliegue-ecs-fargate.md en la raíz del workspace
cd ../terraform
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars  # requiere aprobación explícita
```

## 14. Monorepo

Este microservicio es parte del workspace Convivo. El `AGENTS.md` de la raíz del workspace (`cloud-native/AGENTS.md`) define reglas transversales (infraestructura, Trello, etc.). Este archivo gana sobre ese para código dentro de `ms-espacios-comunes/`.

## 15. Enforcement

Orientativo, no forzado mecánicamente. Las reglas críticas (secretos, queries parametrizadas) deben reforzarse con CI, no depender solo de este texto.

| Regla          | Hook local | CI              | Solo texto        |
| -------------- | ---------- | --------------- | ----------------- |
| Secretos (§10) | —          | escaneo en CI   | —                 |
| Formato (§5)   | —          | linter en CI    | —                 |
| Cobertura (§7) | —          | umbral 60% gate | —                 |
| Commits (§11)  | —          | —               | validación manual |

## 16. Mantenimiento

Tratar como código. Revisar cada sprint o trimestral. Si la normativa declarada en §17 cambia de alcance, revisar en esa pasada.

## 17. Normativa y cumplimiento

Normas que aplican: ISO/IEC 27001 (controles técnicos) + Ley 21.719 (datos personales de residentes en Chile).

### 17.1 ISO/IEC 25010

`(no aplica: microservicio backend sin interfaz propia — los atributos de interacción y usabilidad los determina el frontend)`

### 17.2 ISO/IEC 27001 — SGSI

| Propiedad        | Control mínimo                                                                 | Evidencia                         |
| ---------------- | ------------------------------------------------------------------------------ | --------------------------------- |
| Confidencialidad | secretos en env vars, datos de residentes cifrados en tránsito (HTTPS via BFF) | `.env.example` sin valores reales |
| Integridad       | queries parametrizadas, validación Pydantic en cada endpoint                   | código fuente de repositorios     |
| Disponibilidad   | health check `/health`, reintentos de conexión a DB                            | endpoint de health                |

Controles del Anexo A aplicables:

| Control                            | Dónde vive                                             |
| ---------------------------------- | ------------------------------------------------------ |
| A.8.3 Restricción de acceso        | `X-Usuario-Sub` header, ownership validado en servicio |
| A.8.5 Autenticación segura         | delegada al BFF (Cognito/Entra ID)                     |
| A.8.8 Gestión de vulnerabilidades  | dependencias con lockfile, sin CVEs                    |
| A.8.10 Eliminación de información  | política de retención de reservas (definida en ERS)    |
| A.8.12 Prevención de fuga de datos | sin PII en logs, sin stack traces al cliente           |
| A.8.15/A.8.16 Registro y monitoreo | eventos Outbox con estado, logs de seguridad           |

### 17.3 ISO 9001 / IEEE 730 / ISO/IEC/IEEE 29119

`(no aplica: sin proceso formal de pruebas documentado — cobertura de §7 es métrica interna)`

### 17.4 Cruce con normativa chilena

| Norma         | Ley chilena                                                            | Punto de cruce         | Qué exige en este repo                                                                                 |
| ------------- | ---------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------ |
| ISO/IEC 27001 | **Ley 21.719** (datos personales, entrada en force original 1-12-2026) | cifrado y trazabilidad | inventario de datos personales tratados (RAT), log de acceso, procedimiento de notificación de brechas |
| ISO/IEC 25010 | Ley 21.180 (transformación digital)                                    | interoperabilidad      | interoperabilidad vía API REST + contratos OpenAPI                                                     |

**Ley 21.719 — plazo real:** la APDP no está operativa al 2026 — el gobierno evalúa postergar a 2027. Si Convivo trata datos personales de residentes, el trabajo de cumplimiento se planifica antes de la entrada en force efectiva.

Obligaciones técnicas:

| Obligación                                   | Implicación en código                                     |
| -------------------------------------------- | --------------------------------------------------------- |
| RAT (Registro de Actividades de Tratamiento) | inventario de qué datos personales toca cada endpoint     |
| Derechos ARCO + portabilidad                 | endpoint de exportación de datos de un residente (futuro) |
| Notificación de brechas                      | procedimiento de respuesta a incidentes (futuro)          |
