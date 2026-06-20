# PFM Market Intelligence Tracker — Starter Kit

Sistema gratuito de observación diaria para analizar Prop Firm Match, competidores, prop firms y posibles vendors durante 7 días.

## Arquitectura
GitHub Actions diario → Python + Playwright → captura HTML/texto/screenshots → CSV/JSON → opcional envío a Google Sheets mediante Apps Script Web App.

## Gratis
No usa Apify, Browse AI, Browserless, proxies, SEMrush, Similarweb ni servicios de pago.

## Arranque
1. Crear un repositorio GitHub.
2. Subir estos archivos.
3. Activar GitHub Actions.
4. Opcional: crear Google Sheet + Apps Script con `apps_script/Code.gs`.
5. Añadir la URL del Web App como secret de GitHub: `GAS_WEBHOOK_URL`.
6. Ejecutar manualmente el workflow `Daily market capture`.

## Comando local
```bash
pip install -r requirements.txt
python -m playwright install chromium
python src/scrape.py --config config/sites.yml --out data/run_local --max-pages-total 120
```

## Filosofía
Cada dato conserva fuente, URL, fecha, texto bruto y nivel de confianza. La interpretación viene después.
