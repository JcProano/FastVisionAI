# Checklist de release

- [ ] `PATH="$PWD/venv/bin:$PATH" python -m unittest`
- [ ] `PATH="$PWD/venv/bin:$PATH" python -m compileall src tests scripts`
- [ ] Smoke suite aprobada.
- [ ] `python scripts/release_check.py --require-clean`
- [ ] Config dev y prod válidas.
- [ ] `git diff --check` y working tree revisado.
- [ ] Schemas y `.fvbackup` compatibles.
- [ ] Smoke físico Ubuntu/Jetson aprobado.
- [ ] Backup real verificado sin restaurar producción.
- [ ] Release notes y limitaciones revisadas.
- [ ] Tag `v1.0.0-rc1` solo tras aprobación explícita.

