# Auditoría, validación y corrección del gemelo digital de comunicaciones RF de STRaND-1

**Fecha:** 13 de octubre de 2026 · **Rama:** `auditoria-gemelo-rf` (parte de `despliegue-neon-vercel`)

Este documento recoge qué se encontró, por qué ocurría, qué se cambió, cómo se comprobó y qué
sigue sin poder afirmarse. Las cifras de resultados no se repiten aquí: viven en
`resultados_simulacion/` y llegan al [informe](INFORME_TECNICO_FINAL.md), al README, a
`index.html` y a la web por generadores, con pruebas que fallan si alguno se queda atrás.

> **Estado de despliegue.** Los cambios están probados **en local** y confirmados en la rama
> `auditoria-gemelo-rf`. **No se han publicado**: ni en `origin`, ni en GitHub Pages, ni en
> https://cubesatstrand-1.vercel.app, que sigue mostrando la versión anterior.

---

## 1. Inventario de la fase inicial

Línea base reproducida antes de tocar nada: `pytest` → 30 pruebas pasan; el pipeline documentado
se ejecuta completo. Hipótesis de la revisión preliminar, verificadas contra el código, los
resultados y la API desplegada:

| # | Hipótesis | Estado | Evidencia |
|---|---|---|---|
| H1 | El proyecto se contradice sobre la modulación (FSK frente a BPSK) | **Confirmada** | `Hero.tsx` y `Docs.tsx` decían FSK 9600; `calcular_link_budget.py`, `comparar_con_cubesats_reales.py`, el informe (§9, §13) y `Simulacion.tsx` daban BPSK como característica del satélite |
| H2 | *Advanced* dice que ningún frame es baliza; el Dashboard cuenta 32 754 | **Confirmada** | Texto fijo en `Advanced.tsx`; `/api/frames/kpis` devuelve 32 754 |
| H3 | *Simulación RF* muestra 8,23 °/s, 2,62° y 0,09 dB | **Confirmada** | Constantes en `Simulacion.tsx`; `estacion_terrena_seguimiento.json` da 0,77° y 0,01 dB |
| H4 | *Enlace RF* muestra 1 bit de diferencia sin simular | **Confirmada** | `GET /api/enlace/integrity` en producción: `diferencia: 1` con `sim_status: IDLE` |
| H5 | Corrientes de 508–528 mA y tensiones negativas sospechosas | **Confirmada** | Coinciden con la ordenada `c` de cada recta de calibración: cuenta ADC = 0 |
| H6 | «BPSK 9600 es el estándar de facto» sin sustento | **Confirmada** | Frase en `Simulacion.tsx` y en la tabla de comparación, con porcentajes atribuidos a Bouwmeester & Guo no verificables |
| H7 | La web no distingue simulado, histórico y derivado | **Confirmada** | Ninguna página etiquetaba la clase de dato |
| H8 | FEC, AX.25 y sin codificar se comparan en condiciones distintas | **Confirmada, y peor** | Ver C1–C4 |
| H9 | El Doppler «orbital variable» es un desplazamiento fijo | **Confirmada** | Constante de 150 Hz; el Doppler del paso es ±9,8 kHz |
| H10 | La reserva de implementación se cuenta dos veces | **Refutada** | Se sumaba una sola vez; lo que faltaba era declarar qué es y no sumarla al umbral del receptor simulado |
| H11 | La FER se muestra como N/A habiendo datos | **Parcial** | En *Enlace RF* el N/A es correcto (cadena sin tramas); la FER del modelo avanzado sí existía como recuento y no se calculaba ni se mostraba |
| H12 | `ax25_frames_validos` no llega de forma consistente a la web | **Confirmada** | Valía `0` en configuraciones sin AX.25 (un cero donde debía ir «no aplica») y no llegaba al frontend |

Hallazgos nuevos, no previstos en la revisión preliminar:

