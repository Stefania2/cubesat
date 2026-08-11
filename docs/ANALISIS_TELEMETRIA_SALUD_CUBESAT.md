# De la señal RF al estado del CubeSat: análisis de la telemetría de STRaND-1

**Proyecto aplicado de Ingeniería Electrónica — UNAD, 2026**

Este documento desarrolla la parte que la literatura consultada sobre subsistemas de
comunicaciones de CubeSats deja sin cubrir: **qué ocurre entre el bit demodulado y la
conclusión sobre la salud del satélite**. Los trabajos disponibles describen antenas,
transceptores y arquitectura, y validan en cámara anecoica con estación propia; aquí se
recorre la cadena completa sobre observaciones reales de la red SatNOGS.

```
Señal RF  →  Demodulación  →  Bits  →  Trama  →  Paquete  →  Variable  →  Estado del CubeSat
   §1            §2           §3       §4        §5          §6            §7
```

Todas las cifras proceden de datos procesados en este proyecto: 36 641 frames descargados de
3049 observaciones de SatNOGS —Network para 2022-2023 y el archivo histórico de SatNOGS DB
para 2016-2022, con la ventana de la transición descargada día a día—, de los que 32 754 son
balizas válidas de STRaND-1.

---

## 1. Modulación digital: BPSK frente a FSK

STRaND-1 emite en 437,568 MHz con FSK a 9600 bps según el registro de transmisores de
SatNOGS. El proyecto simula ambos esquemas para cuantificar la diferencia sobre el mismo
flujo de bits reales.

### 1.1 Resultados de BER en canal AWGN

| SNR (dB) | BER BPSK | BER FSK |
|---:|---:|---:|
| −2 | 8,52 · 10⁻⁴ | 1,08 · 10⁻¹ |
| 0 | 5,33 · 10⁻⁵ | 5,33 · 10⁻² |
| 2 | 0 | 1,91 · 10⁻² |
| 4 | 0 | 3,89 · 10⁻³ |
| 6 | 0 | 4,79 · 10⁻⁴ |
| 8 | 0 | 0 |

BPSK alcanza BER nula a partir de 2 dB de SNR por muestra, mientras que FSK necesita 8 dB:
**una ventaja de 6 dB**. A 0 dB la diferencia es de tres órdenes de magnitud. El resultado es
el esperado teóricamente —BPSK es antipodal, FSK ortogonal, y la separación asintótica es de
3 dB para detección coherente— y aquí se amplía porque el receptor FSK implementado es un
detector de energía no coherente, que paga una penalización adicional.

### 1.2 Contrapartida en ancho de banda

| Esquema | Ancho de banda ocupado al 99 % |
|---|---:|
| BPSK, pulso rectangular | 27,0 kHz |
| FSK, Δf·T = 0,5 | 11,8 kHz |
| BPSK con conformado RRC (α = 0,35) | 11,2 kHz |

FSK ocupa menos de la mitad que BPSK sin conformado, y es la razón por la que un CubeSat
puede preferirlo pese a su peor BER: la canalización UHF de radioaficionado es de 25 kHz.
El conformado de pulso resuelve el dilema — BPSK con RRC baja de 66,1 kHz a 11,2 kHz en el
modelo avanzado, igualando a FSK en ocupación espectral y conservando su ventaja de 6 dB.

**Conclusión de diseño:** para un CubeSat nuevo, BPSK con conformado RRC domina a FSK en
ambos ejes. FSK sigue justificándose por simplicidad de implementación en el transceptor,
que es probablemente el criterio que pesó en STRaND-1.

---

## 2. Procesamiento digital de señales

### 2.1 Cadena implementada

```
bits → codificación convolucional (r=1/2, K=7) → mapeo BPSK → sobremuestreo (8 muestras/símbolo)
     → filtro RRC transmisor → canal (AWGN + Rice + Doppler residual)
     → filtro RRC receptor (adaptado) → muestreo en el instante de símbolo
     → decisión → decodificación Viterbi → verificación FCS → bytes
```

### 2.2 Filtrado adaptado y muestreo

El filtro adaptado en recepción es el mismo RRC del transmisor: la cascada de ambos da un
coseno realzado completo, que cumple el criterio de Nyquist de interferencia entre símbolos
nula en los instantes de muestreo.

