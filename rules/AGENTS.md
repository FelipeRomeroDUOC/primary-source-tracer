# Primary Source Tracer Rules

Cuando el usuario pida buscar evidencia primaria, verificar la fuente original de una afirmación o auditar la trazabilidad de información en internet:

1. Activa y sigue la skill `primary-source-search`.
2. Define dinámicamente los términos de búsqueda (`queries`) y los marcadores probatorios (`agent_evidence_markers`) según el tema solicitado por el usuario; nunca asumas términos predefinidos de otro dominio.
3. Incluye siempre consultas tanto para el **registro o estudio fundacional** donde nació la afirmación como para **réplicas independientes, mediciones de contraste o meta-análisis/auditorías posteriores** que la hayan confirmado o refutado.
4. Nunca clasifiques una fuente como primaria solo por estar en formato `.pdf` o en un dominio oficial (`.gov`, `.gob`, `.edu`); verifica con `inspect_and_classify_source` o `compare_echo_and_trace` si contiene datos/registros primarios propios o si es un resumen/comunicado secundario (`official_or_pdf_but_secondary`).
5. No descartes en silencio las fuentes secundarias: lístalas siempre al usuario junto con la razón explícita por la que fueron clasificadas como secundarias y si actuaron como Fuente Puente o parte de un Clúster de Eco.