| # | Hallazgo | Evidencia |
|---|---|---|
| N1 | `modelo_estacion_terrena.py` no restaba la pérdida de polarización | C/N0 1 dB por encima del link budget en la misma geometría |
| N2 | El canal Rice tenía la mitad de potencia difusa | K efectivo de 13 dB declarando 10; potencia media (2K+1)/(2K+2) |
| N3 | BER > 0,5 en los resultados publicados | Ambigüedad de 180° del lazo de Costas sin resolver: flujo invertido |
| N4 | La PER «medida» del 64,2 % estaba inflada | Restaba contadores de balizas consecutivas con dos paquetes por segundo en orden arbitrario |
| N5 | El panel *Enlace RF* marcaba 9,75 V de batería como NORMAL | Límites «nominales» deducidos de la propia recta; un test lo fijaba como «tensión real» |
| N6 | *Status: ACTIVE* fijo en la portada | SatNOGS DB marca el transmisor como *inactive* |
| N7 | Las tarjetas de anomalías mezclaban unidades | *critical/warning* cuentan hallazgos; *normal/unknown*, frames; todas decían «frames» |
| N8 | Dos referencias bibliográficas no localizables | Refs. 16 y 17 del informe |

---

## 2. Informe de auditoría

Prioridad: **C** crítica, **A** alta, **M** media.

### Modulación y presupuesto de enlace

| ID | Pr. | Problema | Causa raíz | Archivo |
|---|---|---|---|---|
| M1 | C | BPSK presentada como modulación de STRaND-1 | Valor escrito a mano como «dato real» en la tabla de CubeSats; el resto lo heredó | `comparar_con_cubesats_reales.py`, `calcular_link_budget.py`, informe, web |
| M2 | C | Umbral de 10,0 dB fijo «para BPSK ~1e-5» | Número huérfano, no calculado de la curva ni ligado al esquema | `calcular_link_budget.py` |
| M3 | A | Campo `snr_requerida_db` para una Eb/N0 | Nomenclatura que confunde SNR con Eb/N0 | ídem |
| M4 | A | Estación terrena sin pérdida de polarización (N1) | Constantes duplicadas por script | `modelo_estacion_terrena.py` |
| M5 | A | Margen solo como barrido por elevación | No se encadenaba SGP4 con el presupuesto | — |
| M6 | A | Parámetros sin procedencia ni sensibilidad | Supuestos de diseño presentados junto a datos documentados | varios |

**Resolución de la modulación** (lo que cada afirmación puede sostener):

| Aspecto | Qué consta | Fuente | Confianza |
|---|---|---|---|
| Modulación del enlace descendente | FSK | AMSAT-UK; SatNOGS DB; PY4ZBZ | Alta: tres fuentes concordantes, una de ellas la organización que coordinó la telemetría |
| Tasa | 9600 bit/s | ídem | Alta |
| Trama y codificación de línea | AX.25 (HDLC), NRZI | AMSAT-UK; PY4ZBZ | Alta |
| Frecuencia | 437,568 MHz | AMSAT-UK; SatNOGS DB | Alta. eoPortal cita 437,575 MHz como asignación previa |
| Potencia | 1 W nominal; 0,25 W en modo baliza/CW | eoPortal | Media: no consta en qué modo se emite la telemetría |
| Desviación, filtrado, aleatorizador G3RUH a bordo | **No documentados** | — | PY4ZBZ decodifica con módem G3RUH: es una observación, no una especificación |
| Ganancia de antena, umbral del receptor | **No documentados** | — | — |
| Modulación del modelo de banda base | BPSK coherente (avanzado, GNU Radio); BPSK y FSK (básico) | código | Es una decisión del proyecto |
| Modulación de la captura IQ de referencia | BPSK con RRC, **sintética** | `captura/*.json` | No es una recepción |

El texto completo de la publicación de la misión (Kenyon, Bridges *et al.*, IAC 2011) no se pudo
consultar; queda como pendiente.