Aquí está la trampa práctica que este proyecto documenta: **hay que muestrear en el instante
del símbolo, no promediar la ventana**. Promediar la salida de un coseno realzado mezcla el
pico con las colas de los símbolos vecinos y fija la BER en torno a 0,15 independientemente
de la SNR. Es un error silencioso: la simulación corre, produce curvas y son falsas.

Igual de importante: sobremuestrear repitiendo la muestra (NRZ rectangular) y sobremuestrear
insertando ceros **no son intercambiables**. La inserción de ceros solo es correcta si detrás
hay un filtro conformador; sin él es un tren de impulsos que tira 9 dB.

### 2.3 Codificación de canal

| Condición | BER a −4 dB de SNR |
|---|---:|
| Sin FEC | 1,04 · 10⁻¹ |
| Con codificación convolucional + Viterbi | 0 |

La ganancia de codificación es de aproximadamente 4 dB en la región de BER 10⁻³. Por debajo
de −8 dB aparece el umbral característico del decodificador Viterbi: cuando la tasa de error
de entrada supera su capacidad de corrección, el decodificador empeora el resultado en lugar
de mejorarlo.

---

## 3. Sincronización

Es el eslabón más delicado de la cadena, y conviene decirlo con precisión porque condiciona
todo lo demás. El modelo básico asume sincronización ideal de portadora y de temporización de
símbolo; el modelo avanzado la hace real con dos lazos que no conocen la secuencia transmitida:
un lazo de Costas de segundo orden (80 Hz de ancho de bucle) para la portadora y una
recuperación de temporización de Gardner para el símbolo, evaluados frente a un desfase
fraccional reproducible de 0,35 muestras (sección 5.4 del informe técnico). El costo de quitar
la sincronización ideal es un umbral operativo alrededor de −6 dB: por debajo, los lazos
pierden el enganche por deslizamientos de ciclo y la BER satura; por encima, la BPSK con RRC
mantiene la BER del modelo ideal y recupera la portadora.

La consecuencia se cuantifica en el modelo avanzado mediante el error residual de Doppler,
que es lo que quedaría tras la precompensación que hace la estación terrena a partir del TLE:

| Error residual de Doppler | Efecto sobre la BER |
|---|---|
| 0,0 Hz | canal intacto, BER limitada solo por el ruido |
| 0,05 – 0,1 Hz | degradación apreciable en la región de baja SNR |
| 0,2 Hz | con el lazo de Costas se recupera; en el modelo de sincronización ideal producía un suelo irreducible de BER |

Una tolerancia de décimas de hercio sobre una portadora de 437 MHz es exigente: equivale a
una precisión relativa de 5 · 10⁻¹⁰. El lazo de Costas implementado (80 Hz) la cumple con
margen, y esa fue la motivación cuantitativa para dejar de asumir portadora ideal. La
recuperación de reloj con Gardner también está implementada; su límite operativo (y no la
deriva de portadora) es hoy el umbral de sincronización del receptor.

---

## 4. De los bits a la trama: estructura del paquete

Aquí empieza lo que la literatura consultada omite. La estructura de la baliza de STRaND-1
está publicada por AMSAT-UK (2013) y es:

```
C0 80 | SEQ (1B) | LENGTH (1B) | ID (1B) | I2C NODE (1B) | CHANNEL (1B) | DATA_SIZE (1B) | DATA (DATA_SIZE bytes)
```

| Campo | Tamaño | Función |
|---|---|---|
| Flag HDLC | 2 B | `C0 80`. Delimita el inicio y permite sincronizar a nivel de trama |
| SEQ | 1 B | Número de secuencia, 0–255 con envolvente. Permite detectar pérdidas |
| LENGTH | 1 B | Bytes que siguen, contando desde ID |
| ID | 1 B | `0x01` baliza de módem, `0x02` baliza de OBC |
| I2C NODE | 1 B | Subsistema de origen dentro del bus I2C del satélite |
| CHANNEL | 1 B | Canal concreto dentro de ese subsistema |
| DATA_SIZE | 1 B | Longitud del dato que sigue: 2, 4 u 8 bytes |
| DATA | variable | Cuenta ADC o valor crudo, little endian salvo la placa de interruptores |

