---
name: primary-source-search
description: Protocolo agnóstico al dominio para buscar y verificar evidencia primaria en internet, contrastar estudios o registros fundacionales con réplicas y auditorías posteriores, saltar fuentes puente, detectar bucles de eco y listar explícitamente las fuentes secundarias con enlaces directos verificables y la razón de su clasificación.
---

# Primary Source Search & Traceability

Usa esta skill cada vez que el usuario pida buscar **evidencia primaria**, verificar el sustento real de una afirmación en internet, auditar la trazabilidad de fuentes o separar documentos raíz del ruido y eco secundario.

## Principios Inquebrantables

1. **100 % Agnóstico al Tema (El Agente define el vocabulario)**:
   - Nunca uses términos de búsqueda ni marcadores fijos de otro dominio.
   - Antes de buscar, **tú (el agente)** debes determinar qué consultas (`queries`) y qué marcadores probatorios (`agent_evidence_markers`: unidades, identificadores de registro, términos de archivo, estructuras esperadas) corresponden específicamente al tema solicitado por el usuario.
2. **Cobertura de Origen + Contraste Posterior (Replicación / Refutación)**:
   - Buscar únicamente el documento donde nació una afirmación puede sesgar el resultado si ese registro inicial tenía limitaciones metodológicas, muestras pequeñas o fue refutado después.
   - Siempre que el tema involucre una afirmación empírica, científica, técnica o estadística, debes dividir tus consultas (`queries`) en dos ramas:
     - **Rama Fundacional**: localizar el registro, documento o experimento original donde se originó la afirmación.
     - **Rama de Contraste / Replicación**: localizar estudios, mediciones o registros posteriores independientes con datos propios que hayan puesto a prueba, confirmado, corregido o refutado el hallazgo inicial, así como síntesis cuantitativas o auditorías agregadas.
3. **Filtro contra "Falsos Primarios" (`official_or_pdf_but_secondary`)**:
   - **Que un documento sea `.pdf` o provenga de un dominio oficial (`.gov`, `.gob`, `.edu`, organismos públicos) NO lo convierte automáticamente en fuente primaria.**
   - Si un PDF o página oficial es un comunicado de prensa, boletín informativo, resumen normativo sin datos empíricos o documento que atribuye el dato clave a terceros (*"según..."*, *"according to..."*), debes clasificarlo como **Secundario** (`official_or_pdf_but_secondary`).
   - Recuerda que `preliminary_classification` es una **señal estructural inicial**, no un veredicto final: si al leer el contenido detectas que una fuente es una revisión narrativa, póster/preprint sin revisión por pares o ficha bibliográfica, corrige y explica su rol real.
4. **Prohibido Descartar Fuentes Secundarias en Silencio**:
   - No ocultes las fuentes secundarias visitadas. Debes listarlas al usuario en una sección dedicada indicando **su enlace directo clickable**, **por qué** fueron calificadas como secundarias y si sirvieron como **Fuente Puente** o fueron un **Callejón sin salida / Eco**.
5. **Links Directos y Epistemología Explícita**:
   - **Toda fuente citada** (primaria, réplica, meta-análisis o secundaria) debe incluir su **enlace directo clickable** en formato Markdown (`[Título o dominio](URL_exacta)` o `file:///...` para rutas locales) copiado literalmente de la salida de las herramientas; nunca acortes al dominio raíz ni inventes URLs.
   - Etiqueta el estado de acceso junto al enlace cuando corresponda (`[Texto completo verificado]`, `[PDF abierto]`, `[Solo abstract / paywall]`, `[Error SSL / 403 / 404]`).
   - Separa siempre con claridad qué fue **observado directamente** en el documento, qué proviene **atribuido a otra fuente** (indicando cuál) y qué no pudo verificarse (prohibido presentar datos recordados de memoria como si hubieran sido verificados por la herramienta).

---

## Flujo de Trabajo en 4 Fases