### Canal y comparabilidad

| ID | Pr. | Problema | Causa raíz | Archivo |
|---|---|---|---|---|
| C1 | C | El FEC se comparaba a igual SNR por muestra | A igual SNR/muestra el código r=1/2 recibe el doble de energía por bit de información (3 dB) | `simular_enlace_rf_bpsk_avanzado.py` |
| C2 | C | Cada configuración veía un ruido distinto | Un único generador avanzando por todas las corridas, una realización por punto | ídem |
| C3 | C | FEC y AX.25 solo sin desvanecimiento; NRZ con él | Matriz de configuraciones incompleta | ídem |
| C4 | C | «≈4 dB de ganancia» de un solo punto | Cociente de dos BER a una SNR, no un cruce a BER objetivo | ídem, informe, web |
| C5 | A | Rice con la mitad de potencia difusa (N2) | Escalado doble de la varianza; solo frecuencias positivas | `gen_rice_fading` |
| C6 | A | El ruido se normalizaba con la señal ya desvanecida | La SNR era la de la realización, no la del canal | `add_awgn` en el canal |
| C7 | A | BER > 0,5 (N3) | Costas sin resolución de ambigüedad | demoduladores |
| C8 | A | «Doppler orbital variable» de 150 Hz; residuales de 0,05–0,2 Hz | La misma constante hacía de dispersión del desvanecimiento y de Doppler orbital | constantes |
| C9 | A | Sin BER con intervalo, sin PER, sin FER | Solo recuento de errores de bit | `SimResult` |
| C10 | A | `ax25_frames_validos = 0` donde no hay trama (H12) | Entero por defecto en lugar de «no aplica» | `SimResult` |

### Telemetría

| ID | Pr. | Problema | Causa raíz | Archivo |
|---|---|---|---|---|
| T1 | A | PER del 64,2 % inflada (N4) | Diferencias de contador entre filas en orden arbitrario dentro del mismo segundo | informe §3.7 |
| T2 | A | Tramas repetidas tratadas como anomalía | Se agrupaba solo por contenido; el satélite repite balizas idénticas | regla `duplicate_frames` (se conserva, ahora explicada) |
| T3 | A | 508–528 mA y tensiones negativas sin explicación (H5) | Valor de la recta con cuenta 0 mostrado como medida | `/api/telemetry/campos`, panel |
| T4 | A | 9,75 V marcado como NORMAL (N5) | Límites inventados a partir de la calibración | `enlace_monitor.py` |

### Plataforma web

| ID | Pr. | Problema | Causa raíz | Archivo |
|---|---|---|---|---|
| W1 | C | «Ningún frame es baliza» (H2) | Texto fijo anterior al decodificador AMSAT | `Advanced.tsx` |
| W2 | C | Cifras de rotor antiguas (H3) | Números escritos en el componente, pese a un comentario que decía lo contrario | `Simulacion.tsx` |
| W3 | C | 1 bit de diferencia sin simular (H4) | `_estado_enlace/bits_rx_sim.bin` de una corrida del 26-sep viajaba en el despliegue y se leía sin saber de qué corrida era | `enlace_monitor.py`, `.vercelignore` |
| W4 | A | «Iniciar simulación» en un despliegue sin GNU Radio | No se declaraba la disponibilidad | ídem, `EnlaceRF.tsx` |
| W5 | A | Sin etiqueta de clase de dato (H7) | — | todas las páginas de simulación |
| W6 | M | *Status: ACTIVE* fijo (N6); unidades mezcladas (N7) | Literales | `Hero.tsx`, `Advanced.tsx` |

---

## 3. Cambios implementados

**Nuevos**

