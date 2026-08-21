# ADR 009: Security y Audit como bounded contexts por operación

## Estado

Aceptado e implementado incrementalmente.

## Contexto

Security y Audit ya estaban aislados funcionalmente, pero organizados como paquetes
técnicos planos. `AuthenticationService` contenía bootstrap, autenticación y cambio
de contraseña; `UserManagementController` contenía cinco operaciones de negocio
además de presentación. Audit mezclaba creación, sanitización y tolerancia a fallos
en un servicio, mientras su controlador accedía directamente al repositorio y al
exportador.

La suite también revelaba conexiones SQLite de Security que no se cerraban en las
lecturas: usar `with sqlite3.Connection` confirma o revierte transacciones, pero no
cierra la conexión.

## Decisión para Security

Crear las capas `domain`, `application` e `infrastructure` dentro de
`src/core/security`.

El dominio contiene usuarios, políticas de contraseña/autenticación, matriz RBAC y
puertos de repositorio y hashing. Las operaciones se separan en nueve casos de uso:

- `AuthenticateUserUseCase`
- `AuthorizeActionUseCase`
- `BootstrapAdminUseCase`
- `ChangePasswordUseCase`
- `ListUsersUseCase`
- `CreateUserUseCase`
- `UpdateUserUseCase`
- `ChangeUserStatusUseCase`
- `ResetUserPasswordUseCase`

La protección contra auto-deshabilitación pertenece a
`ChangeUserStatusUseCase`. La protección del último administrador activo permanece
como invariante transaccional del repositorio, porque requiere una lectura y
escritura atómicas en el mismo store.

`SQLiteUserRepository`, `ScryptPasswordHasher` e
`InMemoryAuthenticatedSessionManager` son adaptadores. El repositorio usa ahora un
context manager explícito que cierra cada conexión de lectura.

## Decisión para Audit

Crear el mismo corte vertical en `src/core/audit`. Los contratos, puertos y la
política de sanitización son dominio. Las operaciones públicas son:

- `RecordAuditUseCase`
- `SafeRecordAuditUseCase`
- `QueryAuditUseCase`
- `SummarizeAuditUseCase`
- `ExportAuditUseCase`

`SQLiteAuditRepository` y `CSVAuditExporter` son adaptadores. La autorización para
ver o exportar continúa en la frontera de presentación y se evalúa nuevamente antes
de invocar los casos de uso.

## Compatibilidad

Los nombres públicos `UserRepository`, `PasswordHasher`,
`AuthenticatedSessionManager`, `AuditRepository` y `AuditCSVExporter` son aliases
temporales de los adaptadores nuevos. `AuthenticationService`,
`AuthorizationEngine` y `AuditService` conservan sus métodos y atributos usados por
el composition root, pero delegan a casos de uso.

Los controladores Tk conservan su API. `UserManagementController` compone cinco
casos de uso administrativos y `AuditController` compone consulta, resumen y
exportación.

## Pruebas y controles

Cada caso de uso tiene una prueba directa bajo `tests/core/security/application` o
`tests/core/audit/application`, usando repositorios, hasher y exporter en memoria.
Estas suites no abren SQLite ni importan UI.

Las reglas de arquitectura impiden imports de infraestructura o presentación desde
dominio/aplicación y fijan los nueve casos de uso de Security y los cinco de Audit,
con máximo una clase `*UseCase` por archivo.

## Consecuencias

- Fallos de credenciales, RBAC, administración, sanitización y exportación quedan
  localizados en pruebas pequeñas.
- Las integraciones existentes no requieren una migración simultánea.
- La auditoría continúa siendo best-effort solo cuando el consumidor elige
  `SafeRecordAuditUseCase`; el caso estricto conserva errores.
- Backup y Configuration son los siguientes contextos a migrar.
