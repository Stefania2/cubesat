# HMTA — Módulo de supervisión de salud de STRaND-1

**Health Monitoring & Telemetry Analysis.** Documentación técnica: arquitectura, inventario
de variables, modelo de datos, modelos PID, instalación, pruebas y resultados sobre el archivo
real. El manual en lenguaje sencillo es [`HMTA_MANUAL_USUARIO.md`](HMTA_MANUAL_USUARIO.md).

> El HMTA es **solo de supervisión**. No tiene ninguna ruta, función ni botón que envíe órdenes al
> satélite, y no podría tenerlo: STRaND-1 está inactivo (SatNOGS marca su transmisor como
> «inactive») y lo que se supervisa es su archivo histórico.

---

## 1. Qué había antes y qué se reutiliza

El módulo se construyó sobre lo que el proyecto ya tenía, sin reemplazar ni duplicar nada:

| Pieza existente | Qué aporta al HMTA |
| --- | --- |
| `gemelo_digital/datos.py` | Única capa que habla con PostgreSQL. Se le añadieron dos cargadores pequeños: `cargar_estados()` (texto de los interruptores) y `cargar_secuencias()` (contador de secuencia de cada baliza). |
| `gemelo_digital/anomalias.py` | z robusto (mediana + MAD), regla de canal enrielado y agrupación de eventos. El HMTA los usa tal cual y solo traduce su salida a alertas. |
| `routers/gemelo.py` (`_campos`) | Caché de las 71 631 lecturas. El router del HMTA la reutiliza: abrir el HMTA después del gemelo no repite la descarga. |
| `services/strand_amsat.calibraciones()` | Rectas de calibración de AMSAT-UK; con ellas se detecta «canal sin medida» (cuenta ADC = 0) y «escala completa» (1023). |
| `parametros_enlace.py` | Potencia de transmisión documentada (eoPortal). |
| `resultados_simulacion/ber_strand1_sweep.csv`, `link_budget_completo.json` | BER de la cadena GNU Radio (SIMULADO) y margen del enlace (ESTIMADO). |
| `tools/analizar_recepcion.py` | Criterio de pérdida por contador de secuencia (ráfagas de 30 s, saltos ≤ 32, reinicios excluidos), replicado en `communication_monitor.perdida_por_secuencia`. |

Cambios en ficheros existentes, todos aditivos: dos funciones nuevas en `gemelo_digital/datos.py`,
una línea de import y otra de `include_router` en `backend/app/main.py`, la ruta `/salud` en
`App.tsx`, la entrada «Salud» en `Header.tsx`, los tipos y llamadas en `lib/api.ts`, y
`health_monitor/_datos/` en `.gitignore`.

## 2. Arquitectura

```
                       PostgreSQL (Neon o local)
                                │
                  gemelo_digital/datos.py  ◄── única capa con SQL
                                │
 health_monitor/                ▼
   telemetry_acquisition   ConjuntoTelemetria (tabla larga + tramas + secuencias
        │                  + observaciones), procedencia fijada al adquirir
        │                  · cargar_real() / desde_campos()   → REAL
        │                  · simular_escenario(nombre)        → SIMULADO
        ▼
   telemetry_validation    valida / motivo por lectura (no borra nada)
        ▼
   anomaly_detection       A límites · B tendencias · desviación (gemelo) ·
        │                  C modelo dinámico · D validación
        ▼
   subsystem_monitor ──► energy_monitor · thermal_monitor · communication_monitor
                         obc_monitor · adcs_monitor
        ▼
   health_assessment       informe: estado general, 6 secciones, vigencia,
        │                  procedencias, alertas, historial mensual
        ├── alerts         Alerta (7 preguntas) + RegistroEventos (SQLite)
        └── pid_reference  G1/G2 · P/PI/PID Ziegler–Nichols · ZOH + Tustin
                                │
telemetria_strand1/backend/app/routers/salud.py   →  /api/salud/*
telemetria_strand1/frontend/src/pages/Salud.tsx   →  /salud
```

