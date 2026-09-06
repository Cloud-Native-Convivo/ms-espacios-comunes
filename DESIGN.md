# DESIGN.md — ms-espacios-comunes

Backend microservice — sin interfaz gráfica propia. Las decisiones de diseño visual (tipografía, color, spacing, componentes) viven en el `DESIGN.md` del frontend que consume esta API (`Frontend-CloudNative/` o `panel-administracion-web/`).

---

## 1. Tipografía

`(no aplica: microservicio backend sin UI)`

## 2. Color

`(no aplica: microservicio backend sin UI)`

## 3. Spacing y tamaños

`(no aplica: microservicio backend sin UI)`

## 4. Radius, elevación y movimiento

`(no aplica: microservicio backend sin UI)`

## 5. Breakpoints

`(no aplica: microservicio backend sin UI)`

## 6. Iconografía

`(no aplica: microservicio backend sin UI)`

## 7. Componentes

`(no aplica: microservicio backend sin UI)`

## 8. Accesibilidad

`(no aplica: microservicio backend sin UI)`

La accesibilidad de la interfaz que consume esta API es responsabilidad del frontend. El backend contribuye indirectamente:
- Mensajes de error claros y accionables (qué pasó, qué hacer).
- HTTP status codes correctos (400, 404, 409, 500).
- Contratos OpenAPI generados automáticamente desde FastAPI.

## 9. Aplicación por módulo

`(no aplica: microservicio backend sin UI)`

## 10. Gobierno y mantenimiento

- **Fuente de verdad**: código fuente (FastAPI genera OpenAPI automáticamente).
- **Dueño**: equipo Convivo.
- **Cómo proponer un cambio**: PR al código fuente + revisión.
- **Contrato API**: OpenAPI 3.1 generado desde los esquemas Pydantic — se versiona con el servicio.
- Tratar como código: cambios al contrato de API son breaking changes (§11.3 del AGENTS.md).

## 11. Normativa y cumplimiento

### 11.1 ISO/IEC 25010

`(no aplica: sin interfaz propia — atributos de interacción los determina el frontend)`

### 11.2 ISO/IEC 27001 — qué le toca al diseño

Desde el backend:
- **Confidencialidad**: datos de residentes nunca en logs claros, respuestas HTTP sin exponer IDs internos innecesariamente.
- **Integridad**: validación Pydantic en cada endpoint, queries parametrizadas.
- **Disponibilidad**: health check, reintentos, degradación graceful.

### 11.3 ISO 9001 / IEEE 730 / ISO/IEC/IEEE 29119

`(no aplica: sin proceso formal de pruebas de interfaz documentado)`

### 11.4 Cruce con normativa chilena

| Norma / criterio | Ley chilena | Punto de cruce | Qué exige en este documento |
| --- | --- | --- | --- |
| ISO/IEC 27001 | **Ley 21.719** (datos personales, entrada en force original 1-12-2026) | minimización y resguardo de datos personales | §10: sin PII en logs, queries parametrizadas, endpoints de derechos ARCO (futuro) |
| ISO/IEC 25010 | Ley 21.180 (transformación digital) | interoperabilidad | API REST + contratos OpenAPI versionados |

**Ley 21.719 — plazo real:** la APDP no está operativa al 2026 — el gobierno evalúa postergar a 2027. Verificar fecha vigente antes de planificar trabajo de cumplimiento.

## 12. Referencias

Del proyecto:

- `ERS.md` — Especificación de Requisitos de Software (§4.6 Auth dual, §4 Arquitectura)
- `mvp.md` — Alcance del MVP + deuda técnica
- `AGENTS.md` — Reglas de implementación y seguridad
- OpenAPI 3.1 generado: `http://localhost:8082/docs` (Swagger UI) al ejecutar el servicio

Canónicas:

- FastAPI documentation: <https://fastapi.tiangolio.com/>
- SQLAlchemy 2.0 async: <https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html>
- OWASP Top 10:2025: <https://owasp.org/Top10/>