En el enlace real el paquete viaja además entre flags de TNC (`C0 00 … C0`) y con **escape
KISS**: un `0xC0` dentro de los datos se transmite como `0xDB 0xDC`. Los archivos de
demoddata de SatNOGS llegan ya sin esa envoltura, pero el decodificador implementado
deshace el escape por si acaso.

### 4.1 Sobre el CRC

La especificación indica un CRC-ITT al final del paquete. Se probaron CRC-16/X-25 y
CRC-16/CCITT-FALSE sobre tres rangos de bytes distintos y en ambos endianness, y **ninguna
combinación valida las tramas recibidas**. La conclusión honesta es que la verificación de
integridad no pudo confirmarse con estos datos: o el CRC cubre un rango no documentado, o los
archivos de demoddata llegan sin él. Se reporta como limitación, no se omite.

### 4.2 Sincronización de trama

El flag `C0 80` es el mecanismo de sincronización de trama. Para descartar que las tramas no
reconocidas fueran balizas mal alineadas se buscó el patrón en los **ocho desplazamientos de
bit** posibles: aparece en 9 de las tramas no reconocidas, cuando el azar predice unas 6 para un patrón de
16 bits en ese volumen. No hay balizas ocultas por desalineamiento.

---

## 5. Del paquete a la variable: nodos, canales y calibración

Cada baliza transporta **una** medida, identificada por el par (nodo I2C, canal). Distribución
real sobre las 32 754 balizas:

| Nodo | Subsistema | Balizas | % |
|---:|---|---:|---:|
| `0x66` | Placa de interruptores | 9594 | 29,3 % |
| `0x2D` | Paneles solares | 9575 | 29,2 % |
| `0x80` | OBC | 8402 | 25,7 % |
| `0x2C` | EPS (baterías) | 5353 | 16,3 % |
| `0x89` | Magnetómetros | 3017 | 9,2 % |
| `0x89` | Magnetómetros | 791 | 9,9 % |

La conversión de cuenta ADC a magnitud física usa las rectas de calibración publicadas:

| Magnitud | Ecuación | Unidad |
|---|---|---|
| Voltaje de batería 0 | −0,00945 × ADC + 9,7488 | V |
| Corriente de batería 0 | −3,4969 × ADC + 3185,1551 | mA |
| Temperatura de batería 0 | −0,163 × ADC + 111,187 | °C |
| Temperatura de panel (todos) | −0,163 × ADC + 110,338 | °C |
| Corriente de interruptor | m × valor + c, con m,c por interruptor | mA |

Los magnetómetros son la excepción: la especificación define «4 B por eje, entero con signo,
little endian» pero **no publica constante de escala**, de modo que se reportan en cuentas y
no en µT. Escalarlos sin esa constante sería inventar la unidad.

### 5.1 El error de usar el decodificador oficial

`satnogs-decoders` reconoce la estructura pero lee **un solo byte** por canal, donde el
formato define un dato precedido de su tamaño. Devuelve por tanto el campo `DATA_SIZE` como
si fuera la medida:

```
C0 80 02 06 02 2C 03 02 00 00
                     ^^ ^^^^^
                     |  dato: cuenta ADC = 0
                     DATA_SIZE = 2

  decodificador oficial → battery_0_voltage_v = 2
  especificación AMSAT  → −0,00945 × 0 + 9,7488 = 9,75 V
```

El efecto es engañoso: todas las magnitudes aparecen constantes, porque lo constante es el
tamaño del campo. Una lectura apresurada concluiría que el satélite emite con la carga útil
vacía. **La herramienta de referencia puede estar equivocada, y la única defensa es
contrastarla contra la especificación primaria.**

---

## 6. De la variable al estado: monitoreo de salud

### 6.1 Indicadores de salud obtenidos