El paquete vive en la raíz del repositorio, junto a `gemelo_digital/`, y el router lo alcanza
con el mismo `sys.path` que ya usa el gemelo. Solo depende de numpy y pandas, que la función
de Vercel ya instala; **no necesita scipy** (los tests sí lo usan para validar).

### API

| Ruta | Devuelve |
| --- | --- |
| `GET /api/salud/resumen?hasta=&ventana_dias=30` | Informe completo sobre el archivo real |
| `GET /api/salud/subsistema/{eps\|termico\|comunicaciones\|obc\|adcs\|anomalias}` | Una sección |
| `GET /api/salud/escenarios` · `GET /api/salud/escenario/{nombre}` | Escenarios de prueba (SIMULADO) |
| `GET /api/salud/pid?ts=0.01` | Modelos G1/G2, sintonía, métricas, polos, respuestas |
| `GET /api/salud/variables` | Inventario de variables (§3) |
| `GET /api/salud/historial` | Cobertura mensual de los canales de energía |
| `GET /api/salud/eventos?subsistema=&procedencia=&nivel=` | Alertas registradas |

Si la base no responde, `/resumen` devuelve **503** con un mensaje que dice que es un problema
de acceso a los datos, «no un estado del satélite»: un panel vacío por una caída de la base no
debe parecer un satélite sin telemetría.

## 3. Inventario de variables

`health_monitor/catalogo.py` es la fuente; `/api/salud/variables` lo sirve. Disponibilidad:
**emitida** (llega en las balizas), **definida no emitida** (la hoja de AMSAT-UK la define pero
la baliza nunca la transmite), **no existe** (ningún canal la mide), **derivada**.

| Sección | Variable | Unidad | Nodo/canal | Disponibilidad |
| --- | --- | --- | --- | --- |
| EPS | Voltaje batería 0 / 1 | V | 0x2C/0x03, 0x08 | emitida |
| EPS | Corriente de panel ±X, ±Y, ±Z (6) | mA | 0x2D/0x01, 04, 07, 0A, 0D, 1F | emitida |
| EPS | Corriente de batería | mA | 0x2C/0x01, 0x06 | definida no emitida |
| EPS | Corriente de buses (batería, 5 V, 3,3 V) | mA | 0x2D/0x11, 1A, 1B | definida no emitida |
| EPS | Potencia | W | — | derivada, **no calculable** (no hay V e I de la misma rama) |
| EPS | Nivel de carga | % | — | no existe |
| Térmico | Temperatura de baterías | °C | 0x2C/0x04, 0x09 | definida no emitida |
| Térmico | Temperatura de paneles (6) | °C | 0x2D/0x02 … 0x1E | definida no emitida |
| Térmico | Temperatura de la electrónica | °C | — | no existe |
| OBC | Campo de tiempo del OBC | s | 0x80/0x0C | emitida, **no se comporta como reloj** (§5.4) |
| OBC | Uso de CPU, memoria, reinicios, errores | — | — | no existe |
| ADCS | Magnetómetro X, Y, Z | cuenta (sin calibrar) | 0x89/0x03, 0x05 | emitida |
| ADCS | Interruptor de ruedas de reacción | estado | 0x66/0xA4 | emitida |
| ADCS | Orientación, velocidad de giro | °, °/s | — | no existe |
| Comunicaciones | Tramas, estado de decodificación, observaciones | — | tabla `frames`, `observations` | REAL |
| Comunicaciones | Pérdida por contador de secuencia | % | `seq_no` | ESTIMADO |
| Comunicaciones | Potencia de transmisión | dBm | eoPortal | DOCUMENTADO |
| Comunicaciones | BER de la cadena GNU Radio | — | `ber_strand1_sweep.csv` | SIMULADO |
| Comunicaciones | Margen del enlace | dB | `link_budget_completo.json` | ESTIMADO |
| Comunicaciones | RSSI, SNR por trama, FER del pase | — | — | no existe en SatNOGS |

**Ningún rango de operación está documentado** para STRaND-1 (`rango_documentado = None` en
todas las variables). Lo único documentado es el dominio del ADC (0–1023) y las rectas de
calibración, y eso lo aplica la validación.

## 4. Modelo de datos

### 4.1 Medición

