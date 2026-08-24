# ADR 008: Biometrics por casos de uso y adaptadores numéricos

## Estado

Aceptado e implementado incrementalmente.

## Contexto

Reconocimiento, enrollment, calibración y persistencia de galería estaban
organizados por componentes técnicos bajo `src/engine`. Aunque ya existían buenos
contratos, los servicios mezclaban coordinación de negocio con NumPy, tipos del
engine y almacenamiento JSON+NPZ. Esto obligaba a usar vectores y adaptadores reales
para probar decisiones que deberían ser deterministas y aisladas.

## Decisión

Crear el bounded context vertical `src/core/biometrics`:

```text
biometrics/
  domain/          políticas, resultados seguros, errores y puertos estructurales
  application/     un archivo y una clase por caso de uso
  infrastructure/  NumPy, identidad FaceGallery y persistencia JSON+NPZ
```

Los casos de uso públicos son:

- `RecognizeFaceUseCase`: interpreta candidatos bajo una política explícita, sin
  calcular vectores ni conocer presentación.
- `EnrollIdentityUseCase`: valida el lote completo, escribe transaccionalmente y
  verifica compensación ante fallos.
- `CalibrateBiometricsUseCase`: coordina el análisis mediante un puerto; el cálculo
  estadístico NumPy vive en `NumpyCalibrationAnalyzer`.
- `ExportGalleryUseCase`: representa la salida explícita de una galería.
- `ImportGalleryUseCase`: representa la importación validada y transaccional.

Los puertos son estructurales para permitir que los contratos existentes del engine
los satisfagan sin herencia ni dependencia inversa artificial. El dominio conserva
solo metadatos, políticas y resultados; no importa `src.engine`, NumPy, OpenCV, UI o
persistencia.

## Compatibilidad y composición

`RecognitionService`, `EnrollmentService` y `CalibrationService` conservan sus
métodos históricos, pero ahora son fachadas que delegan a los casos de uso. Los
contratos históricos reexportan las clases de dominio, por lo que no existen dos
modelos de política o resultado.

`src.engine.gallery.persistence` reexporta el adaptador movido a infraestructura.
`PeopleManagerController` mantiene su constructor público, pero compone
`ExportGalleryUseCase` e `ImportGalleryUseCase` y deja de invocar el adaptador de
persistencia directamente.

Face detection, alignment, embedding, matching y el agregado `FaceGallery` continúan
temporalmente bajo `src.engine`: son capacidades numéricas o modelos de
infraestructura, no casos de uso. Su migración física puede hacerse después sin
cambiar la API de aplicación creada aquí.

## Pruebas y controles

Las pruebas bajo `tests/core/biometrics/application` usan objetos Python simples;
no importan NumPy, OpenCV, SQLite, UI ni contratos del engine. Cubren decisiones de
reconocimiento, validación y compensación de enrollment, calibración por puerto y
transferencia de galería.

`tests/test_clean_architecture_boundaries.py` impide dependencias salientes desde
dominio o aplicación y fija exactamente los cinco archivos `*UseCase`, con máximo
un caso de uso por archivo. Las suites históricas siguen cubriendo los adaptadores y
las fachadas de compatibilidad.

## Consecuencias

- Las reglas biométricas pueden probarse sin frameworks numéricos ni archivos.
- El engine continúa disponible para todos los consumidores existentes.
- La persistencia de desarrollo sigue sin ser almacenamiento biométrico de
  producción y requiere habilitación explícita.
- Security y Audit son los siguientes contextos; sus casos de uso dependerán de
  puertos propios, no de estas implementaciones biométricas.
