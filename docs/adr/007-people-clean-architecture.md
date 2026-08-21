# ADR 007: People como bounded context y enrollment por casos de uso

## Estado

Aceptado e implementado incrementalmente.

## Contexto

Los datos civiles vivían en `src/core/person_database`, pero sus consumidores
usaban directamente el repositorio SQLite. La coordinación de enrollment vivía en
`src/ui/person_enrollment`, aunque contiene reglas críticas: reservar una persona,
confirmar biometría, activar el registro civil y compensar ambos lados ante fallos.

Esto hacía que presentación conociera transacciones y estados de negocio, dificultaba
probar cada operación sin SQLite/FaceGallery y permitía saltarse reglas como las
transiciones administrativas válidas.

## Decisión

Crear el bounded context vertical `src/core/people`:

```text
people/
  domain/          modelos PII, validación, errores y puertos
  application/     una clase y archivo por caso de uso
  infrastructure/  repositorio y migraciones SQLite, proveedor local
```

Los casos de uso civiles son:

- `CreatePersonUseCase`
- `GetPersonUseCase`
- `SearchPeopleUseCase`
- `UpdatePersonUseCase`
- `ChangePersonStatusUseCase`

La saga de enrollment se expresa como tres operaciones independientes:

- `BeginPersonEnrollmentUseCase`
- `CancelPersonEnrollmentUseCase`
- `CommitPersonEnrollmentUseCase`

Estas operaciones comparten exclusivamente `PersonEnrollmentSession`, que contiene
el estado y la reserva actual. Los casos de uso dependen de puertos estructurales para
repositorio, galería, workflow biométrico y edición del resultado; no importan UI,
FaceGallery, LocalEnrollmentWorkflow ni SQLite.

`CommitPersonEnrollmentUseCase` conserva la semántica fail-safe existente:

1. El registro civil permanece `PENDING_BIOMETRIC` durante captura.
2. Solo un commit biométrico exitoso permite pasar a `ACTIVE`.
3. Un fallo de activación elimina identidad biométrica y reserva civil.
4. Si no puede verificarse una compensación, el estado queda `INCONSISTENT`.
5. `PERSON_CREATED` se audita únicamente después de verificar ambos lados.

La transición administrativa permitida (`ACTIVE` ↔ `DISABLED`) vive ahora en
`ChangePersonStatusUseCase`, no en el controlador Tk.

## Compatibilidad

`src/core/person_database` conserva los nombres públicos anteriores como aliases o
reexports. `PersonRepository` apunta a `SQLitePeopleRepository`.

`src/ui/person_enrollment/PersonEnrollmentCoordinator` conserva `begin`, `cancel`,
`commit`, `state` y `active`, pero es una fachada que compone los tres casos de uso.
La conversión de resultados a `EnrollmentResultDTO` permanece en presentación detrás
de `EnrollmentResultEditorPort`.

## Pruebas y controles

Los tests bajo `tests/core/people/application` usan fakes en memoria y prueban cada
caso de uso sin SQLite, OpenCV ni NumPy. Las pruebas históricas siguen validando el
adaptador SQLite y la integración de UI.

`tests/test_clean_architecture_boundaries.py` falla si `people/domain` o
`people/application` importan infraestructura, el paquete legado, engine, UI,
SQLite, OpenCV o NumPy. También fija los ocho archivos `*UseCase` públicos.

## Consecuencias y trabajo posterior

- Los consumidores pueden migrar gradualmente desde `person_database` a `people`.
- Persistencia, reglas y presentación ya pueden fallar en suites distintas.
- Gestión de templates, reemplazo, muestras adicionales y borrado biométrico se
  migrarán con el bounded context Biometrics; no se incorporan al dominio People.
- El composition root seguirá construyendo aliases legados hasta introducir
  containers explícitos por contexto.