| Indicador | Valor observado | Lectura |
|---|---|---|
| Reloj UNIX del OBC | 2 – 3043 s, decreciente con los años | El ordenador se reinicia continuamente y cada vez antes |
| Cuentas ADC del EPS y paneles | válidas hasta 2021-01, cero desde 2021-02 | Los convertidores dejaron de entregar lectura |
| Voltaje de batería | 6,31 – 8,94 V hasta 2020; 9,75 V fijo después | Medida real primero, artefacto de calibración después |
| Estado de los diez interruptores | `OFF` en todos | Cargas útiles y subsistemas apagados |
| Magnetómetros, eje X | σ = 211 487 cuentas | Sensor operativo, con variación coherente |
| Magnetómetros, eje Y | σ = 147 043 cuentas | Sensor operativo |
| Magnetómetros, eje Z | σ = 164 900 cuentas | Sensor operativo |

Las σ de los magnetómetros excluyen las lecturas cuyo último byte llega alterado
y que producen valores tres órdenes de magnitud fuera del resto. Sin excluirlas, la σ del eje Y
sale 878 veces mayor que la de los otros dos ejes, lo que basta para identificarlas.

### 6.2 Distinguir lo normal de lo anómalo

El criterio que sostiene este análisis es que **una variable que no varía no está midiendo**.
Un voltaje de batería idéntico en 578 balizas repartidas en dos meses no es una batería
estable: es un canal muerto. La distinción se hace sobre tres hechos objetivos, sin necesidad
de conocer los límites operativos del fabricante:

1. **Dispersión nula frente a dispersión no nula.** Los magnetómetros tienen desviación
   estándar de cientos de miles de cuentas; los ADC del EPS, cero.
2. **Valor en el extremo de la escala.** Una cuenta ADC de 0 produce, por la recta de
   calibración, el máximo del rango (9,75 V). Un valor pegado al extremo es sospechoso de
   saturación o de ausencia de lectura, no de medida real.
3. **Coherencia física.** Los magnetómetros dan valores con signo y rango simétrico, como
   corresponde a un campo magnético medido en órbita.

### 6.3 Análisis temporal: degradación documentada

| Periodo | Máximo del reloj OBC |
|---|---:|
| 2016-11 | 1139 s |
| 2017-11 | 1815 s |
| 2018-11 | 831 s |
| 2019-11 | **3043 s** |
| 2020-11 | 586 s |
| 2021-11 | 856 s |
| 2022-07 | 866 s |
| 2022-08 | 279 s |
| 2022-10 | 167 s |
| 2022-11 y 12 | 177 s |
| 2023-01 | **2 s** (constante) |

El ordenador sostenía casi cincuenta minutos entre reinicios en 2019 y termina reiniciándose
cada dos segundos en enero de 2023. **El intervalo entre reinicios se acorta a lo largo de la
misión**, lo que indica degradación progresiva y no un fallo estático. La lectura de 866 s de
julio de 2022 la recibieron dos estaciones independientes en el mismo segundo con idéntico
hexadecimal, de modo que no es un artefacto de recepción.

### 6.4 Fechado del fallo del subsistema de energía

El archivo histórico permite distinguir un canal que nunca midió de uno que dejó de medir:

| Fase | Periodo | Lecturas ADC | Con cuenta 0 |
|---|---|---:|---:|
| Instrumentación sana | 2016-11 a 2020-10 | 753 | **0,0 %** |
| Fallo intermitente | 2020-11 a 2021-01 | 5674 | **1,8 %** |
| Fallo permanente | 2021-02 a 2023-01 | 8501 | **100,0 %** |

Ni una sola cuenta a cero en los primeros cuatro años; el 100 % en los veinticuatro meses
finales. Tres fechas comprobables: la primera lectura a cero es del **27 de noviembre de 2020**,
la última válida del **31 de enero de 2021 a las 23:57:52 UTC**, y desde el **24 de febrero de
2021** ya no hay ninguna válida. El fallo definitivo cae entre el 1 y el 24 de febrero de 2021.
Los ocho canales se ven afectados en proporción semejante durante la fase intermitente
—entre 0,9 % y 2,7 %—, lo que apunta a una causa común aguas arriba y no a sensores
degradándose por separado.

El dato más concluyente es la ventana temporal: las 32 754 balizas se extienden del
**30 de noviembre de 2016 al 29 de enero de 2023**, pese a que el conjunto de frames abarca
hasta julio de 2026. Después de esa fecha no hay ni una sola baliza reconocible en 3049
observaciones. El satélite dejó de emitir telemetría interpretable, lo que es coherente con
que SatNOGS marque su transmisor como `inactive`.