Tabla larga, una fila por lectura (`ConjuntoTelemetria.mediciones`):

| Columna | Tipo | Significado |
| --- | --- | --- |
| `timestamp` | datetime UTC | instante de la baliza |
| `variable` | texto | nombre del campo (`battery_0_voltage`, …) |
| `valor` | float | valor numérico (NaN si es texto) |
| `texto` | texto | estado de un interruptor (`OFF`, `0x9A`, …) |
| `unidad` | texto | unidad declarada por el decodificador |
| `procedencia` | REAL · SIMULADO · ESTIMADO · DOCUMENTADO · NO_DISPONIBLE | fijada al adquirir |
| `fuente` | texto | de dónde sale |
| `estacion` | texto | estación receptora |

Acompañan: `tramas` (timestamp, estado, estación, observación), `secuencias` (timestamp,
estación, seq), `observaciones` (inicio, estado, elevación máxima) y `limites`
(`Limite(variable, mínimo, máximo, nivel, fuente)` — **no se puede crear un límite sin fuente**).

### 4.2 Indicador

`nombre`, `unidad`, `que_es`, `por_que_importa` (nivel básico); `valor`, `valor_fecha`,
`estado`, `estado_motivo`, `referencia`, `estadisticas`, `validacion`, `hallazgos`, `tendencia`,
`serie` (nivel técnico); `procedencia`, `fuente`, `notas`.

### 4.3 Alerta

Responde siempre a las siete preguntas — `Alerta.__post_init__` rechaza una alerta a la que le
falte alguna: qué ocurrió, componente, variable, valor registrado, valor de referencia (y de
dónde sale), por qué importa y qué información falta para investigarla. Además: nivel,
mecanismo, inicio, fin, procedencia y número de lecturas.

### 4.4 Registro de eventos

SQLite (biblioteca estándar), tabla `eventos`. Identificador determinista (hash de subsistema,
variable, mecanismo, inicio y procedencia): reevaluar el mismo periodo no duplica. Ruta en
`HMTA_DB_PATH`, por defecto `health_monitor/_datos/eventos_hmta.sqlite` (ignorado por git). En
Vercel el disco es de solo lectura: el registro cae a memoria y la API lo dice
(`persistente: false`). No toca la base PostgreSQL.

## 5. Reglas de supervisión

### 5.1 Clasificación

| Nivel | Cuándo |
| --- | --- |
| NORMAL | sin alertas; el campo `referencia` dice contra qué se comparó (casi siempre, el propio historial) |
| ADVERTENCIA | cualquier alerta de tendencia, desviación, validación, comunicaciones u OBC |
| CRÍTICO | **solo** un límite con `nivel = CRITICO` y fuente documentada |
| DESCONOCIDO | sin lecturas, o ninguna lectura válida |

Sobre los datos reales ninguna alerta puede llegar a CRÍTICO, porque no hay límites publicados.
Una desviación de 40 σ sigue siendo ADVERTENCIA. El estado general es el peor de los
subsistemas; DESCONOCIDO no cuenta como peor que NORMAL (falta de datos ≠ fallo).

### 5.2 Validación (`telemetry_validation`)

En orden: `no_finito`, `duplicado` (misma marca, valor y estación), `fuera_rango_fisico`
(voltaje < 0, temperatura < −273,15 °C, porcentaje fuera de 0–100), `canal_sin_medida` (valor =
ordenada de la recta, cuenta ADC 0), `escala_completa` (valor = recta en 1023), `canal_enrielado`
(regla del gemelo; solo voltajes y temperaturas, porque una corriente de panel en sombra puede
quedarse legítimamente en la misma cuenta). Las lecturas inválidas se conservan y se dibujan,
pero no entran en ningún cálculo.

### 5.3 Detección de anomalías

