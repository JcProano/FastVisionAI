# NVIDIA Jetson Orin Nano

## Prerrequisitos

- JetPack compatible, Python 3.12 si está disponible para la imagen elegida.
- OpenCV de JetPack con GStreamer; evitar sustituirlo por el wheel sin comprobar CSI/CUDA.
- NumPy compatible con la versión de OpenCV.
- Tkinter únicamente si se usará la UI local.

## Instalación

Crear un `venv`, instalar solo dependencias compatibles y colocar los modelos en `models/face/` y `models/face_embedding/`. No versionar pesos ni `data/`.

Validar primero:

```bash
venv/bin/python scripts/release_check.py --config config/local_face_validation.prod.json
```

Inicio:

```bash
venv/bin/python -m src.ui.main --config config/local_face_validation.prod.json --load-gallery
```

Para CSI se añadirá posteriormente un source GStreamer sin modificar los contratos de Camera Service. TensorRT/DeepStream no están integrados en este RC. Verifique permisos de cámara, disponibilidad de modelos, memoria y backend OpenCV antes de iniciar.

