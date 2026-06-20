# Instalación rápida

1. Crear repo en GitHub y subir el contenido del ZIP.
2. Crear un Google Sheet vacío.
3. En el Sheet: Extensiones → Apps Script → pegar `apps_script/Code.gs`.
4. Implementar como Aplicación web.
5. Guardar la URL como secret `GAS_WEBHOOK_URL` en GitHub Actions.
6. Ejecutar `Daily market capture` manualmente.

## Volumen

El workflow permite ajustar:
- `max_pages_total`
- `max_pages_per_site`

Yo empezaría con 250 páginas y subiría a 500 si no hay bloqueos ni errores.
