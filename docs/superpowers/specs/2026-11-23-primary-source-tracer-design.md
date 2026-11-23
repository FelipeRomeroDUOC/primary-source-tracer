# Diseño del Plugin: Primary Source Tracer (`primary-source-tracer`)

**Fecha:** 2026-11-23  
**Tipo de proyecto:** Plugin local de Antigravity (Servidor MCP en Python + Skill metodológica + Regla de activación)  
**Ubicación objetivo del plugin instalado:** `C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\`

---

## 1. Intención y el Porqué (Intent & Why)

Los experimentos previos de búsqueda demostraron que la capa superficial de internet (tanto en motores de búsqueda web como en plataformas de video) está saturada de **eco secundario**: artículos y notas que repiten las mismas afirmaciones sin enlazar al documento original, imágenes de bancos de stock o generadas por IA, y alta fricción de monetización (muros de cookies, newsletters, anuncios).

Además, identificamos dos trampas críticas:
1. **El falso positivo de formato o dominio ("es un PDF o un sitio `.gov`, así que es primario")**: muchos sitios oficiales publican páginas meramente informativas, comunicados de prensa o resúmenes normativos sin datos ni registros originales, y muchos PDFs son informes secundarios que solo citan a terceros.
2. **El sesgo de vocabulario fijo**: cada tema (lingüística histórica, infraestructura de IA, economía, medicina, jurisprudencia) tiene sus propios tipos de registros primarios, unidades y jerga documental. Una herramienta con términos predefinidos para un solo tema fracasa al cambiar de dominio.

**Por qué un Plugin de Antigravity (sin API de LLM externa):**
En lugar de pagar una API de modelo dentro del script, el **propio agente de Antigravity** actúa como el cerebro semántico (define qué es primario para el tema pedido, genera las consultas y los marcadores relevantes del dominio, y redacta el juicio final), mientras un **servidor MCP local en Python** ejecuta el trabajo determinístico pesado: descargar páginas/PDFs, extraer enlaces salientes del cuerpo del documento para saltar de fuentes puente a fuentes raíz, medir similitud textual entre artículos para detectar copias (eco) y detectar marcadores estructurales de atribución secundaria vs. datos propios.

---

## 2. Metas, No-Metas y Anti-Metas

### Metas (Goals)
1. **100 % agnóstico al tema**: el código del servidor MCP no contiene términos de búsqueda, unidades ni palabras clave de ningún dominio específico. El agente determina dinámicamente los términos de búsqueda (`queries`) y los marcadores de evidencia esperados (`agent_evidence_markers`) según la solicitud del usuario.
2. **Filtro explícito contra fuentes secundarias (incluyendo PDFs y sitios oficiales)**: evaluar tanto en HTML como en PDF si el documento aporta registros/mediciones/actas originales o si atribuye la información a terceros (*"según..."*, *"according to..."*, comunicados de prensa, resúmenes normativos sin datos crudos).
3. **Transparencia total sin descartes silenciosos**: el agente **no oculta** las fuentes secundarias encontradas; las lista explícitamente al usuario en una sección dedicada indicando su subtipo (*Secundaria Puente*, *Secundaria Oficial/Informativa*, *PDF Secundario de Revisión/Cita*, *Secundaria en Bucle de Eco*) y la **razón concreta** por la que se calificaron como secundarias.
4. **Rastreo de trazabilidad (*Link-Hopping*) y detección de eco**: extraer enlaces salientes relevantes de páginas secundarias para llegar al documento raíz en 1–2 saltos y agrupar artículos clonados por similitud textual.
5. **Métrica de esfuerzo visible**: reportar siempre cuántas búsquedas y cuántas inspecciones de documentos tomó llegar a la evidencia primaria, y la proporción entre fuentes primarias y secundarias.

### No-Metas (Non-Goals)
- No es un buscador o indexador web generalista ni almacena una base de datos permanente de internet.
- No utiliza APIs de modelos de lenguaje externas ni servicios de pago.
- No evade muros de pago (*paywalls*), CAPTCHAs ni controles de acceso; si un expediente oficial está bloqueado o roto (como páginas en blanco o con CAPTCHA), lo registra explícitamente como fricción técnica del documento.

### Anti-Metas (Anti-Goals — lo que haría que el proyecto falle aunque funcione técnicamente)
- Asumir automáticamente que cualquier `.pdf` o dominio `.gov`/`.gob`/`.edu` es una fuente primaria sin inspeccionar si su contenido es un resumen secundario o una cita a terceros.
- Incluir listas fijas de palabras clave temáticas (como `MW`, `dBA`, `tribunal`, `medioambiental`, `facsímil`) en el código del servidor MCP.
- Descartar en silencio las fuentes secundarias visitadas en vez de explicarle al usuario por qué fueron clasificadas como secundarias.
- Volcar páginas HTML enteras o PDFs de decenas de páginas en la ventana de contexto del agente.

---

## 3. Restricciones (Constraints)

- **Entorno**: Windows local, Python 3 local ejecutándose vía protocolo MCP estándar (`stdio` JSON-RPC 2.0).
- **Presupuesto de contexto (`context-mode`)**: las respuestas de cada herramienta MCP deben ser compactas (<12 KB), devolviendo señales estructuradas, metadatos, enlaces filtrados y extractos breves con número de página o sección.
- **Convenciones de Plugins de Antigravity**:
  - `plugin.json` válido únicamente con campos soportados (`name`, `displayName`, `description`, `version`, `logo`, `suggestedPrompts`).
  - El servidor MCP en `mcp_config.json` debe usar un nombre prefijado único (`primary-source-tracer`) para no colisionar en el espacio global.

---

## 4. Enfoques Considerados (Approaches)

1. **Skill independiente con scripts Python sueltos (`~/.gemini/config/skills/`)**:
   - *Ventaja*: sin servidor MCP, muy simple de crear.
   - *Desventaja*: el agente debe construir comandos de terminal manuales para cada análisis y no cuenta con herramientas nativas tipadas ni un interruptor único de plugin.
2. **Servidor MCP puro sin Skill**:
   - *Ventaja*: herramientas disponibles directamente en el catálogo MCP.
   - *Desventaja*: sin una `SKILL.md` que gobierne el razonamiento del agente, este podría pasar términos genéricos, olvidar definir la rúbrica del tema o descartar las fuentes secundarias sin explicar la razón.
3. **Plugin completo de Antigravity (Elegido)**:
   - *Por qué se eligió*: une en un solo paquete instalable y conmutable el **servidor MCP determinístico** (análisis estructural de fuentes, PDFs, enlaces y similitud) y la **Skill metodológica + Regla** (que obliga al agente a definir los términos del dominio, discernir falsos primarios en PDF/sitios oficiales y listar todas las secundarias con su razón).

---

## 5. Arquitectura y Decisiones Definidas (The How)

### 5.1 Estructura de archivos del Plugin
```text
C:\Users\felipe-pc\.gemini\config\plugins\primary-source-tracer\
├── plugin.json
├── README.md
├── mcp_config.json
├── assets/
│   └── logo.svg
├── mcp/
│   └── server.py
├── skills/
│   └── primary-source-search/
│       └── SKILL.md
└── rules/
    └── AGENTS.md
