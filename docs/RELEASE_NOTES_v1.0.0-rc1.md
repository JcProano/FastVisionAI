# FastVisionAI 1.0.0-rc1

Release Candidate de consolidación: cámara modular, pipeline biométrico desacoplado, SQLite civil/operativo, RBAC local con scrypt, auditoría append-only, backup verificable, configuración validada, reportes y System Health.

## Seguridad y operación

- Login ocurre antes de construir Runtime y Camera.
- Seguridad falla cerrada; módulos opcionales degradan de forma segura.
- Persistencia temporal en UTC; presentación diaria en `America/Guayaquil`.
- Backup incorpora people, events, attendance, users, audit, galería, thumbnails y configuración permitida.

## Limitaciones conocidas

- Reconocimiento automático y thresholds de identidad deshabilitados.
- Asistencia automática deshabilitada.
- Backups sensibles sin cifrado.
- Latencia de inferencia puede mostrarse como N/D.
- Modelos oficiales de InsightFace están limitados a investigación no comercial.
- Cámara, OpenCV y aceleración dependen del hardware/JetPack.

Los tags históricos `v0.33-audit-log` y `v0.34-system-health` apuntan al mismo commit de Fase 32 y no se reescriben. Las referencias correctas posteriores son `v0.37-system-health` y `v0.39-audit-log`.

