# Presentación de cámara

El Dashboard adapta el video al espacio disponible conservando su relación de aspecto,
lo centra y deja un fondo neutro (letterbox) cuando las proporciones no coinciden. La
rotación, el espejo horizontal y el recorte configurables se aplican únicamente a esta
copia de presentación; no modifican los frames usados por detección, reconocimiento,
enrollment, calidad ni thumbnails aprobados.

La marca de agua de DroidCam debe deshabilitarse desde la fuente DroidCam si la
aplicación/origen lo permite. FastVisionAI no intenta borrarla, reconstruirla ni pintar
sobre ella. El recorte de presentación es opcional y está desactivado inicialmente.

Valores admitidos para `camera.presentation.rotation`: `0`, `90`, `180` y `270`.
`camera.presentation_crop` acepta porcentajes independientes y sólo se aplica cuando
`enabled` es `true`.