**Diagnóstico:** STRaND-1 pasó por una fase de fallo progresivo del ordenador de a bordo
—reinicios cada vez más frecuentes— con el subsistema de energía sin instrumentación válida y
todas las cargas apagadas, hasta el cese de emisiones. El único subsistema que reportaba
datos coherentes hasta el final era el magnetómetro.

---

## 7. Indicadores de desempeño del enlace (KPI)

| Indicador | Valor medido | Fuente |
|---|---|---|
| Integridad de la telemetría | 89,4 % (32 754 balizas de 36 641 frames) | Datos reales |
| Balizas por pase | media 14,7 · mediana 6 · máx 411 | Datos reales |
| Tiempo entre paquetes | mediana 2,0 s · p90 17,0 s | Datos reales |
| Continuidad de secuencia | 27,4 % de transiciones consecutivas | Datos reales |
| Pérdida de paquetes en el pase | 72,6 % de las transiciones con hueco | Datos reales |
| Estaciones que recibieron balizas | 114 | Datos reales |
| Observaciones con balizas | 775 de 3049 (25,4 %) | Datos reales |
| Packet Error Rate | 64,2 % · 79,1 % en horizonte, 52,1 % en cenit | Datos reales |
| BER (BPSK) | 0 para SNR ≥ 2 dB | Simulación |
| BER (FSK) | 0 para SNR ≥ 8 dB | Simulación |
| Margen de enlace descendente | 7,1 dB a 5° · 18,0 dB en cenit | Modelo de link budget |
| Margen de enlace ascendente | 23,3 dB a 5° · 34,2 dB en cenit | Modelo de link budget |
| C/N₀ en un paso completo | 60,9 – 72,6 dB-Hz | Modelo de estación terrena |

### 7.1 Indicadores que no pudieron medirse

La honestidad sobre lo que falta es parte del resultado:

- **RSSI y SNR del enlace real.** La API de SatNOGS no entrega la potencia recibida por
  frame. Los valores de SNR de este trabajo son de simulación, no medidos.
- **BER real del enlace.** Requeriría conocer los bits transmitidos, imposible sin
  cooperación del operador.
- **Latencia.** No hay marca de tiempo de generación a bordo utilizable: el reloj del OBC
  está averiado, que es precisamente uno de los hallazgos.
- **Packet Error Rate exacta.** El 72,6 % de huecos de secuencia mide pérdidas *observadas*,
  que mezclan paquetes perdidos en el enlace con paquetes que el satélite no llegó a emitir.
  Es una cota superior, no una PER limpia.

---

## 8. La red SatNOGS como fuente de observaciones

Frente a la validación en cámara anecoica con estación propia, este trabajo usa una red
abierta de estaciones voluntarias. Implicaciones metodológicas:

**A favor.** 3049 observaciones de 184 estaciones repartidas por el mundo y 9,6 años de
cobertura, imposible de replicar con una estación única. Los datos son verificables por
terceros: cualquiera puede descargar las mismas tramas.

**En contra.** No hay control sobre la instrumentación: cada estación tiene su antena, su
receptor y su nivel de ruido, y la red no publica RSSI por trama. Tampoco hay acceso a la
señal IQ original salvo que la estación la conserve.

**Validación cruzada.** El estado de calidad que asigna SatNOGS (`good`/`bad`) y el análisis
de bytes de este trabajo se obtuvieron por caminos independientes y coinciden:

| Estado | Observaciones | Frames | Balizas | % balizas |
|---|---:|---:|---:|---:|
| `good` | 488 | 6225 | 5929 | 95,2 % |
| `bad` | 1873 | 2415 | 6 | 0,2 % |

Que el 95,2 % de los frames de observaciones buenas sean balizas reconocibles, frente al
0,2 % de las malas, valida a la vez el criterio de la red y el decodificador implementado.

### 8.1 Acceso a los datos

Dos instalaciones distintas, con cuentas y tokens independientes:

- **SatNOGS DB** (`db.satnogs.org/api/telemetry`): frames con estación observadora. Requiere
  clave propia de esa instalación.
- **SatNOGS Network** (`network.satnogs.org/api/observations`): observaciones y sus archivos
  de demoddata, más los metadatos de pase. Es la vía que permite el conjunto ampliado.

