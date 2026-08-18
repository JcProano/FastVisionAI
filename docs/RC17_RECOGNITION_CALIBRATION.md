# RC17 — calibración y activación segura

RC17 separa los templates de referencia de las muestras de evaluación. Ningún
comando de captura o análisis modifica `people.db`, la galería, thumbnails o el
perfil PC seguro. Por defecto solo se guardan embeddings y metadata; `--save-images`
es opt-in y escribe fuera de la galería productiva.

Los mínimos predeterminados son salvaguardas operativas configurables, no valores
científicamente óptimos: 12 muestras genuinas, 2 sesiones genuinas, 20 muestras
impostoras, 2 sujetos impostores, FAR máximo 0.01, FRR máximo 0.10 y margen de
distribución mínimo 0.02.
Están declarados en `config/recognition_calibration_policy.pc.json`; el analizador
acepta otro archivo o overrides explícitos por argumento.

## 0. Inspeccionar

```bash
venv/bin/python -m src.validation.inspect_recognition_calibration \
  --gallery-manifest data/fastvision/gallery/gallery.json \
  --gallery-archive data/fastvision/gallery/gallery.npz
```

## A. Capturar muestras genuinas

Use el `person_id` registrado en `--expected-identity`. `--temporary-id` solo
agrupa el dataset de evaluación y no crea una identidad productiva.

```bash
venv/bin/python -m src.validation.capture_genuine_calibration \
  --confirm-sample-type 'CONFIRM GENUINE' \
  --temporary-id genuine-jean --expected-identity PERSON_ID \
  --gallery-manifest data/fastvision/gallery/gallery.json \
  --illumination NORMAL --distance OPERATIONAL --pose FRONTAL \
  --max-near-duplicate-similarity 0.995 --save-data --consent-confirmed
```

Repita en sesiones separadas y cambie condiciones. No es necesario cubrir el
producto cartesiano completo; el reporte enumera la cobertura ausente.

## B. Capturar muestras impostoras

Cada persona externa usa un `--temporary-id` distinto. No use
`--expected-identity`.

```bash
venv/bin/python -m src.validation.capture_impostor_calibration \
  --confirm-sample-type 'CONFIRM IMPOSTOR' \
  --temporary-id impostor-01 \
  --gallery-manifest data/fastvision/gallery/gallery.json \
  --illumination SIDE --distance OPERATIONAL --pose SLIGHT_LEFT \
  --max-near-duplicate-similarity 0.995 --save-data --consent-confirmed
```

## C. Analizar

```bash
venv/bin/python -m src.validation.analyze_recognition_calibration \
  --gallery-manifest data/fastvision/gallery/gallery.json \
  --gallery-archive data/fastvision/gallery/gallery.npz \
  --evaluation data/calibration --output data/calibration/rc17-report.json
```

El análisis no elige un threshold ni activa reconocimiento. Con una sola identidad,
el margen de ambigüedad se reporta como N/D; FAR continúa requiriendo impostores
externos. Un margen de distribución menor o igual a cero nunca se respalda.

## D. Aprobar

Solo después de revisar el reporte, use exactamente uno de sus
`supported_thresholds`:

```bash
venv/bin/python -m src.validation.approve_recognition_calibration \
  --source-report data/calibration/rc17-report.json --threshold VALOR_EXACTO \
  --gallery-manifest data/fastvision/gallery/gallery.json \
  --gallery-archive data/fastvision/gallery/gallery.npz \
  --confirm 'APPROVE RC17'
```

Esto crea `config/recognition_calibration.pc.json` y el perfil separado
`config/local_face_validation.pc.recognition.json`. Nunca modifica
`config/local_face_validation.pc.json`. El perfil activo mantiene `FaceMatcher`
non-deciding y valida modelo, versión, hash, threshold y margen antes de construir
`RecognitionService`.
