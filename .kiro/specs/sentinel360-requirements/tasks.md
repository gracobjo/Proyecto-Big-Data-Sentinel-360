# Tareas de Implementación – Sentinel360 Requirements

## Estado actual

Referencia de alcance: `requirements.md` y `design.md` de esta misma spec.

---

## T1. Alinear ejecución Spark Fase II con modo dual (YARN/local)

- [x] Ajustar scripts de ejecución para soportar `--local` en Fase II.
- [x] Añadir en la UI Streamlit selector de perfil de recursos para Spark.
- [x] Forzar modo local con perfil **Seguro (evitar reinicios)**.
- [ ] Verificar en entorno limpio que YARN y local producen artefactos equivalentes en `cleaned/` y `enriched/`.

Requisitos cubiertos: R4.4, R4.5, RNF-1.3

---

## T2. Mejorar observabilidad operativa en Streamlit

- [x] Mostrar salida en tiempo real para comandos largos de Fase II.
- [x] Renderizar salida en contenedor con scroll y descarga de log.
- [x] Añadir bloque **Validar éxito (Airflow + HDFS)** en Fase II con comandos de comprobación.
- [ ] Añadir captura de evidencia "un clic" (guardar salida de validación en ruta de reporte dedicada).

Requisitos cubiertos: R13.2, R13.7, R13.8, RNF-6.1, RNF-6.4

---

## T3. Consolidar criterios de validación de éxito técnico

- [x] Definir criterios cruzados: reporte Airflow + escritura HDFS + logs locales.
- [x] Documentar comandos de validación en guías operativas.
- [ ] Automatizar una comprobación de semáforo (OK/WARN/FAIL) en UI según presencia de `_SUCCESS` y Parquet.

Requisitos cubiertos: R12.6, RNF-6.4

---

## T4. Robustecer Fase I ante dependencias opcionales

- [x] Evitar fallo total del DAG cuando OpenWeather no tenga API key disponible.
- [ ] Añadir aviso estructurado en reporte final del DAG indicando degradación funcional.

Requisitos cubiertos: R2.2, R12.6

---

## T5. Calidad y regresión

- [ ] Añadir tests automáticos para:
  - ejecución local de `clean_and_normalize.py` y `enrich_with_hive.py`,
  - generación de artefactos en `cleaned/` y `enriched/`,
  - presencia de bloque de validación en la vista Fase II (smoke test UI).
- [ ] Incluir validación de documentación en CI (links y secciones requeridas de la spec).

Requisitos cubiertos: RNF-4.2, RNF-4.3, RNF-6.1

---

## T6. Cerrar especificación de Fase I en UI y orquestación

- [x] Documentar validación técnica de Fase I desde Streamlit (Airflow/HDFS/Kafka/OpenWeather).
- [x] Documentar manejo degradado cuando falta `openweather_api_key` en Airflow.
- [x] Especificar priorización de datos reales frente a bloques demo en Fase I.
- [ ] Añadir prueba de aceptación que verifique ocultación de fallback cuando hay evidencia real reciente.

Requisitos cubiertos: R1.6, R2.4, R2.5, R13.9

---

## T7. Observabilidad en vivo de Spark/Kafka por fase

- [x] Incorporar en requisitos el acceso a Spark UI para seguimiento de ejecución.
- [x] Incorporar en diseño técnico la monitorización combinada Spark UI + YARN UI + topics Kafka.
- [ ] Exponer en Streamlit (fase correspondiente) botones/enlaces directos a Spark UI y YARN UI.
- [ ] Añadir comandos rápidos para inspección de topics (`raw-data`, `filtered-data`, `alerts`) y su estado.
- [ ] Validar en una ejecución real que la Spark UI refleja el job activo de streaming o batch.

Requisitos cubiertos: R7.9, R13.10, RNF-6.5