| Archivo | Qué hace |
|---|---|
| `parametros_enlace.py` | Fuente única de parámetros con procedencia, fuente e incertidumbre; curvas de BER y umbral teórico por esquema |
| `margen_paso_sgp4.py` | TLE → SGP4 → Doppler y derivada → residual → rotor → margen en el tiempo; percentiles, intervalos y sensibilidad |
| `estimar_snr_iq.py` | Estimador M2M4 de Es/N0 sobre IQ, contrastado con la SNR conocida |
| `telemetria_strand1/tools/analizar_recepcion.py` | Metadatos disponibles, coincidencias entre estaciones, ganancia por combinación, pérdida por secuencia (solo lectura, base local) |
| `generar_resumen_web.py` | Único camino de un número hasta la web, el README e `index.html` |
| `tests/test_presupuesto_enlace.py`, `test_modelo_avanzado.py`, `test_paso_sgp4.py`, `test_coherencia_resultados.py` | 119 pruebas nuevas (más 4 en `test_plataforma_monitor.py`) |

**Modificados**

| Archivo | Cambio |
|---|---|
| `calcular_link_budget.py` | Parámetros desde la fuente única; umbral calculado de la curva; margen FSK (documentada) y BPSK (comparativa); `eb_n0_requerida_db` en lugar de `snr_requerida_db`; procedencia en el JSON |
| `modelo_estacion_terrena.py` | Mismos parámetros que el link budget; añade la pérdida de polarización |
| `simular_enlace_rf_bpsk_avanzado.py` | Eje en Eb/N0 por bit de información; canal común con semillas explícitas; Rice normalizado; ruido referido a la potencia transmitida; Doppler residual con deriva; resolución de polaridad; BER, BER diferencial, PER y FER con IC de Wilson; ganancia por cruce a tasa objetivo; Viterbi y codificador vectorizados; metadatos de corrida |
| `simular_enlace_rf_fsk_bpsk.py` | Columna de Eb/N0; advertencias de lectura |
| `simular_enlace_ascendente.py` | Declarado como escenario hipotético |
| `comparar_con_cubesats_reales.py` | STRaND-1 con datos documentados y marca de verificación; se retiran juicios y porcentajes sin fuente |
| `generar_tablas_informe.py` | 20 tablas (antes 11); un marcador ausente es un error, no un aviso |
| `backend/app/services/enlace_monitor.py`, `routers/monitor.py` | Registro de corrida (`corrida.json`); una salida sin registro no se presenta como resultado; disponibilidad de la simulación; sin límites NORMAL/ALERTA inventados |
| `backend/app/services/strand_amsat.py`, `routers/telemetry.py` | Procedencia de cada conversión y estado de validación por campo (campos añadidos, contrato compatible) |
| `frontend/src/pages/Simulacion.tsx` | Sin cifras propias: todo desde el resumen generado, con etiqueta de tipo |
| `Advanced.tsx`, `EnlaceRF.tsx`, `Telemetry.tsx`, `Hero.tsx`, `lib/api.ts` | Recuento de balizas desde la API; rótulos de modelo e histórico; columna de validación; estado del transmisor |
| `.vercelignore` | No se sube el estado de corridas locales |
| `README.md`, `index.html`, `docs/*.md` | Modulación, resultados generados, limitaciones, referencias |

Se conservan la arquitectura, la navegación, la identidad visual y los contratos de la API (solo se
añaden campos). No se ha modificado ningún dato original ni la base de datos.

---

## 4. Pruebas ejecutadas

```bash
cd cubesat
../strand/bin/python -m pytest          # 153 pasan (eran 30), ~19 s
cd telemetria_strand1/frontend && npm run build    # tsc -b && vite build: sin errores
```

Comprobaciones manuales en local, con la base PostgreSQL local y `READ_ONLY=true`:

