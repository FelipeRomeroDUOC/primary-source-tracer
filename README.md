# Primary Source Tracer (`primary-source-tracer`)

Plugin portable y agnóstico al dominio (servidor MCP en Python + Skill + Reglas) para rastrear **evidencia primaria**, contrastar estudios o registros fundacionales con réplicas posteriores, saltar a través de fuentes puente, detectar **clústeres de eco** y listar explícitamente las **fuentes secundarias** (incluyendo falsos primarios en formato PDF, sitios oficiales o tras *paywall*) con la razón de su clasificación.

---

## Instalación rápida

### Opción A — Sin clonar el repo (vía `uvx` desde GitHub)
Si tienes [`uv`](https://docs.astral.sh/uv/) instalado, cualquier agente compatible con MCP puede ejecutar el servidor directamente desde GitHub sin instalación global previa:

```json
{
  "mcpServers": {
    "primary-source-tracer": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/FelipeRomeroDUOC/primary-source-tracer[pdf]",
        "primary-source-tracer-mcp"
      ]
    }
  }
}
```

### Opción B — Instalar el paquete Python (`pip`)
Desde GitHub o desde un clon local:

```bash
# Desde GitHub (recomendado, incluye soporte para PDFs y facsímiles escaneados)
pip install "git+https://github.com/FelipeRomeroDUOC/primary-source-tracer.git[pdf]"

# O desde un clon local en modo editable
git clone https://github.com/FelipeRomeroDUOC/primary-source-tracer.git
cd primary-source-tracer
pip install -e ".[pdf]"
```

> Si prefieres cero dependencias externas (solo HTML y extracción básica), omite `[pdf]`.

### Instalar solo la Skill en múltiples agentes (`npx skills`)
```bash
npx skills add FelipeRomeroDUOC/primary-source-tracer
```

---

## Conectar con cada agente

### 1. Claude Code
Este repositorio incluye `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.mcp.json` y `skills/primary-source-search/SKILL.md`.

En Claude Code:
```text
/plugin marketplace add FelipeRomeroDUOC/primary-source-tracer
/plugin install primary-source-tracer@primary-source-tracer
```
O localmente tras clonar e instalar con `pip`:
- Abre el directorio del proyecto (`.mcp.json` se detecta automáticamente) o copia `skills/primary-source-search/SKILL.md` a `.claude/skills/primary-source-search/SKILL.md`.

### 2. Antigravity
1. Clona este repositorio dentro de `~/.gemini/config/plugins/primary-source-tracer/` (o cárgalo como workspace).
2. Instala las dependencias Python (`pip install -e ".[pdf]"`), o actualiza `mcp_config.json` para usar `uvx` si prefieres entorno aislado.
3. Incluye de fábrica:
   - `plugin.json`
   - `mcp_config.json`
   - `assets/logo.svg`
   - `skills/primary-source-search/SKILL.md`
   - `rules/AGENTS.md`

### 3. Gemini CLI
Este repositorio incluye `gemini-extension.json` (con `rules/AGENTS.md` como contexto y el servidor MCP apuntando a `primary_source_tracer/server.py`):

```bash
gemini extensions install https://github.com/FelipeRomeroDUOC/primary-source-tracer
```
O añade manualmente a `~/.gemini/settings.json`:
```json
{
  "mcpServers": {
    "primary-source-tracer": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/FelipeRomeroDUOC/primary-source-tracer[pdf]",
        "primary-source-tracer-mcp"
      ]
    }
  }
}
```

### 4. Cursor / Windsurf
Agrega la entrada MCP en `~/.cursor/mcp.json` (o `.cursor/mcp.json` del proyecto / configuración MCP de Windsurf):

```json
{
  "mcpServers": {
    "primary-source-tracer": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/FelipeRomeroDUOC/primary-source-tracer[pdf]",
        "primary-source-tracer-mcp"
      ]
    }
  }
}
```
*(Si instalaste con `pip`, también puedes usar `"command": "python", "args": ["-m", "primary_source_tracer.server"]`.)*

Luego instala la skill con `npx skills add FelipeRomeroDUOC/primary-source-tracer` o copia `skills/primary-source-search/SKILL.md` y `rules/AGENTS.md` a tus reglas/skills.

### 5. OpenAI Codex CLI
Agrega a `~/.codex/config.toml`:

```toml
[mcp_servers.primary-source-tracer]
command = "uvx"
args = [
  "--from",
  "git+https://github.com/FelipeRomeroDUOC/primary-source-tracer[pdf]",
  "primary-source-tracer-mcp"
]
```
*(O con `pip` instalado: `command = "python"`, `args = ["-m", "primary_source_tracer.server"]`.)*

Copia `skills/primary-source-search/SKILL.md` a `~/.codex/skills/primary-source-search/SKILL.md` (o instala con `npx skills add FelipeRomeroDUOC/primary-source-tracer`) y añade el contenido de `rules/AGENTS.md` a tu `~/.codex/AGENTS.md`.

---

## Uso remoto (Claude.ai, App web de Gemini o Cloud Run)

El servidor incluye un modo **Streamable HTTP** (`--http`, endpoint `/mcp` y `/healthz`) que **desactiva automáticamente la lectura de archivos locales y bloquea IPs privadas/internas (protección anti-SSRF)**.

### 1. Arrancar en modo HTTP remoto
```bash
# Recomendado: define un Bearer token si lo vas a exponer públicamente
export MCP_AUTH_TOKEN="tu-token-secreto"
primary-source-tracer-mcp --http --host 127.0.0.1 --port 8000
```

O en Docker / Google Cloud Run (usa el `Dockerfile` incluido):
```bash
gcloud run deploy primary-source-tracer \
  --source . \
  --allow-unauthenticated \
  --set-env-vars MCP_AUTH_TOKEN="tu-token-secreto"
```

### 2. Pruebas rápidas desde tu PC con túnel HTTPS
Si quieres probar desde la nube sin desplegar todavía, levanta el servidor en `127.0.0.1:8000` y expón un túnel HTTPS en puerto 443 (por ejemplo con Cloudflare Tunnel o `ngrok`):
```bash
cloudflared tunnel --url http://127.0.0.1:8000
```
Usa la URL resultante terminada en `/mcp` (ej. `https://tu-subdominio.trycloudflare.com/mcp`).

### 3. Conectar en interfaces web
- **Claude.ai / Claude Desktop**: *Settings → Connectors → Add custom connector* → pega `https://<tu-dominio>/mcp`.
- **Gemini (`gemini.google.com`)**: *Settings → Connected Apps → Custom App / MCP Server* → pega `https://<tu-dominio>/mcp` (disponibilidad según cuenta/Workspace).
- **Claude Code (remoto)**:
  ```bash
  claude mcp add --transport http primary-source-tracer https://<tu-dominio>/mcp --header "Authorization: Bearer tu-token-secreto"
  ```

---

## Herramientas MCP incluidas

1. `search_web_candidates(queries, max_results_per_query)` — Ejecuta consultas dinámicas definidas por el agente (100 % agnóstico al tema).
2. `inspect_and_classify_source(url_or_path, agent_evidence_markers, max_excerpts)` — Inspecciona HTML o PDF (remoto o local), detecta falsos primarios (`official_or_pdf_but_secondary`), detecta *paywalls* (`paywalled_abstract_only`) resolviendo DOIs vía OpenAlex, renderiza PDFs escaneados a PNG y extrae enlaces puente.
3. `compare_echo_and_trace(urls, agent_evidence_markers, follow_bridge_links, max_bridge_hops)` — Detecta clústeres de eco mediante similitud TF-IDF en Python puro, sigue enlaces puente automáticamente (1 salto) y conserva todas las fuentes secundarias con sus razones.

---

## Verificación local

```bash
pip install -e ".[pdf]"
python -m unittest discover -s tests -p "test_*.py" -v
```

## Licencia

MIT — consulta [LICENSE](LICENSE).