### Fase 1: Discernimiento Dinámico del Dominio
Antes de lanzar la primera búsqueda, define explícitamente para el tema del usuario:
1. **Qué constituye Evidencia Primaria Fundacional** (el registro, documento, acta o experimento original donde nace el dato).
2. **Qué constituye Evidencia Primaria de Replicación / Contraste** (mediciones o experimentos independientes posteriores con datos crudos propios a favor o en contra) y **Qué constituye Fuente Compilada de 2.º Orden** (meta-análisis, revisiones sistemáticas cuantitativas o auditorías oficiales que agregan múltiples registros primarios).
3. **Qué constituye Fuente Secundaria** (incluyendo qué falsos primarios en PDF o sitios oficiales podrían aparecer).
4. **Consultas dinámicas (`queries`)** —cubriendo tanto el origen como las réplicas/contrastes posteriores— y **Marcadores probatorios (`agent_evidence_markers`)** propios del tema.

### Fase 2: Búsqueda e Inspección Estructural
1. Descubre candidatos combinando:
   - `search_web_candidates(queries=...)` del servidor MCP `primary-source-tracer`, y
   - si `search_web_candidates` reporta `search_friction` (p. ej. bloqueo anti-bot en DuckDuckGo) o necesitas cobertura de prensa/medios/portales generales, combina con tu **búsqueda web nativa** (`search_web` o equivalente) y el subagente `browser` cuando se requiera inspección visual interactiva.
2. Evalúa las fuentes candidatas con `inspect_and_classify_source(url_or_path=..., agent_evidence_markers=...)` o en lote con `compare_echo_and_trace(urls=..., agent_evidence_markers=..., follow_bridge_links=True)`.

### Fase 3: Salto desde Fuentes Puente y Manejo de Paywalls / Fuentes Inaccesibles
1. **Salto desde Fuentes Puente (*Link-Hopping*)**:
   - Si una página es secundaria pero enlaza a un documento candidato (`secondary_bridge`) o menciona el identificador exacto de un documento oficial, réplica o auditoría, da el salto hacia ese enlace o busca el identificador exacto hasta verificar el documento raíz.
2. **Protocolo ante Paywalls (`paywalled_abstract_only`) y Bloqueos Técnicos (`unreachable_or_empty`)**:
   - **Prohibido evadir controles de acceso o desactivar seguridad (SSL/paywalls)**: nunca intentes saltar un muro de pago ni dar por verificado el documento completo si solo es visible el *abstract*.
   - **Paso A — Inspección obligatoria de copia abierta (*Green Open Access*)**: cuando una fuente sea clasificada como `paywalled_abstract_only` y el servidor devuelva `open_access_resolution.oa_pdf_url` (o aparezca un enlace abierto a PMC/repositorio `.edu`/`.pdf`), **debes llamar a `inspect_and_classify_source` sobre esa URL abierta** antes de concluir que solo viste el resumen. Si no aparece por DOI, toma el título exacto y autores para buscar copias legítimas depositadas en repositorios universitarios (`.edu`/`.ac`) o archivos públicos.
   - **Paso B — Operación sin navegador y PDFs escaneados**: cuando un PDF es un facsímil escaneado sin capa OCR (`[SCANNED_FACSIMILE_PDF]`), en modo local el servidor renderiza las páginas a PNG en `rendered_page_images` (léelas con `read_file`) y en modo remoto (`--http`) adjunta bloques de imagen MCP directamente; úsalos para leer el documento antes de declararlo ilegible. Si un servidor devuelve `HTTP 403`, SSL inválido, desafío anti-bot (`Client Challenge`) o carga vacía, regístralo como fricción técnica y busca un espejo documental o recurre al subagente `browser` si está disponible en tu entorno.
   - **Paso C — Declaración transparente cuando no exista copia abierta**: si tras buscar copias abiertas el texto completo sigue restringido, repórtalo bajo la etiqueta **`Primaria Identificada pero Restringida (Solo Abstract / Metadatos verificados)`**, detallando qué confirma el resumen público y qué partes (tablas, datos crudos) quedaron sin verificar tras el paywall.