| Comprobación | Resultado |
|---|---|
| `GET /api/enlace/integrity` con el archivo heredado | `valido: null`, `procedencia: archivo_sin_registro` (antes: «discrepancia de 1 bit») |
| `POST /api/enlace/simulate` a 6 dB y nueva lectura | 47 bits erróneos de 18 776, BER 2,5·10⁻³, con SNR, semilla y fecha de la corrida |
| `GET /api/telemetry/campos` | 9 campos `canal_sin_medida`, 14 `pendiente_de_validacion`, 6 `sin_calibrar`, 2 `calibrado` |
| `GET /api/telemetry` | 32 754 balizas: la misma cifra que usa ahora *Advanced* |

**Limitaciones del entorno.** No se ha probado la interfaz en un navegador (solo compilación y
API). No se ha desplegado. `analizar_recepcion.py` se ejecutó contra la base local, no contra
Neon. El tiempo de la simulación avanzada es de unos 2,5 min en 8 núcleos.

---

## 5. Resultados regenerados

En `resultados_simulacion/`:

| Archivo | Origen |
|---|---|
| `link_budget_completo.json`, `link_budget_resultados.csv`, `link_budget_margen_enlace.png` | `calcular_link_budget.py` |
| `margen_paso_sgp4.json`, `margen_paso_sgp4_serie.csv`, `margen_paso_sgp4.png` | `margen_paso_sgp4.py` (nuevo) |
| `resultados_simulacion_avanzada.{csv,json}`, `umbrales_receptor_simulado.json`, `simulacion_avanzada_resultados.png` | `simular_enlace_rf_bpsk_avanzado.py` |
| `estimacion_snr_iq.{json,png}` | `estimar_snr_iq.py` (nuevo) |
| `analisis_recepcion_telemetria.json` | `tools/analizar_recepcion.py` (nuevo) |
| `resultados_ber_fsk_bpsk.csv`, `curva_ber_fsk_bpsk.png` | `simular_enlace_rf_fsk_bpsk.py` |
| `estacion_terrena_seguimiento.{json,png}`, `enlace_ascendente_resultados.{json,png}` | sus scripts |
| `comparacion_parametros_cubesats_reales.{csv,json}`, `cubesats_reales_referencia.{csv,json}` | `comparar_con_cubesats_reales.py` |

Derivados de los anteriores: las 20 tablas del informe, el bloque de resultados del README, los
datos enlazados de `index.html` y `telemetria_strand1/frontend/src/data/resumen_simulacion.json`.

**Resultados que cambiaron a peor, y por qué se conservan:**

| Resultado | Antes | Ahora | Motivo |
|---|---|---|---|
| Margen descendente a 5° | 7,1 dB | 3,7 dB (FSK); 7,5 dB (BPSK) | El anterior usaba el umbral de BPSK para un satélite FSK |
| Ganancia de codificación | «≈4 dB» | 1,3 dB a BER 10⁻³; 3,0 dB en FER 10 % | Comparación a igual Eb/N0 por bit de información |
| Robustez con desvanecimiento | «penalización de unos 3 dB» | El receptor BPSK pierde el enganche; FER del 17 % a 12 dB | Rice con su potencia difusa correcta y varios ensayos |
| Tolerancia al Doppler residual | décimas de Hz | 50 Hz sin pérdida; a 100 Hz empieza a fallar | Residuales del orden que produce el paso real |
| Pérdida de paquetes | 64,2 % | 36,8 % (cota inferior) | Método independiente del orden de las filas |

---

## 6. Matriz de trazabilidad

Requisito → módulo → prueba → resultado → estado. Todas las pruebas citadas pasan.

