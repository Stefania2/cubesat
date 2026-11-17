# STRaND-1 SCIENTIFIC VALIDATION

Módulo de validación, trazabilidad y reproducibilidad científica de la plataforma
STRaND-1 (https://cubesatstrand-1.vercel.app/validacion). Implementado el 2026-11-17
en la rama `validacion-cientifica`.

> **Regla de oro.** Si un resultado no puede demostrarse, no se presenta como validado.
> En el código: un `Resultado` en VALIDATED, FAILED o WARNING sin `ejecutado_utc` no
> puede construirse (`validacion_cientifica/estados.py`).

---

## 1. Diagnóstico de la arquitectura existente (fase 1)

| Pieza | Dónde | Qué hace | Observación relevante para la validación |
| --- | --- | --- | --- |
| Datos | PostgreSQL (Neon) `frames`, `observations`, `decoded_fields` | 36 641 tramas, 3 049 observaciones, 198 349 campos | No hay copia sellada; la ingesta no guardó las respuestas originales de la API |
| SatNOGS | `services/satnogs.py`, `tools/*.py` | ingesta DB y Network | Solo en local; Vercel es de solo lectura |
| Decodificación | `services/strand_amsat.py` | baliza AMSAT-UK → cuenta ADC → recta | Sin número de versión |
| SGP4 | `orbita_sgp4.py` | python-sgp4 2.27, TEME→terrestre por GMST IAU-82 | Sin pruebas contra referencias externas |
| TLE | `backend/app/data/geometria_observaciones.json` | TLE con que SatNOGS programó cada observación | Épocas desde finales de 2022 |
| Estado | `gemelo_digital/estado.py` | último valor conocido + edad | — |
| Diagnóstico | `gemelo_digital/anomalias.py` | z robusto (mediana + MAD) y canal enrielado | Umbral 6,0 sin referencia; la ventana incluye la lectura |
| Modelo 3D | `pages/GemeloDigital.tsx` → `/api/gemelo/estado` | color según el diagnóstico | La actitud no es un dato |
| Observaciones 3D | `/api/observations/{id}/paso` | pase SGP4 por observación | Independiente del cursor del gemelo |

Hallazgos que condicionan el diseño:

1. **El cursor del gemelo y la órbita no estaban unidos.** El modelo 3D avanza por eventos
   de telemetría; la posición orbital solo se calculaba por observación. La reconstrucción
   de este módulo es la primera pieza que asocia telemetría, gemelo, modelo 3D y órbita
   al mismo instante UTC.
2. **No hay TLE para casi toda la telemetría.** Telemetría decodificada: 2016-11-30 →
   2023-01-29. TLE históricos: desde finales de 2022 (SatNOGS Network no conserva
   observaciones anteriores). Para 2016-2022 la posición se informa como NOT_AVAILABLE.
3. **Empates de marca de tiempo.** En 552 instantes dos balizas distintas dan valores
   distintos de la misma magnitud con la misma marca (resolución de 1 s). El gemelo se
   queda con la «última» fila de una consulta que PostgreSQL no ordena entre empates. El
   archivo desempata por `id`, de forma estable. El gemelo no se modificó.
4. **El catálogo de TLE es una entrada mutable.** `geometria_observaciones.json` lo amplía la
   descarga de SatNOGS. En la primera versión de este módulo se leía de ahí, y la misma
   reconstrucción dio huellas distintas en Vercel y en local (el TLE «más cercano» había
   cambiado sin que cambiara ninguna huella). Ahora el catálogo se sella con el resto del
   archivo (`catalogo_tle.jsonl.gz`); `PROV-TLE-VIVO` avisa si el fichero vivo se ha movido, y
   `test_reconstruccion_no_depende_del_catalogo_vivo` impide que vuelva a ocurrir.
5. **3 187 tramas decodificadas dos veces** (33 476 filas duplicadas en `decoded_fields`,
   valores idénticos). No cambian ningún valor reconstruido; sí inflan recuentos por fila.

## 2. Arquitectura implementada (fase 2)

```
validacion_cientifica/           (raíz del repositorio; numpy, pandas, sgp4)
├── archivar.py      adquisición   sella la base en archivo/ (JSON Lines + SHA-256)
├── archivo/         ORIGINAL      tramas_originales, observaciones, catalogo_tle
│                    PROCESADA     tramas_clasificacion, campos_decodificados; sello.json
├── conjunto.py      archivo → DataFrames con la forma de gemelo_digital.datos
├── procedencia.py   módulo 1      huellas, verificación, versiones, ficha de procedencia
├── orbital.py       módulo 2      pruebas A–E, catálogo de TLE, posición histórica
├── telemetria.py    módulo 3      controles y ficha por variable
├── sincronizacion.py módulo 4     pruebas S1–S7, empates
├── reconstruccion.py módulos 5/7  reconstrucción reproducible y manifest.json
├── diagnosticos.py  módulo 6      fichas de los diagnósticos y su reproducibilidad
├── panel.py         resumen       ejecuta y agrupa todo
├── informe.py       informes      JSON y PDF (PDF escrito a mano, sin dependencias)
├── reproducir.py    CLI           generar / repetir una reconstrucción
├── ejecutar_pruebas.py CLI        pytest → resultados/pruebas_automatizadas.json
└── resultados/      divergencia_tle.json, pruebas_automatizadas.json, comparacion_base.json

telemetria_strand1/backend/app/routers/validacion.py   /api/validacion/*  (solo serializa)
telemetria_strand1/frontend/src/pages/ValidacionCientifica.tsx  /validacion (solo presenta)
tests/test_validacion_cientifica.py                    módulo 8
```

Principios:

* **No se duplica el procesamiento.** El módulo llama a `strand_amsat`, `orbita_sgp4`,
  `gemelo_digital.estado` y `gemelo_digital.anomalias`. Validar una copia no diría nada
  del código desplegado.
* **Adquisición, procesamiento, validación y visualización separadas.** Ningún cálculo
  científico vive en el router ni en el frontend.
* **Sin base ni red en tiempo de reconstrucción.** El archivo sellado y el catálogo de
  TLE viajan en el repositorio y en el despliegue (`.vercelignore` los incluye). Si Neon
  o SatNOGS desaparecen, las reconstrucciones siguen siendo reproducibles.
* **Ninguna dependencia nueva**, ni en Python ni en el frontend.

## 3. Módulo 1 — Data Provenance

* **Archivo sellado** (2,7 MB): cinco ficheros (cuatro de la base y el catálogo de TLE) JSON Lines con gzip determinista. Cada
  fila se serializa canónicamente (claves ordenadas, UTF-8, fechas ISO 8601 UTC con
  microsegundos, `null` = ausente). `sello.json` guarda, por fichero, el SHA-256 del
  contenido sin comprimir y del `.gz`, el número de filas y las versiones del código al
  sellar.
* **Verificación**: `procedencia.verificar_archivo()` recalcula las huellas (en cada
  arranque del servidor). `archivar.py --comparar` compara la base viva con el sello; tarda
  minutos contra Neon, así que se ejecuta en local y su resultado se registra con fecha.
* **Ficha de procedencia de cada trama** (`/api/validacion/procedencia/trama/{id}`):
  fuente original, observación, estación, fecha de recepción, fecha de medición
  (NO DISPONIBLE: la baliza no la lleva), fecha de ingesta, trama original y su SHA-256,
  estructura (nodo, canal, DATA_SIZE), y por cada valor: original (cuenta ADC), procesado,
  unidad, método de conversión, fuente y si el código vigente lo reproduce.
* **Versión del procesador**: SHA-256 del fichero fuente de cada pieza (el código no
  tenía números de versión; la huella lo identifica sin ambigüedad).

Limitaciones: las respuestas originales de la API de SatNOGS no se guardaron al ingerir;
la fecha de descarga desde SatNOGS no se registró (se conserva la de ingesta en la base).

## 4. Módulo 2 — Orbital Validation

| Id | Prueba | Referencia | Tolerancia |
| --- | --- | --- | --- |
| ORB-A / A-CAT | Formato, nº de línea, catálogo, NORAD 39090, checksum mód. 10 | Hoots y Roehrich (1980) | exacta |
| ORB-B | Repetibilidad bit a bit | — | 0 |
| ORB-C1 | Propagador de la plataforma vs `tcppver.out` (666 puntos) | Vallado et al. (2006) | 2e-7 km, km/s |
| ORB-C2 | Traducción a Python puro vs `tcppver.out` | Vallado et al. (2006) | 2e-7 |
| ORB-C2b | C++ vs Python puro con TLE reales de STRaND-1 | — | 1 mm |
| ORB-C3 | Elevación máxima y azimuts de SatNOGS (PyEphem) vs plataforma | SatNOGS Network | ±1,5°, ≥95 % |
| ORB-D1 | TEME→PEF→ITRF, ejemplo resuelto | Vallado et al. (2006), apéndice C | 1 m |
| ORB-D2 | Error de UT1≈UTC y sin polo | cota analítica | 0,52 km |
| ORB-D3 | Geodésica iterativa vs forma cerrada | Heikkinen (1982) | medio paso de redondeo |
| ORB-E | Cobertura de TLE del archivo | estudio empírico | — |

**Resultados (2026-11-17).** C1 y C2: 666 puntos, diferencia máxima 1,15e-7 km y 5,0e-10 km/s.
C2b: 1,3e-11 km. D1: 4,9e-8 km (0,05 mm) frente al ejemplo de Vallado — valida el GMST de la
plataforma. D2: 0,26 km de error por UT1≈UTC y sin polo, bajo la cota de 0,52 km. D3: dentro del
medio paso de redondeo. **C3: 870 observaciones de SatNOGS**; elevación máxima con mediana
|Δ| = 0,25° y p95 = 0,53°, el 98,7 % dentro de ±1,5°; azimuts con mediana 0,27° y p95 0,62°. Las
11 observaciones fuera de tolerancia discrepan también en azimut, lo que apunta a una ventana o
geometría del registro distinta de la usada al calcular. Se comprobó que SatNOGS publica el
máximo **dentro de la ventana programada**, no el del pase completo: con el máximo del pase la
discrepancia empeora (p95 1,2°). El estado «bad» de SatNOGS no discrimina: lo llevan todas las
observaciones comparadas, porque el satélite está inactivo.

**Honestidad sobre C1.** La extensión C++ de python-sgp4 *es* el código de Vallado
compilado: C1 descarta errores de empaquetado y de uso, no de algoritmo. Por eso existen
C2 (otra traducción, otro autor) y C3 (otra implementación completa, con datos reales).

**Modelo de tiempo y de Tierra de la plataforma** (documentado, no modificado): UTC; GMST
IAU-82 con UT1≈UTC; sin movimiento del polo ni ecuación de los equinoccios (TEME→PEF solo
con GMST, convención de Vallado); WGS-84 para estación y geodésica; WGS-72 interno de
SGP4; ECEF dextrógiro, longitud positiva al este, azimut desde el norte hacia el este; km
y km/s. El error de la simplificación queda por debajo de 0,52 km (ORB-D2): despreciable
frente al error del TLE.

**Antigüedad del TLE (criterio E).** No se fijó un umbral a ojo. Se propagó cada TLE
histórico de STRaND-1 hasta la época de los TLE de los 30 días siguientes (y viceversa) y
se midió la separación (`resultados/divergencia_tle.json`). Es una medida de
consistencia entre TLE, rotulada ESTIMADA. Tolerancias derivadas de la resolución de 1°
con que SatNOGS publica los ángulos:

| Propósito | Tolerancia | Antigüedad admisible (p95 ≤ tolerancia) |
| --- | --- | --- |
| Geometría vista desde una estación | 775 km · tan 1° = 13,5 km | 10 días |
| Punto subsatélite en el globo | (6378 + 775) km · 1° = 124,8 km | 30 días |

Más allá de 30 días (lo estudiado) la posición es **NOT_AVAILABLE**: no se propaga un TLE
cuyo error no está caracterizado, y nunca se usa el TLE actual para una fecha histórica.

## 5. Módulo 3 — Telemetry Validation

Controles sobre el archivo completo: errores de conversión (re-decodificación de los
198 349 valores desde `raw_hex` con el código vigente: 0 diferencias), duplicados de la
capa procesada, recepciones múltiples (1 678), inconsistencias temporales (antes del
lanzamiento del 2013-02-25, después de la ingesta, campo con fecha distinta de su trama),
balizas truncadas, balizas corruptas (89) y cuentas fuera del dominio de 10 bits (301).

Ficha por variable: identificador, descripción (catálogo HMTA), fuente documental (hoja de
AMSAT-UK), nodo/canal, unidad, conversión, resolución (|m| por cuenta, derivada de la
recta), rango de referencia (solo el dominio del convertidor está documentado), lecturas
en la ordenada de la recta (cuenta 0: el canal no mide), disponibilidad y dos estados
separados: **integridad** del dato y **validación física**. Esta última es NOT_VERIFIED en
todas las magnitudes: no existe rango de operación documentado de ningún componente. Las
variables que la hoja define pero STRaND-1 nunca emitió (temperaturas, corrientes de
batería y de bus) aparecen como NOT_AVAILABLE, nunca como cero.

## 6. Módulo 4 — Temporal Synchronization

Referencia única: UTC (`tiempo.instante_utc` rechaza fechas sin zona). Métodos de
asociación: `coincidencia_exacta`, `muestra_anterior_mas_cercana` (retención de muestra,
la regla del gemelo; se informa el desfase y la medición siguiente sin combinarlas),
`valor_calculado` (órbita), `no_disponible`. **Interpolación: no se aplica a ninguna
variable**; los estados de los interruptores son discretos.

Pruebas por reconstrucción: S1 referencia única, S2 evento del gemelo = último ≤ t, S3
telemetría = instantánea del gemelo, S4 órbita calculada exactamente en t, S5 sin
interpolación, S6 modelo 3D con el diagnóstico del instante, S7 ninguna medición
posterior a t. `SYNC-GLOBAL` las repite en 25 instantes repartidos (eventos exactos,
puntos intermedios, antes y después del archivo). Además, la prueba de integración
`test_modelo_3d_del_gemelo_coincide_con_la_reconstruccion` llama al **router real del
gemelo** (`/api/gemelo/estado`) y compara su estado visual y sus lecturas con la
reconstrucción.

## 7. Módulo 6 — Diagnostic Validation

| Diagnóstico | Fórmula | Ventana | Umbral | Justificación |
| --- | --- | --- | --- | --- |
| z robusto | (x − med) / (1,4826·MAD) | 51 lecturas, mín. 25, incluye la lectura; ≤ 30 días | 3,5 | Iglewicz y Hoaglin (1993) |
| | | | 6,0 | Parámetro del proyecto, **sin respaldo bibliográfico** |
| Canal enrielado | rango ≤ 1e-3·|mediana| | 20 lecturas | 1e-3 | Parámetro del proyecto |

Ventanas incompletas: < 25 lecturas → `sin_referencia`; 25–50 → ventana parcial; ventana
de más de 30 días → `sin_referencia`. MAD = 0 → z indefinido, lo decide el enrielado.

Escala de interpretación usada en informes: sin desviación → comportamiento inusual
(|z| ≥ 3,5) → anomalía estadística (|z| ≥ 6) → posible anomalía operacional (canal
enrielado) → **falla confirmada: nunca** desde estadística. La etiqueta «CRÍTICO» del
modelo 3D es una codificación visual de la plataforma, no una afirmación sobre el
satélite.

Hallazgo documentado: el docstring de `zscore_robusto` dice «lecturas previas», pero la
ventana de pandas incluye la lectura evaluada. No se cambió (alteraría el gemelo).

## 8. Módulos 5 y 7 — Reconstrucción y manifest

`reconstruccion.reconstruir(t)` devuelve telemetría (con método, desfase, frescura y
trama de origen), gemelo (evento, pase), modelo 3D, órbita (TLE, antigüedad, propagación
completa o NOT_AVAILABLE), diagnóstico y procedencia. Es determinista.

`manifest.json` contiene: misión y NORAD, id de la reconstrucción (huella de las
entradas), instante, fuente de telemetría, observaciones, tramas usadas con `raw_hex` y
SHA-256, huellas del archivo, TLE, época, fuente orbital, versión de SGP4, marco, modelos
de tiempo y Tierra, versiones (huella de cada pieza de código, bibliotecas, commit),
parámetros estadísticos, métodos de sincronización, versión de la aplicación, SHA-256 de
los resultados y referencias a los ficheros originales y derivados. Lo desconocido es
`null` (p. ej. `orbita.sgp4` cuando no hay TLE cercano; `commit` en despliegues por CLI, que no
definen `VERCEL_GIT_COMMIT_SHA`). `cambios_sin_confirmar` dice si la copia local difiere del
commit: en ese caso la identidad exacta del código son las huellas de `versiones.codigo`.

**Casos de regresión** (fijados el 2026-11-17 sobre el archivo sellado):

| Caso | Valor |
| --- | --- |
| 2021-03-01T12:00:00Z → evento del gemelo | 2021-02-28T19:30:25Z |
| battery_voltage en ese instante | 9,7488 V (ordenada de la recta: canal sin medida) |
| estado del modelo 3D | INSTRUMENTACION_PERDIDA |
| trama 17348 `C0800206022C03020000` | battery_0_voltage 9,7488 V, cuenta 0 |
| lecturas de battery_voltage | 5 269 |

## 9. Pruebas automatizadas (módulo 8)

`tests/test_validacion_cientifica.py`: unitarias (TLE, SGP4, coordenadas, unidades,
estadística, hashes, tiempo), integración (archivo, re-decodificación, SatNOGS, API
SatNOGS en vivo — omitida salvo `SATNOGS_EN_VIVO=1` —, sincronización, modelo 3D vía
router del gemelo, manifest, informes, API) y regresión. Cada caso registra esperado,
obtenido y tolerancia (`record_property`).

Resultado el 2026-11-17: **50 aprobadas, 1 omitida** (SatNOGS en vivo, NOT_VERIFIED) en la suite
de validación; suite completa del repositorio **278 aprobadas, 1 omitida, 0 fallos**.

```bash
cd cubesat
../strand/bin/python -m pytest tests/test_validacion_cientifica.py
../strand/bin/python -m validacion_cientifica.ejecutar_pruebas      # registra el resultado para la interfaz
```

## 10. Reproducir una reconstrucción histórica

```bash
cd cubesat
# 1. generar: manifest.json, informe.json e informe.pdf
../strand/bin/python -m validacion_cientifica.reproducir --instante 2021-03-01T12:00:00Z --salida /tmp/rec
# 2. repetir desde el manifest (sin base de datos ni red): todo VALIDATED
../strand/bin/python -m validacion_cientifica.reproducir /tmp/rec/manifest.json
```

Desde la interfaz: `/validacion` → G · Reproducibilidad → «Descargar manifest.json», y
después subirlo en «Verificar un manifest».

## 11. Mantenimiento y despliegue

* **Origen del sello vigente**: la copia local de PostgreSQL (36 641 / 3 049 / 36 641 / 198 349
  filas). Las tres primeras tablas dieron exactamente las mismas huellas leídas desde Neon; la
  comparación completa con Neon queda en `resultados/comparacion_base.json`. Leer Neon a
  través del pooler tarda minutos y una consulta única llegó a colgarse 27 min: por eso
  `archivar.py` pagina por clave (10 000 filas) con reintentos.
* **Renovar el sello** cuando la base cambie (nueva ingesta):
  `../strand_api/bin/python -m validacion_cientifica.archivar --forzar`, después
  `--comparar`, y volver a ejecutar las pruebas. Un manifest antiguo dejará de
  reproducirse (REP-DATOS FAILED): es lo correcto, sus entradas ya no existen.
* **Ampliar el catálogo de TLE**: `telemetria_strand1/tools/descargar_geometria_observaciones.py`,
  volver a sellar (el catálogo forma parte del sello) y regenerar el estudio de divergencia
  (`ORB-E-ESTUDIO` avisa si se calculó con otro catálogo):
  `../strand/bin/python -c "import json; from validacion_cientifica import orbital as O; O.DIVERGENCIA.write_text(json.dumps(O.estudio_divergencia(), ensure_ascii=False, indent=1)+'\n')"`.
* **Despliegue**: igual que el resto (`vercel deploy --prod` desde `cubesat/`). El paquete y
  el archivo (2,6 MB) están en la lista blanca de `.vercelignore`. Sin variables nuevas.

## 12. Limitaciones conocidas

Ver `informe.LIMITACIONES`. Las principales: sin TLE para 2016-2022; sin rangos de
operación documentados; sin fecha de medición en la baliza; respuestas originales de
SatNOGS no archivadas en la ingesta; la comparación base↔archivo no puede ejecutarse en
Vercel; el criterio de antigüedad se estimó con TLE de 2022-2026, en época de máximo solar.

## Referencias

* Vallado, D. A., Crawford, P., Hujsak, R. y Kelso, T. S. (2006). *Revisiting Spacetrack
  Report #3*. AIAA/AAS Astrodynamics Specialist Conference, AIAA 2006-6753.
* Hoots, F. R. y Roehrich, R. L. (1980). *Spacetrack Report No. 3: Models for Propagation
  of NORAD Element Sets*.
* Heikkinen, M. (1982). Geschlossene Formeln zur Berechnung räumlicher geodätischer
  Koordinaten aus rechtwinkligen Koordinaten. *Zeitschrift für Vermessungswesen*, 107.
* Iglewicz, B. y Hoaglin, D. C. (1993). *How to Detect and Handle Outliers*. ASQC.
* NIST FIPS 180-4, *Secure Hash Standard*.
* AMSAT-UK, «STRAND-1 Packet Format» (`amsat-strand-1-20130327.xlsx`).
* SatNOGS Network API, `/api/observations/`.

No se aplicó ningún estándar CCSDS concreto: el formato del archivo y del manifest es
propio del proyecto. Citar uno sin haber seguido su especificación sería atribuir una
conformidad que no se ha comprobado.
