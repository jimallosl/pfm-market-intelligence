# PFM Starter v2 Ready — qué hacer ahora

Este ZIP ya incluye:
- `config/sites.yml` adaptado al método v2.
- `src/scrape.py` parcheado para añadir `source_class`, `quality_estimate`, `influence_estimate`, `data_type` y `confidence_level`.
- `apps_script/Code.gs` actualizado para recibir esas columnas en Google Sheets.

## Orden correcto

1. Crear un repositorio GitHub nuevo.
2. Subir TODO el contenido de esta carpeta al repo, no la carpeta contenedora.
3. Crear un Google Sheet vacío.
4. En el Sheet: Extensiones → Apps Script.
5. Pegar `apps_script/Code.gs` completo.
6. Implementar como Aplicación web:
   - Ejecutar como: tú mismo.
   - Quién tiene acceso: cualquiera con el enlace.
7. Copiar la URL de la Web App.
8. En GitHub: Settings → Secrets and variables → Actions → New repository secret.
9. Nombre del secret: `GAS_WEBHOOK_URL`.
10. Valor: la URL de Apps Script.
11. En GitHub: Actions → Daily market capture → Run workflow.
12. Primer run:
    - max_pages_total: 250
    - max_pages_per_site: 50
13. Revisar:
    - Google Sheet: `run_log`, `raw_pages`, `extracted_signals`, `errors`.
    - GitHub artifact: `market-capture-...`.
14. Si errores <10-15% y los screenshots/HTML se generan bien, segundo run a 500 páginas.

## No hacer todavía

No escribir el case final.
No mandar candidatura.
No presentar vendors como oportunidad confirmada.
No afirmar Pareto como dato.
