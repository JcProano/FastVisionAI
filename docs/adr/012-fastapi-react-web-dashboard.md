# ADR 012: Dashboard FastAPI + React por casos de uso

## Estado

Aceptado e implementado.

## Contexto

El dashboard anterior usaba `http.server` y construía HTML, CSS y JavaScript
inline desde un controlador Python. El mismo objeto resolvía rutas, sesiones CSRF,
streaming MJPEG, tokens opacos, proyecciones, acciones administrativas y el flujo
de enrolamiento. Eso dificultaba probar reglas de forma aislada y obligaba a
mantener estilos y comportamiento mediante strings extensos.

Se evaluaron Django, Flask y FastAPI. El appliance no necesita ORM, panel admin ni
el stack completo de Django. Flask es pequeño, pero este proyecto ya usa DTOs
tipados y requiere streaming, ciclo de vida embebido y fronteras HTTP explícitas.
FastAPI/Starlette ofrece esas piezas con un coste de runtime adecuado y encaja con
la composición existente.

## Decisión

El dashboard queda dividido así:

```text
React + Tailwind + shadcn/ui
            |
      JSON / MJPEG / SSE
            v
FastAPI adapter -> WebDashboardController -> application controllers
                         |
                         v
             WebEnrollmentContainer
                         |
       un archivo/clase por caso de uso
                         v
             WebEnrollmentState (domain)
```

- FastAPI expone una lista cerrada de endpoints y Uvicorn conserva el ciclo de
  vida embebido dentro del proceso existente.
- React/Vite genera una SPA estática. Tailwind CSS y componentes shadcn/ui se
  compilan en build time; Node.js no se instala en el appliance de producción.
- `src/core/web_dashboard/domain` no depende de FastAPI, UI ni dispositivos.
- `src/core/web_dashboard/application` contiene siete operaciones, una por
  archivo: iniciar, registrar datos civiles, capturar, seleccionar fotografía,
  confirmar, cancelar y consultar estado.
- `WebEnrollmentContainer` compone esos casos de uso mediante callbacks/puertos;
  el controlador web no conoce el motor biométrico concreto.
- El adapter FastAPI delega autorización en la sesión del appliance. Toda
  mutación exige JSON acotado, mismo origen y una sesión CSRF expirable.
- Las fotografías y personas se publican mediante tokens opacos con memoria
  acotada. Ningún `person_id`, embedding o template se serializa al navegador.
- El MJPEG y las sesiones HTTP tienen adaptadores independientes y tests propios.

## Controles

- `tests/core/web_dashboard/application/` prueba cada caso de uso directamente.
- `tests/test_clean_architecture_boundaries.py` prohíbe FastAPI, Uvicorn, UI,
  SQLite, OpenCV y NumPy dentro de dominio/aplicación, y fija un caso de uso por
  archivo.
- `tests/test_web_dashboard_fastapi_adapter.py` verifica SPA, headers de seguridad,
  autorización, mismo origen, CSRF, expiración y límite de sesiones.
- `npm run format:check` y `npm run build` validan el frontend tipado y producen
  el artefacto estático servido por Python.

## Consecuencias

- Backend y frontend pueden evolucionar y probarse sin construir Tkinter ni una
  cámara real.
- El runtime agrega FastAPI/Uvicorn, pero elimina el servidor HTTP artesanal y el
  HTML inline.
- El artefacto de despliegue debe incluir el build estático.
- La LAN sigue siendo un límite de confianza: aún no existe login web propio, TLS,
  reverse proxy ni gestión de sesiones de usuario por navegador.