3. **Protocolo Híbrido para Evidencia Audiovisual (Imágenes y Videos)**:
   - **Descubrimiento vía búsqueda web nativa**: delega a tu búsqueda web nativa el descubrimiento de entrevistas, ruedas de prensa, reportajes en primera persona o evidencia gráfica relevante (y en Gemini aprovecha su soporte nativo de YouTube si está disponible).
   - **Inspección con el MCP**:
     - **Videos de YouTube**: pásalos a `inspect_and_classify_source` para obtener título, canal, enlaces puente de la descripción y transcripción con marcas de tiempo clickables (`timestamp_url`, ej. `https://youtu.be/<id>?t=134`). Si el video no tiene subtítulos ni pudo procesarse, decláralo explícitamente sin inventar lo que dice.
     - **Imágenes informativas y directas**: cuando una página reporte gráficos, actas o fotos relevantes en `content_images`, o tengas una URL directa (`.png`/`.jpg`/`.webp`), llámala con `inspect_and_classify_source` para recibirla como imagen MCP e inspeccionarla visualmente.
   - **Clasificación audiovisual honesta**: distingue entre **Evidencia Primaria Audiovisual** (entrevista directa al protagonista, testimonio en primera persona, rueda de prensa oficial, grabación de un hecho o gráfico con datos originales) y **Video / Imagen Secundaria** (divulgador comentando a terceros, compilación, foto de stock o captura sin contexto).

### Fase 4: Reporte Transparente y Métrica
Presenta siempre el resultado con estas secciones y **con enlace clickable directo en cada entrada**:

1. **Evidencia Primaria Confirmada (Fundacional y de Replicación/Contraste)**:
   - Separa claramente:
     - **A. Evidencia Primaria Fundacional**: documento o registro original verificado, `[título/identificador](URL)` con etiqueta de acceso y datos observados directamente (separando lo verificado en el texto de lo atribuido en terceros o no verificado).
     - **B. Evidencia Primaria de Replicación / Contraste Posterior**: estudios o mediciones independientes posteriores con datos propios que confirman, matizan o refutan el registro inicial, con su `[enlace](URL)` y estado de verificación.
2. **Fuentes Compiladas / Meta-análisis / Auditorías (2.º orden)** *(si aplica)*:
   - Síntesis cuantitativas, meta-análisis o auditorías oficiales que recopilan y evalúan estadísticamente múltiples registros primarios (distinguiendo si son preprints/pósters preliminares sin revisión por pares), con su `[enlace](URL)`.
3. **Fuentes Secundarias Evaluadas (con enlace directo y razón explícita)**:
   - Lista o tabla con **todas** las fuentes secundarias revisadas (incluyendo PDFs secundarios y páginas `.gov`/oficiales informativas), con su `[enlace directo](URL)`, subtipo y razón concreta:
     - `Secundaria Puente`: no es primaria, pero enlazó o dio el identificador exacto de un documento primario o réplica.
     - `PDF / Sitio Oficial Secundario` (`official_or_pdf_but_secondary`): proviene de un PDF o dominio institucional pero es un comunicado de prensa, resumen normativo o cita a terceros sin registro primario propio.
     - `Secundaria respecto al estudio consultado`: documento que tiene datos propios sobre otro subtema, pero que respecto a la afirmación auditada solo la cita en su marco teórico o introducción.
     - `Secundaria sin Trazabilidad`: cita o repite afirmaciones sin enlazar al documento original.
     - `Clúster de Eco`: agrupa artículos que repiten prácticamente el mismo texto; verifica en `matched_excerpts` e indica explícitamente si se trata de **eco periodístico real** o de un **falso positivo por plantilla compartida** (ej. cabecera de repositorio o catálogo).
4. **Métrica de Esfuerzo y Fricción**:
   - Total de búsquedas ejecutadas (MCP + web nativa si aplicó), total de fuentes inspeccionadas (primarias fundacionales, primarias de contraste, compiladas de 2.º orden y secundarias) y fricciones encontradas (desafíos anti-bot / `search_friction`, portales en blanco/rotos, certificados SSL, muros de pago o imágenes de stock).
5. **Dossier HTML con Embeds Audiovisuales (cuando haya videos/imágenes relevantes o el usuario lo pida)**:
   - Llama a `generate_evidence_html(topic, verdict, primary_sources, secondary_sources, notes, ...)` para generar un dossier HTML autocontenido con embeds de YouTube (`youtube-nocookie.com/embed/<id>?start=<segundos>`), figuras `<figure>` para imágenes/gráficos verificados, botones de respaldo clickables (por si el sandbox bloquea iframes) y la tabla colapsable de fuentes secundarias.
   - Si tu cliente soporta **Artifacts / Canvas** (como Claude.ai o Gemini), presenta ese HTML como artefacto interactivo; si trabajas en local, guárdalo en un archivo `.html` y entrégale el enlace clickable al usuario.