| Mecanismo | Criterio | Parámetro |
| --- | --- | --- |
| A. Límites | lecturas fuera de `[mínimo, máximo]` de un `Limite` con fuente | — |
| B. Tendencia | regresión lineal, \|t\| ≥ 5 y cambio ≥ 2 σ del residuo; solo V y °C | ≥ 20 lecturas, ≥ 1 día, ≥ 3 pases |
| Desviación | z robusto del gemelo (ventana de 51 lecturas, aviso \|z\| ≥ 3,5) | ≥ 3 lecturas seguidas o \|z\| ≥ 6; episodios a menos de 1 día se agrupan |
| C. Modelo | RMS del residuo respuesta medida − modelo, normalizado al valor final | tolerancia 0,05 |
| D. Validación | `canal_sin_medida`, `escala_completa`, `canal_enrielado`, `fuera_rango_fisico` | — |
| Comunicaciones | pérdida o error de la mitad reciente frente a todo lo anterior | +15 y +10 puntos |
| OBC | vuelta atrás de un contador validado como reloj | ritmo 0,9–1,1 s/s en ≥ 70 % de parejas |

Los umbrales de persistencia, de tendencia y de comunicaciones son **criterios de este módulo**,
no requisitos de la misión, y así lo dice cada alerta en su campo `referencia`. Dos se
ajustaron con evidencia: sin la exigencia de 3 lecturas, el escenario nominal daba 10 alertas
de ruido (lecturas sueltas con \|z\| ≈ 3,6); sin el agrupamiento por episodios, la fase
intermitente del ADC daba 201 alertas en lugar de 47; y sin el mínimo de 1 día y 3 pases, una
ráfaga de 2019 producía una «tendencia» de +89 V/día.

### 5.4 El campo de tiempo del OBC no es un reloj

La hoja de AMSAT-UK describe 0x80/0x0C como «4B UNIX TIME». En el archivo vale 2 en la mayoría
de las lecturas y, entre balizas separadas menos de 5 minutos, su ritmo mediano es 0 s/s. El
monitor lo comprueba con los datos antes de usarlo (`obc_monitor.comportamiento_reloj`) y, como
no pasa, **no cuenta reinicios ni afirma que el computador funcione**. Con un contador que sí
avanza (escenario `reinicios_obc`), el mismo código detecta las tres vueltas a cero inyectadas.

### 5.5 Vigencia

El informe separa el estado del periodo evaluado de la vigencia de los datos. Con la última
telemetría decodificada del 2023-01-29, el campo `vigencia` dice que el estado actual de
STRaND-1 es DESCONOCIDO, sea cual sea el estado del periodo.

## 6. Modelos PID

### 6.1 Qué son y qué no

G1(s) = 8 / (s + 2)³ y G2(s) = 4 / [s (s² + 13,5 s + 38,048)] son los modelos del trabajo de
Teoría de Control. **No representan ningún subsistema de STRaND-1**, no envían órdenes y no
diagnostican fallos. En el HMTA sirven de referencia para el mecanismo C: comparar una
respuesta medida con la esperada. Sus resultados se etiquetan ESTIMADO.

### 6.2 Sintonía

Método de la ganancia última de Ziegler–Nichols (el de la curva de reacción no vale para G2,
que tiene integrador). Ku y Pu se calculan sobre la respuesta en frecuencia y coinciden con
Routh:

| Planta | ωu (rad/s) | Ku | Pu (s) |
| --- | ---: | ---: | ---: |
| G1 | √12 = 3,4641 | 8 | 1,8138 |
| G2 | √38,048 = 6,1683 | 128,412 | 1,0186 |

| | Kp | Ti | Td |
| --- | --- | --- | --- |
| P | 0,5 Ku | — | — |
| PI | 0,45 Ku | Pu / 1,2 | — |
| PID | 0,6 Ku | Pu / 2 | Pu / 8 |

> **Pendiente de confirmar.** El repositorio no contenía la tabla de parámetros del trabajo
> académico, así que se recalcularon con el método de la ganancia última. Si el trabajo usó
> otro método o redondeos, basta con cambiar `pid_reference.sintonia()`; los tests de MATLAB y
> scipy seguirán validando la implementación.

### 6.3 Implementación digital