| Requisito | Módulo | Prueba | Resultado | Estado |
|---|---|---|---|---|
| Modulación real establecida y unificada | `parametros_enlace.py` | `test_la_modulacion_documentada_es_fsk_y_el_modelo_es_bpsk`, `test_el_informe_declara_la_modulacion_documentada` | Informe §1.3; esta auditoría §2 | Hecho; desviación y umbral del receptor real, pendientes |
| Ecuaciones del presupuesto con casos independientes | `geometria_orbital.py`, `calcular_link_budget.py` | `test_fspl_caso_de_referencia`, `test_caso_cenital_calculado_a_mano`, `test_densidad_de_ruido_a_290_k…` | `link_budget_completo.json` | Hecho |
| Unidades y conversiones | ídem | `test_conversion_dbm_vatios`, `test_temperatura_de_sistema_…` | — | Hecho |
| Relación P_rx, ruido, C/N0, Eb/N0, margen | `calcular_link_budget.py` | `test_relaciones_entre_potencia_ruido_cn0_ebn0_y_margen` | tabla `link_budget` | Hecho |
| Umbral por esquema, sin doble cuenta | `parametros_enlace.py`, `margen_paso_sgp4.py` | `test_umbrales_teoricos_a_ber_1e5`, `test_el_umbral_calibrado_no_lleva_reserva_de_implementacion` | tabla `margen_paso` | Hecho |
| Margen en el tiempo sobre SGP4, con estadísticas | `margen_paso_sgp4.py` | `test_estadisticas_del_margen`, `test_la_serie_de_ebn0_es_coherente_con_la_trayectoria` | `margen_paso_sgp4.json` | Hecho |
| Sensibilidad a potencia, temperatura, pérdidas y umbral | ídem | `test_sensibilidad_signos_fisicos` | tabla `sensibilidad` | Hecho; rangos de diseño, no medidos |
| Curva BER de referencia en AWGN | modelo avanzado | `test_ber_awgn_con_sincronizacion_ideal_coincide_con_la_teoria` | tabla `avanzado_principal` | Hecho |
| Reproducibilidad con semillas | ídem | `test_misma_semilla_mismo_resultado`, `test_metadatos_de_reproducibilidad_presentes` | metadatos del JSON | Hecho |
| Comparación pareada bajo el mismo canal | ídem | `test_dos_senales_ven_el_mismo_ruido_y_el_mismo_desvanecimiento`, `test_todas_las_configuraciones_comparten_bits_y_criterio` | — | Hecho |
| Normalización de potencia y K del canal Rice | `gen_rice_fading` | `test_rice_potencia_unitaria_y_factor_k` | — | Hecho; parámetros hipotéticos |
| Definición de SNR/Eb/N0 por esquema | `snr_muestra_desde_ebn0` | `test_snr_por_muestra_frente_a_ebn0`, `test_el_canal_impone_la_ebn0_pedida` | — | Hecho |
| Doppler coherente con SGP4, signo y derivada | `orbita_sgp4.py`, `margen_paso_sgp4.py` | `test_signo_del_doppler`, `test_la_velocidad_radial_es_la_derivada_de_la_distancia`, `test_residual_proporcional_al_error_de_tiempo` | tabla `doppler_paso` | Hecho |
| Doppler residual hasta el demodulador | `canal_enlace` | `test_doppler_constante_y_con_deriva`, `test_costas_y_gardner_recuperan…` | tabla `doppler_residual` | Hecho; residual constante por captura de 2 s |
| Estimación de SNR desde IQ | `estimar_snr_iq.py` | `test_m2m4_en_awgn`, `test_m2m4_devuelve_none_cuando_no_tiene_solucion` | tabla `estimador_snr` | Hecho sobre IQ sintético |
| BER, FER, PER y denominadores | modelo avanzado | `test_agregado_fer_solo_donde_hay_trama`, `test_metricas_del_modelo_avanzado_tienen_denominadores_coherentes` | tabla `ax25` | Hecho |
| CRC/FCS y contadores AX.25 | ídem | `test_fcs_es_crc16_x25`, `test_un_bit_erroneo_invalida_exactamente_una_trama`, `test_trama_no_recuperada_se_cuenta_como_descartada` | — | Hecho; sin búsqueda de banderas |
| Ceros y divisiones por cero | ídem | `test_tasa_con_denominador_cero_es_none_no_cero`, `test_cero_errores_tiene_cota_superior_no_nula` | «0 (< x)» y «N/A» en tablas | Hecho |
| Ganancia de codificación solo si es medible | `analizar` | `test_la_ganancia_de_codificacion_solo_se_informa_si_es_medible`, `test_el_cruce_de_umbral_no_interpola_sobre_un_cero` | tabla `ganancia_codificacion` | Hecho |
| Validación con telemetría real | `tools/analizar_recepcion.py` | `test_analisis_de_recepcion_es_internamente_coherente` | tablas `perdida_secuencia`, `diversidad` | Hecho; FER empírica no obtenible |
| Diversidad de estaciones | ídem | ídem | tabla `diversidad` | Hecho; observacional |
| Magnitudes de telemetría con procedencia | `strand_amsat.py`, `routers/telemetry.py` | `test_calibracion_cuenta_cero_es_la_ordenada_de_la_recta`, `test_bateria_en_cuenta_cero_se_marca_sin_medida` | columna *Validación* | Hecho; rangos físicos, pendientes |
| Sin valores imposibles sin aviso | varios | `test_link_budget_csv_y_json_coinciden_y_son_fisicamente_plausibles`, `test_ningun_parametro_se_marca_normal_sin_limites_documentados` | — | Hecho |
| Coherencia scripts ↔ archivos ↔ informe ↔ web | `generar_tablas_informe.py`, `generar_resumen_web.py` | `test_cada_tabla_del_informe_coincide_con_los_resultados` (×20), `test_el_resumen_publicado_es_el_que_dan_los_resultados_actuales`, `test_index_html_muestra_los_valores_vigentes`, `test_el_readme_publica_los_resultados_vigentes` | — | Hecho |
| Sin datos obsoletos como resultado actual | `enlace_monitor.py` | `test_salida_sin_registro_no_se_presenta_como_resultado`, `test_corrida_registrada_informa_snr_y_errores`, `test_el_estado_de_corridas_locales_no_se_despliega` | — | Hecho en local; sin desplegar |
| Web sin cifras escritas a mano | `Simulacion.tsx`, `Advanced.tsx` | `test_simulacion_tsx_toma_sus_cifras_del_resumen`, `test_advanced_tsx_no_afirma_que_no_hay_balizas` | — | Hecho en local; sin desplegar |
| Ruido de fase, no linealidad, desbalance I/Q | — | — | Informe §12.2 | Excluido: sin parámetros que lo justifiquen |
| Modelo ionosférico (Faraday, centelleo) | — | — | Informe §12.2 | Excluido; solo reserva fija de polarización |
| Adaptación de modulación y codificación | — | — | Informe §12.2 | No aplicable: baliza sin canal de retorno |

