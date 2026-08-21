# ADR 006: Migración incremental a Clean Architecture

## Estado

Aceptado para migración incremental. `attendance` es el primer bounded context.

## Contexto

FastVisionAI ya separa muchos contratos y adaptadores, pero la estructura histórica
mezcla entidades, casos de uso, SQLite y presentación dentro de paquetes técnicos.
Además, `src/ui/main.py` concentra composición, infraestructura y coordinación de
múltiples dominios.

Los proyectos Solintsoft organizan cada capacidad funcional como un módulo vertical:

```text
bounded_context/
  domain/          entidades, value objects, reglas y puertos
  application/     un archivo/clase por caso de uso y proyecciones
  infrastructure/  SQLite, modelos, cámaras, red y otros adaptadores
  container        composición de dependencias
```

La regla de dependencias apunta hacia adentro y el bootstrap es el único lugar que
conoce todas las implementaciones:

```text
presentation -> application -> domain
bootstrap    -> application + infrastructure + presentation
infrastructure -------------------------> domain
```

`application` usa puertos definidos por el módulo; nunca importa una base de datos,
Tkinter, HTTP, OpenCV o la implementación concreta de otro bounded context. Cada
operación pública se expresa como una clase `*UseCase` con un único método
`execute`. Un caso de uso puede conservar estado propio de su flujo, pero no comparte
un servicio monolítico con operaciones no relacionadas.

## Decisión

Migrar por bounded context y mantener fachadas de compatibilidad temporales. No se
hará una reescritura global ni se cambiarán contratos públicos y persistencia en la
misma operación.

El primer slice reorganiza `attendance`:

- `domain/models.py`: entidades, DTO y errores.
- `domain/policy.py`: política y reglas invariantes.
- `domain/ports.py`: puertos de persistencia, persona y reloj local.
- `application/manual_check_in.py`: registro manual de entrada.
- `application/manual_check_out.py`: registro manual de salida.
- `application/evaluate_observation.py`: estabilidad y alternancia de observaciones.
- `application/consume_detection_event.py`: consumo atómico de detecciones.
- `service.py`: fachada de compatibilidad fuera de application que compone y delega
  a esos casos de uso.
- `application/projection.py`: proyecciones de lectura.
- `infrastructure/sqlite_repository.py`: adaptador SQLite.
- `infrastructure/migrations.py`: schema SQLite.

Los módulos anteriores (`contracts.py`, `repository.py`, `service.py`, etc.) son
fachadas de compatibilidad. Se eliminarán solo cuando todos los consumidores usen
las rutas nuevas.

Los tests nuevos replican la estructura del módulo bajo
`tests/core/<context>/application/`. Prueban cada caso de uso directamente mediante
fakes en memoria de los puertos; las pruebas de integración del repositorio SQLite
se mantienen separadas. Así, una regla de negocio rota falla en un test pequeño y
determinista, mientras que un problema del adaptador falla en su suite de
infraestructura.

## Fases siguientes

People fue migrado como segundo slice en
[ADR 007](007-people-clean-architecture.md) y Biometrics como tercero en
[ADR 008](008-biometrics-clean-architecture.md). Security y Audit se migraron en
[ADR 009](009-security-audit-clean-architecture.md). Las fases restantes son:

1. Migrar Backup y Configuration con puertos explícitos.
2. Reducir `src/ui/main.py` a un composition root que construya contenedores por
   contexto, siguiendo los containers de Solintsoft sin introducir un framework DI.
3. Separar presentación Tk y web de los controladores/casos de uso compartidos.

## Controles

`tests/test_clean_architecture_boundaries.py` inspecciona imports y falla si dominio
o aplicación vuelven a depender de UI, SQLite, OpenCV, NumPy o infraestructura.
También fija los casos de uso públicos de cada contexto migrado y exige como máximo
una clase `*UseCase` por archivo.

## Consecuencias

- La migración es reversible por módulo y conserva los tests existentes.
- Durante la transición existen imports antiguos y nuevos.
- Habrá algo de código de compatibilidad temporal, pero no duplicación de reglas.
- Cada siguiente módulo requiere primero tests de comportamiento y después reglas
  automáticas de dependencias.
