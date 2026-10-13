# areazero-novedades

Dashboard de novedades de areazero.biz.

- Web: https://ivanareazero-eng.github.io/areazero-novedades/
- Se actualiza solo con GitHub Actions (`.github/workflows/monitor.yml`), dos veces al día. Se puede lanzar a mano desde la pestaña Actions → "areazero Monitor" → Run workflow.
- Email de aviso: necesita los secrets `GMAIL_USER` y `GMAIL_PASS` (contraseña de aplicación de Gmail) en Settings → Secrets and variables → Actions.
- Ya no depende del PC de la oficina ni de un token personal que caduque.