El raspado del HTML no es alternativa: `robots.txt` prohíbe expresamente `/observations/`, y
el hexadecimal que muestra el navegador lo construye JavaScript a partir de los mismos
archivos que ofrece la API.

---

## 9. Comparación de protocolos

### 9.1 Capa física

| Esquema | Eficiencia espectral | Eb/N0 para BER 10⁻⁵ | Complejidad de receptor | Uso en CubeSats |
|---|---|---|---|---|
| **BPSK** | 1 bit/símbolo | ~9,6 dB (coherente) | Alta: requiere recuperación de portadora | Muy extendido a 9600 bps |
| **FSK** | 1 bit/símbolo | ~13,4 dB (no coherente) | Baja: detección de energía | Extendido a 1200–9600 bps |
| **GFSK** | 1 bit/símbolo | ~12,5 dB | Baja-media | Habitual en transceptores comerciales |
| **GMSK** | 1 bit/símbolo | ~9,6 dB | Media-alta | AX.25 a 9600 bps, D-STAR |

BPSK y GMSK comparten la eficiencia en potencia; GMSK añade envolvente constante, lo que
permite operar el amplificador en saturación —crítico con el presupuesto de energía de un
CubeSat—. GFSK y GMSK son las versiones con filtro gaussiano de FSK y MSK: reducen las
emisiones fuera de banda a cambio de interferencia entre símbolos controlada.

### 9.2 Capa de enlace y aplicación

| Protocolo | Ámbito | Overhead | Detección de errores | Adecuación |
|---|---|---|---|---|
| **AX.25** | Enlace, radioaficionado | 16+ B por trama | FCS CRC-16/X-25 | Estándar de facto en CubeSats universitarios; ineficiente en tramas cortas |
| **CCSDS** | Enlace y espacio profundo | Variable, mayor | Reed-Solomon, turbo, LDPC | Estándar de agencias; robusto pero complejo para un 3U |
| **CSP** | Red, interno del satélite | 4 B de cabecera | Delegada a la capa inferior | Diseñado para CubeSats (GomSpace); ligero, con direccionamiento tipo IP |
| **Baliza propietaria** (STRaND-1) | Enlace | 6 B de cabecera | CRC-ITT declarado | Mínimo overhead; sin interoperabilidad |

La baliza de STRaND-1 es un formato propietario con 6 bytes de cabecera sobre datos de 2 a
8 bytes: entre un 43 % y un 75 % de overhead. AX.25 sería aún peor para esas cargas —su
cabecera mínima ya supera los 16 bytes—, lo que explica la decisión de diseño. El coste es
la falta de interoperabilidad: cada decodificador debe implementarse a medida, y como se ha
visto, incluso la implementación de referencia puede tener errores.

---

## 10. Síntesis

La cadena completa, con lo que aporta cada eslabón sobre estos datos:

| Eslabón | Herramienta | Resultado obtenido |
|---|---|---|
| Señal RF → bits | Estaciones SatNOGS (demodulación FSK 9600) | 36 641 frames de 3049 observaciones |
| Bits → trama | Flag HDLC `C0 80` | 32 754 balizas, 89,4 % de integridad |
| Trama → paquete | Campos SEQ, LENGTH, ID, NODE, CHANNEL, DATA_SIZE | 5 subsistemas identificados |
| Paquete → variable | Ecuaciones de calibración de AMSAT-UK | 53 magnitudes, 26 con variación |
| Variable → estado | Análisis de dispersión y evolución temporal | Fallo progresivo del OBC, EPS sin instrumentación, cese de emisiones |

Lo que este recorrido añade frente a la literatura consultada es que **el eslabón débil no
está en la radio, sino en la interpretación**: el enlace tiene margen de sobra (7,1 dB en el
peor caso), las estaciones reciben correctamente (95,2 % de balizas en observaciones buenas)
y el formato está documentado desde 2013. Aun así, la telemetría llevaba años sin
interpretarse porque la herramienta de referencia leía mal un campo.

---

*Documento generado como parte del proyecto aplicado de Ingeniería Electrónica — UNAD, 2026.
Datos procesados a 28 de julio de 2026.*
