# Biometric data handling

Face embeddings are sensitive biometric data. They must not be written to
application logs, exception messages, diagnostics or console output. Temporary
identifiers used by validation tools are not real identities.

`FaceGallery` is an in-memory development implementation. Optional JSON+NPZ
export is explicit and disabled by default. JSON stores metadata and NPZ stores
the numeric templates; this format provides integrity validation but **does not
provide encryption** and is not suitable for production storage.

A production persistence layer must include encryption at rest and in transit,
least-privilege access control, audit trails, explicit retention limits,
verifiable deletion and external key management with rotation. Legal basis,
consent, data minimization and incident response must be defined for the target
jurisdiction before collecting real identities.

Official InsightFace weights used during current validation are restricted to
non-commercial research and development. Commercial deployment requires a
model with appropriate commercial rights or a corresponding license.

Static enrollment creates deterministic brightness variants solely to exercise
transaction and policy code. These variants are not independent biometric
captures and must never be used to calibrate production thresholds.

## Calibration captures and consent

Face-similarity calibration uses temporary test identifiers only. The operator
must obtain informed, explicit consent before persisting embeddings or diagnostic
images. The capture command requires `--consent-confirmed` whenever `--save-data`
or `--save-images` is selected. Nothing is saved by default.

Each session is restricted operationally to one person. Because Phase 10 has no
recognition or tracking, continuity of identity is the operator's responsibility.
Calibration artifacts are Git-ignored under `data/calibration/`. JSON+NPZ provides
integrity checking but no encryption and is not production storage.

Session deletion removes known manifests, archives and associated images, but it
does not claim secure physical erasure from the storage medium. Production policy
must define consent, access, retention, verifiable deletion and key management.

A score is accepted when `similarity >= threshold` and rejected when
`similarity < threshold`. FAR is accepted impostor pairs divided by evaluated
impostor pairs; FRR is rejected genuine pairs divided by genuine pairs. EER is a
sample-dependent estimate, never a production threshold recommendation.

Guided capture persists nothing by default. Enabling diagnostic aligned-face
images requires both `--save-data` and explicit consent. Rejected frames, rejected
aligned faces and embeddings rejected as near duplicates are never persisted.
Logs and final summaries contain states, aggregate quality metrics and safe sample
indices only; they must not serialize `GuidedCaptureResult.embedding`.

Face quality scores are diagnostic metadata, not identity evidence. They may be
stored with accepted calibration samples to support ordering and analysis, but
must not be interpreted as recognition confidence or access authorization. Score
reports include components, bands and profile provenance only; no image,
landmark, embedding or embedding fragment is included.

The people manager associates optional template quality metadata by the stable
gallery `template_index`. Its versioned `face_quality_templates` object contains
only score, band, profile provenance and recording time. Rebuilding a gallery
remaps indices explicitly; an absent score remains `sin score`. This metadata
must never contain vector fingerprints, embedding hashes, images or vector data.
## Interfaz local de validación

La interfaz local no registra imágenes ni embeddings por defecto. Cualquier
persistencia requiere consentimiento explícito y debe ocurrir después de un
enrollment válido. Los DTO públicos no transportan vectores biométricos. La
persistencia JSON+NPZ sigue siendo una facilidad de desarrollo sin cifrado y no
es adecuada para producción; requiere controles futuros de acceso, auditoría,
retención, borrado verificable y gestión de claves.
# Miniaturas faciales de presentación

Las miniaturas faciales son datos faciales sensibles. FastVisionAI las mantiene
separadas de embeddings, templates y archivos JSON/NPZ de la galería. Su uso es
exclusivamente visual: no participan en reconocimiento, matching, calidad ni
decisiones automáticas. Se crean solo tras consentimiento y enrollment exitoso,
y su actualización o borrado es una acción explícita e independiente.

El almacenamiento visual local actual no ofrece cifrado y no es apto para un
despliegue sensible de producción sin cifrado, control de acceso, auditoría,
retención, borrado verificable y gestión de claves.
# Person Database y datos personales

La base SQLite de Person Database contiene PII administrativa —cédula, nombres,
dirección, teléfono, email y otros campos— y permanece separada de fotografías,
embeddings y templates biométricos. La validación matemática de una cédula no
confirma la existencia de una persona ni la titularidad del documento.

SQLite local no se considera almacenamiento seguro de producción. Un despliegue
real deberá añadir cifrado en reposo, roles y control de acceso, auditoría,
políticas de retención y borrado, backups cifrados y gestión de claves. Esta fase
no implementa consultas externas, scraping ni acceso a instituciones nacionales.

La coordinación conserva dominios separados: PII civil en SQLite y templates
con metadata técnica en FaceGallery. Cédula, dirección, teléfono, email y fecha
de nacimiento no se copian a templates ni logs biométricos. `PENDING_BIOMETRIC`
solo cambia a `ACTIVE` después del commit biométrico. Una compensación no
verificable exige revisión administrativa y nunca autoriza borrados globales.

La ficha de persona expone únicamente agregados biométricos seguros y una
miniatura visual autorizada. No transporta embeddings, templates, landmarks,
procedencia del modelo ni rutas físicas. La cédula sirve solo para resolver el
registro civil y nunca participa en matching o reconocimiento.

El historial de detección guarda únicamente observaciones escalares. No contiene
cédula completa, domicilio, teléfono, email, notas, imágenes, thumbnails,
embeddings ni templates. `display_name_snapshot` es informativo y `person_id`
sigue siendo la referencia interna. Una cédula se resuelve al leer desde Person
Database y se presenta enmascarada. Debe definirse una política futura de
retención; esta fase no realiza borrado automático.
# Separación de cuentas administrativas

La base local `users.db` de la Fase 35 no es almacenamiento biométrico y no se
relaciona con `FaceGallery` ni con `PersonRepository`. No contiene rostros,
embeddings, templates o imágenes. Una persona registrada no se convierte en
operador y el inicio de sesión nunca utiliza reconocimiento facial.