```

### 5.2 Herramientas del Servidor MCP (`mcp/server.py`)

El servidor MCP es **100 % agnóstico al dominio** y expone tres herramientas:

#### 1. `search_web_candidates`
- **Argumentos**:
  - `queries: list[str]` — Consultas generadas dinámicamente por el agente para el tema solicitado.
  - `max_results_per_query: int = 8`
- **Comportamiento**:
  - Ejecuta las búsquedas desde Python local (usando endpoints web/lite de búsqueda accesibles como DuckDuckGo HTML/Lite, con deduplicación de URLs).
  - Para cada resultado devuelve: `query_used`, `title`, `url`, `domain`, `resource_type` (`pdf`, `html`, `doc`, `dataset`), `domain_category` (`institutional_gov`, `academic_edu`, `media_or_blog`, `social_or_video`, `other`) —aclarando explícitamente en el esquema que `domain_category` **no implica** que sea fuente primaria— y `snippet`.

#### 2. `inspect_and_classify_source`
- **Argumentos**:
  - `url_or_path: str` — URL (HTML o PDF) o ruta local a un PDF descargado (por ejemplo, desde el subagente `browser`).
  - `agent_evidence_markers: list[str] = []` — Patrones, términos técnicos, unidades o identificadores que **el agente** definió dinámicamente para el tema actual.
  - `max_excerpts: int = 5`
- **Comportamiento (Análisis estructural agnóstico al tema)**:
  - Descarga la página HTML o abre el PDF (usando `pypdf`/`fitz` si están disponibles, o descarga binaria + parser ligero).
  - Extrae el texto principal (limpiando `<nav>`, `<footer>`, `<script>`, `<style>`).
  - Evalúa tres grupos de señales universales:
    1. **Señales de fuente secundaria / atribución externa (`secondary_signals`)** *(se aplican por igual a blogs, PDFs y sitios `.gov`/oficiales)*:
       - Detección de frases de atribución a terceros en español e inglés (*"según..."*, *"de acuerdo con..."*, *"citado por..."*, *"fuente: ..."*, *"according to..."*, *"as reported by..."*, *"source: ..."*, *"study by..."*).
       - Detección de marcadores de formato secundario/resumen (*"comunicado de prensa"*, *"nota de prensa"*, *"boletín"*, *"press release"*, *"fact sheet"*, *"policy brief"*, *"overview"*, *"resumen ejecutivo"*).
       - Ausencia de tablas de datos, registros identificables o coincidencias con `agent_evidence_markers`.
    2. **Señales de registro primario (`primary_signals`)**:
       - Presencia de estructura tabular o series de datos, numeración de páginas/secciones con coincidencias de `agent_evidence_markers`, metadatos de documento original, imágenes que no provienen de bancos de stock comerciales.
    3. **Señales de fricción y ruido comercial (`friction_signals`)**:
       - Imágenes de bancos de stock (`istockphoto`, `shutterstock`, `gettyimages`, `unsplash`, `freepik`, `adobe.stock`), bloques de suscripción/newsletter/cookies, o página vacía (`text_length == 0`).
  - **Extracción de enlaces salientes (`outbound_links`)**:
    - Extrae enlaces del cuerpo del documento, descartando navegación interna/redes sociales irrelevantes, y destaca aquellos cuyo texto de anclaje o URL apunte a documentos referenciados (`.pdf`, `.csv`, expedientes, estudios citados) para que sirvan como **salto desde una fuente puente**.
  - **Salida**: JSON compacto con `format` (`pdf`/`html`), `page_count`, `secondary_signals`, `primary_signals`, `friction_signals`, `preliminary_classification` (`likely_primary`, `official_or_pdf_but_secondary`, `secondary_bridge`, `secondary_no_outbound_proof`, `unreachable_or_empty`), `classification_reasons: list[str]` (las razones legibles de por qué presenta rasgos secundarios o primarios), `matched_excerpts` (con número de página o sección) y `outbound_links`.

#### 3. `compare_echo_and_trace`
- **Argumentos**:
  - `urls: list[str]` — Lista de URLs visitadas o candidatas (hasta 10).
  - `agent_evidence_markers: list[str] = []`
  - `follow_bridge_links: bool = True`
  - `max_bridge_hops: int = 4`
- **Comportamiento**:
  - Inspecciona en lote las URLs dadas.
  - Calcula **similitud textual par-a-par** (TF-IDF / similitud coseno en Python puro sobre el texto limpio) para detectar **clústeres de eco** (artículos que repiten prácticamente el mismo contenido).
  - Si `follow_bridge_links=True`, toma los mejores enlaces salientes hacia posibles documentos primarios encontrados dentro de las páginas secundarias ("fuentes puente") y los inspecciona automáticamente (1 salto).
  - Devuelve el árbol de trazabilidad (`evaluated_sources`, `echo_clusters`, `bridge_paths: [{from_secondary_url, to_candidate_url, anchor_text}]`) conservando **todas** las fuentes con sus razones de clasificación.

### 5.3 Protocolo del Agente en `skills/primary-source-search/SKILL.md`

La skill instruye al agente a ejecutar siempre 4 fases:
1. **Fase 1 — Definición dinámica del dominio (por el Agente)**:
   - Antes de lanzar búsquedas, el agente define para el tema concreto del usuario:
     - Qué cuenta como **evidencia primaria** y qué cuenta como **fuente secundaria** (advirtiendo qué tipo de PDFs o páginas oficiales podrían ser falsos primarios en ese tema).
     - Los **términos de búsqueda (`queries`)** adaptados al tema (incluyendo variantes técnicas o en el idioma donde residan los registros originales, sin usar plantillas fijas de otro tema).
     - Los **marcadores de evidencia (`agent_evidence_markers`)** propios del tema para pasarlos a `inspect_and_classify_source` / `compare_echo_and_trace`.
2. **Fase 2 — Búsqueda e inspección híbrida**:
   - El agente puede buscar con `search_web_candidates` del MCP y/o con `search_web` y el subagente `browser` (especialmente cuando la evidencia primaria sea visual, como un facsímil escaneado, o requiera interactuar con un portal web).
   - Toda fuente candidata (incluso si es `.pdf` o `.gov`) se pasa por `inspect_and_classify_source` o `compare_echo_and_trace` (o inspección directa verificada) para comprobar si contiene el registro original o si solo cita/resume a terceros.
3. **Fase 3 — Salto desde fuentes puente**:
   - Si una fuente es secundaria pero enlaza o nombra un documento primario concreto (*Secundaria Puente*), el agente sigue ese enlace o busca el identificador exacto del documento nombrado hasta verificar la fuente raíz.
4. **Fase 4 — Reporte final con listado explícito de secundarias y métricas**:
   - El reporte al usuario debe incluir obligatoriamente:
     1. **Evidencia Primaria Verificada**: documentos raíz confirmados, datos/imágenes extraídas y ruta de hallazgo (`búsqueda directa` o `vía fuente puente X`).
     2. **Fuentes Secundarias Encontradas (No descartadas en silencio)**: tabla o lista con **todas** las fuentes secundarias revisadas (incluyendo PDFs secundarios o páginas oficiales informativas), indicando su categoría (*Secundaria Puente*, *PDF/Sitio Oficial Secundario*, *Secundaria sin Trazabilidad*, *Clúster de Eco*) y la **razón específica** por la que se calificó como secundaria.
     3. **Métrica de Trazabilidad**: total de búsquedas, total de fuentes inspeccionadas, proporción primarias vs. secundarias y fricciones detectadas (páginas en blanco, fotos de stock, muros de cookies/newsletters, bucles sin raíz).

---

## 6. Lo que queda a criterio del implementador (What's left to the builder)

- **Implementación sin dependencias frágiles**: escribir `mcp/server.py` usando la biblioteca estándar de Python (`urllib.request`, `html.parser`, `json`, `re`, `math`, `collections`) con soporte opcional automático para `pypdf` / `pymupdf` (`fitz`) / `beautifulsoup4` si están instalados en el entorno Python local, de modo que el servidor MCP nunca falle al arrancar por falta de un paquete externo.
- **Manejo de tiempos de espera (timeouts)**: limitar cada descarga HTTP en el MCP a 8–10 segundos con un `User-Agent` estándar para que una página colgada no bloquee el lote.
- **Diseño del ícono `assets/logo.svg`**: crear un SVG limpio de alto contraste (lupa/grafo de nodos hacia documento raíz) para la tarjeta del plugin en la UI de Antigravity.