Estado de cada fenómeno del canal:

| Fenómeno | Estado |
|---|---|
| Geometría del paso, distancia, pérdida de espacio libre | Modelado (SGP4) |
| Doppler y su derivada | Modelado (SGP4) |
| Doppler residual tras la precompensación | Representado por una aproximación (desfase temporal del TLE; escenarios) |
| Ruido térmico del receptor | Modelado con parámetros supuestos |
| Seguimiento y pérdida de apuntamiento | Modelado; rotor y antena hipotéticos |
| Desvanecimiento Rice | Representado por una aproximación; no calibrado con datos |
| Polarización, rotación de Faraday, orientación de antenas | Reserva fija de 1 dB con ±2 dB en la sensibilidad; no modelado |
| Centelleo ionosférico | Excluido del alcance |
| Atenuación atmosférica y por lluvia | Reserva fija de 0,5 dB; la lluvia no es relevante a 437 MHz |
| Ruido de fase, no linealidad del amplificador, desbalance I/Q | Excluidos del alcance |
| Demodulador FSK real (discriminador de FM) | Pendiente de validación |

---

## 7. Pendientes

Requieren fuentes externas, datos reales o una decisión de la autora.

1. **Publicar los cambios.** Fusionar la rama, desplegar en Vercel y actualizar GitHub Pages.
   Hasta entonces la web pública sigue mostrando la versión anterior.