Planta discretizada con retenedor de orden cero (exacta en los instantes de muestreo);
controlador por Tustin; derivativo filtrado con polo en N/Td, N = 10. Ts = 0,01 s por defecto
(≈ 100 muestras por Pu de G2); la interfaz permite 0,001–0,25 s. Estabilidad por los polos del
lazo cerrado discreto (\|z\| < 1) y continuo (Re s < 0); márgenes de ganancia y fase del lazo
abierto continuo.

### 6.4 Resultados (Ts = 0,01 s, escalón unitario, banda del 2 %)

| Planta | Control | Kp | Ti (s) | Td (s) | Sobrepaso | T. subida | T. asentamiento | Error est. | máx \|z\| | MG / MF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| G1 | P | 4 | — | — | 55,2 % | 0,48 s | 9,53 s | 0,2 | 0,99602 | 6,02 dB / 27,1° |
| G1 | PI | 3,6 | 1,5115 | — | 57,2 % | 0,53 s | 16,58 s | 0 | 0,99775 | 3,65 dB / 14,8° |
| G1 | PID | 4,8 | 0,9069 | 0,2267 | 43,9 % | 0,41 s | 4,63 s | 0 | 0,99215 | 19,1 dB / 29,4° |
| G2 | P | 64,206 | — | — | 59,7 % | 0,28 s | 5,78 s | 0 | 0,99358 | 6,02 dB / 19,4° |
| G2 | PI | 57,785 | 0,8489 | — | 100,5 % | 0,25 s | > 20 s (MATLAB: 26,8 s) | 0 | 0,99853 | 2,23 dB / 5,2° |
| G2 | PID | 77,047 | 0,5093 | 0,1273 | 64,7 % | 0,20 s | 3,31 s | 0 | 0,98722 | 21,4 dB / 24,0° |

Los seis lazos son estables a Ts = 0,01 s. El error de 0,2 de G1 con P es el esperado para una
planta tipo 0 (1 / (1 + Kp·G(0)) = 1/5); G2 lo anula con P por su integrador. El PI de G2 queda
con 5° de margen de fase: es lo que da la tabla de Ziegler–Nichols sobre una planta con
integrador, y se muestra tal cual. Con Ts = 0,25 s el PID de G2 se vuelve inestable
(\|z\|máx > 1) y la interfaz lo indica en lugar de dibujar métricas.

### 6.5 Validación

- **scipy.signal**: la ZOH coincide con `cont2discrete` hasta 1e-15 y Tustin con `bilinear`
  hasta 1e-13; la respuesta muestreada sigue a la continua a menos de 0,03 en G1.
- **MATLAB R2026a** (Control System Toolbox): `health_monitor/validacion_matlab/validar_pid_zn.m`
  recalcula todo de forma independiente (`margin`, `pid`, `c2d`, `feedback`, `stepinfo`) y
  escribe `resultados_simulacion/hmta_pid_matlab.json`. Ku idéntico, sobrepasos y tiempos
  iguales al centésimo, respuestas a menos de 1e-5, mismos polos. `test_coincide_con_matlab` lo
  comprueba en cada ejecución.

```bash
matlab -batch "run('health_monitor/validacion_matlab/validar_pid_zn.m')"
```

## 7. Resultados sobre el archivo real

Evaluación de los periodos que ofrece la interfaz (datos de Neon, 71 631 lecturas):

| Periodo | Estado general | Lo que encuentra |
| --- | --- | --- |
| Último registro (2022-12-30 → 2023-01-29) | ADVERTENCIA | Las 40 lecturas de batería son «canal sin medida» → voltaje DESCONOCIDO y alerta de validación; 945 tramas, 633 balizas, enlace Activo; OBC y ADCS DESCONOCIDO; térmico NO DISPONIBLE |
| Fase sana (2019-11 → 2020-10) | ADVERTENCIA | Voltajes y corrientes válidos; algunas desviaciones puntuales del historial; escala completa en −X y −Z |
| Fallo del ADC (2020-11 → 2021-02) | ADVERTENCIA | 47 alertas: episodios de desviación y canal sin medida en las 8 variables de energía |

El historial mensual (`/api/salud/historial`) reproduce sin intervención la cronología ya
documentada del fallo: 100 % de lecturas válidas hasta 2020-10, 98,5–99,8 % en 2020-11 a
2021-01, y 0 % desde 2021-02.

