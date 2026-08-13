# Despliegue Ubuntu

1. Crear `venv` con Python 3.12 e instalar `requirements.txt`.
2. Colocar modelos localmente y validar sus licencias.
3. Copiar y revisar `config/local_face_validation.prod.json` sin añadir secretos.
4. Dar al usuario de servicio acceso a `/dev/videoX` y a los directorios configurados.
5. Ejecutar `scripts/release_check.py`.
6. Iniciar con `venv/bin/python -m src.ui.main --config config/local_face_validation.prod.json --load-gallery`.

Las bases, galería, thumbnails, backups y logs deben tener propietario/permisos restrictivos. Cierre mediante la UI o SIGTERM gestionado por el supervisor; no mate el proceso durante enrollment o restore. El backup actual no está cifrado.