2. **Descripción del repositorio en GitHub.** Dice «análsis de telemetria». No está en ningún
   archivo: se cambia en *Settings → About* del repositorio.
3. **Publicación de la misión** (Kenyon, Bridges *et al.*, IAC-11-B4.6B.8): consultada después de
   esta auditoría. Confirma AX.25, 1 W nominal (0,25 W en baliza/CW) y las frecuencias previstas,
   pero **no especifica modulación, tasa ni desviación**: esas siguen dependiendo de AMSAT-UK y
   SatNOGS.
4. **Umbral de un receptor FSK real.** Simular un demodulador con discriminador de FM y
   aleatorizador G3RUH, o medirlo. Hoy es la mayor incertidumbre del margen.
5. **Captura IQ real de un SDR** de un paso de STRaND-1, con el manifiesto ya definido. Permitiría
   medir BER, SNR y Doppler residual, y calibrar el canal.
6. **TLE históricos** (Space-Track) para calcular la elevación en el instante de cada trama de
   2016–2023. Con el TLE de 2026 no es válido.
7. **Rangos de operación de las magnitudes de telemetría** (batería, corrientes, interruptores):
   sin ellos los 14 campos «pendiente de validar» no pueden clasificarse.
8. **Referencias 16 y 17 del informe:** no se localizaron; confirmar o retirar.
9. **Tabla de CubeSats de referencia:** verificar en fuente primaria las seis filas restantes.
10. **Rossi (2026).** No se dispone del documento ni se pudo identificar autoría, título y evento,
    de modo que no se cita. La distinción entre estimación (el estimador M2M4), predicción (el
    presupuesto sobre SGP4) y modelado (el canal) se aplica en el informe sin atribuirla.
11. **Enlace ascendente real** (VHF, 145,860 MHz según eoPortal): no caracterizado.
12. **Prueba de la interfaz en navegador** tras desplegar: estados de carga, error y ausencia de datos.
13. **Implementación autónoma de referencia** (`backend/` + `dashboard/`): no se ha tocado; conserva
    el comportamiento anterior del panel.

---

## 8. Conclusiones

**Demostrado por simulación** (modelo de banda base, bajo supuestos declarados):

- El modelo BPSK reproduce la curva teórica en AWGN con sincronización ideal y, con lazos reales y
  conformado RRC, desde 3 dB de Eb/N0.
- El conformado RRC reduce el ancho de banda ocupado de unos 66 kHz a unos 11 kHz.
- A igual Eb/N0 por bit de información, el código convolucional con Viterbi de decisión dura gana
  del orden de 1 dB en BER y 3 dB en el umbral de FER de tramas AX.25.
- Con el desvanecimiento del escenario hipotético, un receptor BPSK coherente sin codificación
  diferencial no es robusto.
- El presupuesto de enlace da margen positivo para FSK no coherente, con una dependencia fuerte de
  la potencia transmitida y del umbral del receptor.

**Observado en telemetría real:**

- 32 754 balizas decodificadas de 36 641 tramas; el contenido y la evolución de sus magnitudes.
- Los valores constantes de 9,75 V y de 508–528 mA son canales sin medida, no lecturas.
- 1 993 de 28 179 emisiones llegaron a dos o más estaciones; combinarlas aporta ×1,32 en las
  ventanas simultáneas.
- Dentro de las ráfagas recibidas falta el 36,8 % de los paquetes, bajo la hipótesis del contador.

**Lo que todavía no se puede afirmar:**

- La BER, la FER, la SNR o el margen del enlace real de STRaND-1.
- Que el enlace cierre con una estación concreta: la del modelo es hipotética.
- El umbral de un receptor FSK real ni la forma de onda exacta del modulador.
- Que la pérdida de paquetes observada se deba al canal y no a la estación o al demodulador.
- Que haya diversidad física entre estaciones.