## 8. Instalación y ejecución

No hay dependencias nuevas.

```bash
# Backend + frontend de la plataforma (incluye /salud)
cd telemetria_strand1 && ./arrancar.sh          # panel en :5173, API en :8000/docs

# El módulo, desde Python
../strand/bin/python -c "
from health_monitor import health_assessment as ha, telemetry_acquisition as ta
r = ha.evaluar(ta.simular_escenario('caida_voltaje'))
print(r['estado_general'], [a.que_ocurrio for a in r['_alertas']])"

# Pruebas
../strand/bin/python -m pytest tests/test_health_monitor.py     # 46 pruebas
```

`HMTA_DB_PATH` cambia la ruta del registro de eventos (`:memory:` para no persistir).

La primera petición a `/api/salud/resumen` descarga las lecturas y las tablas de recepción;
contra Neon eso tardó entre 1 y 4 minutos en las pruebas de esta sesión (la descarga completa
llegó a cortarse una vez). Después todo queda en caché del proceso y cada evaluación tarda
≈ 1 s. Si antes se abrió el gemelo digital, las lecturas ya están en caché.

## 9. Pruebas

`tests/test_health_monitor.py`, 46 pruebas, sin base de datos:

| Grupo | Qué comprueba |
| --- | --- |
| PID (9) | Ku/ωu = Routh; tabla de Ziegler–Nichols; filtro derivativo; ZOH y Tustin = scipy; lazo muestreado ≈ continuo; seis lazos estables; errores estacionarios teóricos; inestabilidad con Ts lento; coincidencia con MATLAB |
| Escenarios (20) | Para los 9 escenarios: el nominal no da alertas; cada uno dispara su alerta (subsistema, variable, mecanismo y nivel esperados) con las 7 preguntas respondidas; ninguno contamina otros subsistemas; CRÍTICO solo con límite documentado; los 3 reinicios inyectados; los 4 tipos de dato inconsistente; sin telemetría = DESCONOCIDO, no fallo; **nada simulado sale marcado REAL**; historial persistente sin duplicados; caída a memoria; informes serializables |
| Fuente real (9) | Canal muerto ≠ batería sana; reloj que no avanza no cuenta reinicios; sin temperatura ni actitud; vigencia; reglas de validación; límites y alertas exigen fuente; pérdida por secuencia |
| API (4) | `/resumen`, `/subsistema`, 404 y 422; escenarios y eventos marcados SIMULADO; `/pid`, `/variables`, `/historial`; base caída = 503 |

| Escenario | Alertas obtenidas |
| --- | --- |
| nominal | ninguna |
| caida_voltaje | tendencia + desviación en `battery_0_voltage` |
| aumento_temperatura | límite CRÍTICO (de prueba) + tendencia en `battery_temperature` |
| perdida_paquetes | pérdida 34,9 % frente a 1,8 % de referencia |
| errores_comunicacion | tramas con error 21,4 % frente a 0,3 % (y la pérdida que arrastra) |
| reinicios_obc | 3 vueltas atrás del reloj |
| datos_inconsistentes | canal sin medida (900 lecturas) + escala completa (60) |
| sin_telemetria | ninguna; todo DESCONOCIDO; enlace «Sin información suficiente» |
| respuesta_dinamica_anormal | residuo RMS 0,101 > 0,05 frente al modelo G1-PID |

Suite completa: `../strand/bin/python -m pytest` → 224 pruebas.

## 10. Limitaciones

- Ningún límite de operación documentado: CRÍTICO no puede dispararse con datos reales.
- Térmico y orientación vacíos sobre datos reales: el satélite no envía esos datos.
- La pérdida por secuencia es una cota inferior (no ve lo perdido antes de la primera trama ni
  después de la última de cada ráfaga).
- Los magnetómetros son cuentas sin calibrar; `magnetometer_y` toma valores de 10⁹ que no se
  pueden interpretar sin documentación.
- El registro de eventos es local; en Vercel vive en memoria.
- Los parámetros PID se recalcularon (§6.2); falta contrastarlos con la tabla del trabajo
  académico.
