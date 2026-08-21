# ADR 011: Containers por bounded context

## Estado

Aceptado e implementado.

## Contexto

Los siete bounded contexts migrados ya separaban dominio, casos de uso y
adaptadores, pero `src/ui/main.py` todavía construía políticas, rutas y servicios
concretos. Esto dejaba decisiones de infraestructura dentro del bootstrap de
presentación y duplicaba la forma de componer cada módulo.

Los proyectos Solintsoft usan un container pequeño por capacidad funcional. El
container es código explícito de composición, no un service locator ni un framework
de inyección de dependencias.

## Decisión

Agregar un composition root a cada contexto migrado:

- `AttendanceContainer`
- `PeopleContainer`
- `BiometricsContainer`
- `SecurityContainer`
- `AuditContainer`
- `BackupContainer`
- `ConfigurationContainer`

Cada container interpreta únicamente la configuración de su contexto, valida rutas
y valores, selecciona adaptadores y devuelve un grafo de dependencias listo para la
presentación. Sus factories concretas se pueden reemplazar explícitamente en tests.

`src/ui/main.py` conserva la coordinación global y la creación de controladores de
presentación, pero delega al container correspondiente la construcción de políticas,
repositorios y servicios. Ningún container puede importar `src.ui`.

Biometrics se importa desde `src.core.biometrics.container`, y no desde el
`__init__` del paquete, porque el engine histórico reutiliza contratos del dominio
biométrico durante su propia inicialización. La ruta explícita evita un ciclo sin
invertir la regla de dependencias.

## Garantías conservadas

- Security deshabilitado no inicializa SQLite y el modo appliance no crea cuentas.
- Audit queda deshabilitado si su repositorio no puede inicializarse; el estado se
  propaga al caso de uso de escritura.
- Attendance deshabilitado no resuelve ni abre su base de datos.
- People, Audit, Attendance y Security rechazan rutas que escapan del proyecto.
- Backup comparte una sola instancia de mantenimiento, catálogo, archivo y snapshot
  entre backup y restore.
- Configuration solo admite perfiles de ejecución disponibles.
- Biometrics mantiene la decisión automática desactivada ante calibración inválida.

## Pruebas y controles

`tests/test_clean_architecture_containers.py` prueba la composición mediante factories
falsas, sin levantar UI ni infraestructura real. La regla estática de arquitectura
inspecciona los siete `container.py` y prohíbe dependencias hacia presentación.

Las pruebas históricas continúan entrando por los builders públicos de
`src/ui/main.py`, lo que comprueba la compatibilidad del bootstrap.

## Consecuencias

- Las reglas de composición tienen un único dueño por contexto.
- Los casos de uso continúan siendo probables de forma aislada mediante puertos.
- El bootstrap global pierde lógica de negocio e infraestructura repetida.
- La siguiente mejora puede separar los bootstraps Tk y web sin volver a mover reglas
  hacia presentación.
