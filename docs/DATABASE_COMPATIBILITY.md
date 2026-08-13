# Compatibilidad de datos v1.0.0-rc1

| Componente | Versión |
|---|---:|
| people.db | 1 |
| events.db | 1 |
| attendance.db | 1 |
| users.db | 1 |
| audit.db | 1 |
| manifest `.fvbackup` | 1 |
| configuración | 1 |

Versiones futuras desconocidas se rechazan. El backup usa snapshots SQLite consistentes, registra schema y versión de aplicación, y se valida por completo antes de restaurar. No se realizan migraciones silenciosas.

