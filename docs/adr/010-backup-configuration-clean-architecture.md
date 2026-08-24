# ADR 010: Backup y Configuration por casos de uso

## Estado

Aceptado e implementado incrementalmente.

## Contexto

Backup combinaba creación, validación, OpenCV, galería biométrica, ZIP, SQLite y
mantenimiento en dos servicios grandes. Configuration combinaba snapshot, validación,
diff, escritura atómica, backups, importación y exportación en un solo servicio.

Ambos contextos ya tenían garantías de seguridad valiosas que debían conservarse:
allowlists de rutas, ZIP sin `extractall`, snapshots SQLite, rollback verificado,
validación antes de publicar, escritura atómica y exportación sin secretos.

## Decisión para Backup

Crear `domain`, `application` e `infrastructure` dentro de `src/core/backup` y
expresar los flujos públicos como:

- `CreateBackupUseCase`
- `VerifyBackupUseCase`
- `PrepareRestoreUseCase`
- `RestoreBackupUseCase`

Application coordina el flujo mediante puertos para catálogo, archivo, snapshots,
mantenimiento y validación de contenido. `EngineBackupContentValidator` concentra
OpenCV, NumPy y la importación de la galería biométrica. Por lo tanto, application no
conoce engine ni frameworks numéricos.

La preparación de restore solo valida y crea un plan. El commit requiere estado
`QUIESCENT`, instala componentes allowlisted y conserva la compensación verificada.
Un rollback no verificable sigue produciendo `RestoreRollbackError` y estado
`FAILED`.

`BackupService` y `RestoreService` permanecen como fachadas compatibles que componen
los casos de uso.

## Decisión para Configuration

Crear siete operaciones independientes:

- `GetConfigurationUseCase`
- `ValidateConfigurationUseCase`
- `DiffConfigurationUseCase`
- `ReloadConfigurationUseCase`
- `SaveConfigurationUseCase`
- `ImportConfigurationUseCase`
- `ExportConfigurationUseCase`

Los casos comparten únicamente `ConfigurationSession`, un holder thread-safe del
snapshot actual y la señal `restart_required_pending`. La clasificación del diff es
una política pura de dominio.

`ProjectConfigurationPolicy` adapta las allowlists y redacción existentes.
`JSONConfigurationLoader` y `AtomicConfigurationStore` encapsulan JSON, filesystem,
fsync, copia previa y rotación. `SaveConfigurationUseCase` publica el snapshot solo
después de que storage confirma la escritura y recarga el archivo. Importar devuelve
un candidato y su diff, sin aplicarlo.

`ConfigurationService` conserva la API histórica y los puntos de inyección usados
para comprobar fallos de `os.replace`, fsync y rotación, pero delega cada operación a
su caso de uso.

## Pruebas y controles

Las pruebas bajo `tests/core/backup/application` y
`tests/core/configuration/application` usan puertos falsos y verifican cada operación
sin engine, OpenCV, NumPy, SQLite o UI. Las suites históricas siguen cubriendo ZIP,
filesystem, SQLite, rollback, RBAC y ventanas.

Las reglas estáticas fijan los cuatro casos de uso de Backup y los siete de
Configuration, además de impedir dependencias desde dominio/aplicación hacia
adaptadores o presentación.

## Consecuencias

- Los fallos de coordinación se distinguen de fallos de ZIP, SQLite, JSON o imagen.
- Se conservan las fachadas públicas y formatos persistidos.
- Los siete bounded contexts funcionales usan la misma convención vertical.
- El trabajo restante es composición: extraer containers por contexto y reducir el
  bootstrap monolítico de UI.
