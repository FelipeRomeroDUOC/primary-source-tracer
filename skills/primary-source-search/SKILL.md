---
name: primary-source-search
description: Protocolo agnóstico al dominio para buscar y verificar evidencia primaria en internet, contrastar estudios o registros fundacionales con réplicas y auditorías posteriores, saltar fuentes puente, detectar bucles de eco y listar explícitamente las fuentes secundarias con la razón de su clasificación.
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
4. **Prohibido Descartar Fuentes Secundarias en Silencio**:
   - No ocultes las fuentes secundarias visitadas. Debes listarlas al usuario en una sección dedicada indicando **por qué** fueron calificadas como secundarias y si sirvieron como **Fuente Puente** o fueron un **Callejón sin salida / Eco**.

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
   - `search_web_candidates(queries=...)` del servidor MCP `primary-source-tracer`, y/o
   - `search_web` y el subagente `browser` (especialmente cuando se requiera verificar evidencia visual como documentos escaneados o interactuar con portales web).
2. Evalúa las fuentes candidatas con `inspect_and_classify_source(url_or_path=..., agent_evidence_markers=...)` o en lote con `compare_echo_and_trace(urls=..., agent_evidence_markers=..., follow_bridge_links=True)`.

### Fase 3: Salto desde Fuentes Puente y Manejo de Paywalls / Fuentes Inaccesibles
1. **Salto desde Fuentes Puente (*Link-Hopping*)**:
   - Si una página es secundaria pero enlaza a un documento candidato (`secondary_bridge`) o menciona el identificador exacto de un documento oficial, réplica o auditoría, da el salto hacia ese enlace o busca el identificador exacto hasta verificar el documento raíz.
2. **Protocolo ante Paywalls (`paywalled_abstract_only`) y Bloqueos Técnicos (`unreachable_or_empty`)**:
   - **Prohibido evadir controles de acceso o desactivar seguridad (SSL/paywalls)**: nunca intentes saltar un muro de pago ni dar por verificado el documento completo si solo es visible el *abstract*.
   - **Paso A — Extracción de identificadores y búsqueda de copia abierta (*Green Open Access*)**: cuando una fuente sea clasificada como `paywalled_abstract_only`, el servidor MCP consulta automáticamente la API abierta de **OpenAlex** con el DOI detectado (`open_access_resolution`) e inyecta el enlace `oa_pdf_url` en `outbound_links` si existe una copia abierta. Si no aparece por DOI, toma el título exacto y autores para buscar copias legítimas depositadas en repositorios universitarios (`.edu`/`.ac`) o archivos públicos.
   - **Paso B — Operación sin navegador y PDFs escaneados**: cuando un PDF es un facsímil escaneado sin capa OCR (`[SCANNED_FACSIMILE_PDF]`), el servidor MCP renderiza automáticamente sus primeras páginas a archivos `.png` locales en `rendered_page_images`; léelos directamente con `read_file` sin necesitar navegador. Si un servidor devuelve `HTTP 403`, SSL inválido o carga en blanco por requerir JavaScript, regístralo como fricción técnica y busca un espejo documental o solo recurre al subagente `browser` si está disponible en el entorno y se trata de un registro único.
   - **Paso C — Declaración transparente cuando no exista copia abierta**: si tras buscar copias abiertas el texto completo sigue restringido, repórtalo bajo la etiqueta **`Primaria Identificada pero Restringida (Solo Abstract / Metadatos verificados)`**, detallando qué confirma el resumen público y qué partes (tablas, datos crudos) quedaron sin verificar tras el paywall.

### Fase 4: Reporte Transparente y Métrica
Presenta siempre el resultado con estas secciones:

1. **Evidencia Primaria Confirmada (Fundacional y de Replicación/Contraste)**:
   - Separa claramente:
     - **A. Evidencia Primaria Fundacional**: documento o registro original verificado, URL/ruta y datos observados directamente.
     - **B. Evidencia Primaria de Replicación / Contraste Posterior**: estudios o mediciones independientes posteriores con datos propios que confirman, matizan o refutan el registro inicial.
2. **Fuentes Compiladas / Meta-análisis / Auditorías (2.º orden)** *(si aplica)*:
   - Síntesis cuantitativas, meta-análisis o auditorías oficiales que recopilan y evalúan estadísticamente múltiples registros primarios.
3. **Fuentes Secundarias Evaluadas (con razón explícita)**:
   - Lista o tabla con **todas** las fuentes secundarias revisadas (incluyendo PDFs secundarios y páginas `.gov`/oficiales informativas), especificando su subtipo:
     - `Secundaria Puente`: no es primaria, pero enlazó o dio el identificador exacto de un documento primario o réplica.
     - `PDF / Sitio Oficial Secundario` (`official_or_pdf_but_secondary`): proviene de un PDF o dominio institucional pero es un comunicado de prensa, resumen normativo o cita a terceros sin registro primario propio.
     - `Secundaria respecto al estudio consultado`: documento que tiene datos propios sobre otro subtema, pero que respecto a la afirmación auditada solo la cita en su marco teórico o introducción.
     - `Secundaria sin Trazabilidad`: cita o repite afirmaciones sin enlazar al documento original.
     - `Clúster de Eco`: agrupa artículos que repiten prácticamente el mismo texto.
   - Para cada una, incluye la **razón concreta** de por qué se calificó como secundaria.
4. **Métrica de Esfuerzo y Fricción**:
   - Total de búsquedas ejecutadas, total de fuentes inspeccionadas (primarias fundacionales, primarias de contraste, compiladas de 2.º orden y secundarias) y fricciones encontradas (imágenes de bancos de stock, portales en blanco/rotos, muros de pago o cookies/newsletters).
