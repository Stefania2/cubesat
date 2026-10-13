# Informe técnico: Caracterización del subsistema de comunicaciones de un CubeSat mediante simulación de señales de radiofrecuencia

**Proyecto aplicado de Ingeniería Electrónica**

**Autora:** Mayelin Stefania Aguilar Vásquez  
**Línea de investigación:** Ciberseguridad y Telecomunicaciones  
**Universidad:** UNAD — Escuela de Ciencias Básicas, Tecnología e Ingeniería (ECBTI)

**Fecha:** Julio 2026

> Las tablas de resultados de este informe se generan automáticamente desde los
> archivos de `resultados_simulacion/` mediante `generar_tablas_informe.py`. No
> deben editarse a mano: cualquier cambio en los modelos se propaga volviendo a
> ejecutar el pipeline y ese script.

---

## Resumen

Este informe documenta el desarrollo de un modelo reproducible para la caracterización del subsistema electrónico de comunicaciones de un CubeSat, usando como referencia el satélite STRaND-1 (NORAD 39090). El trabajo integra: (1) procesamiento de telemetría real descargada de SatNOGS —36 641 tramas de 3049 observaciones, de noviembre de 2016 a julio de 2026—, con la decodificación de 32 754 balizas según la especificación publicada por AMSAT-UK, su conversión a magnitudes físicas y el diagnóstico del estado del satélite a partir de ellas, que permite fechar entre noviembre de 2020 y febrero de 2021 la degradación y el fallo definitivo de la instrumentación de su subsistema de energía; (2) simulación de enlace RF en banda base para modulaciones BPSK y FSK bajo canal AWGN —la modulación documentada del satélite es FSK a 9600 bit/s con NRZI; la BPSK es un modelo comparativo—; (3) un modelo avanzado que añade conformado de pulso RRC, desvanecimiento Rice, error residual de Doppler, codificación convolucional con decodificación Viterbi, tramas AX.25 verificadas por FCS y sincronización realista de portadora y símbolo con lazos de Costas y Gardner; (4) flujogramas en GNU Radio para visualización IQ y demodulación; (5) cálculo de link budget descendente y ascendente en UHF; (6) un modelo de estación terrena con seguimiento automático sobre un paso orbital completo, complementado con una ruta SGP4 con TLE real versionado y con el formato de validación para capturas IQ de un SDR; (7) comparación con parámetros documentados de 7 CubeSats reales y con los protocolos de enlace habituales en la industria; y (8) una plataforma web —FastAPI, React y PostgreSQL— que ingiere, decodifica y presenta la telemetría con un modelo de datos por capas que impide estructuralmente mostrar una interpretación como si fuera una medida; y (9) un gemelo digital que reconstruye el estado del satélite a partir de esos registros, lo reproduce en un eje temporal comprimido y lo representa en tres dimensiones, con detección de anomalías que fecha por sí sola el fallo de la instrumentación de energía y con la edad de cada lectura siempre a la vista. Todos los scripts, flujogramas y componentes se desarrollan con herramientas de software libre.

El resultado central es que la cadena completa —señal RF, demodulación, bits, tramas, paquetes, variables y estado del sistema— puede recorrerse íntegramente con datos de una red abierta de estaciones voluntarias, y que el eslabón que falla no es el enlace, sino la interpretación de los bytes.

---

## 1. Introducción

Los CubeSats se han consolidado como plataformas accesibles para misiones espaciales universitarias, pero el diseño de su subsistema de comunicaciones sigue siendo un desafío técnico que requiere validación mediante simulación antes de la implementación física. Este proyecto aborda la necesidad de contar con documentación técnica en español que describa, simule y caracterice cada componente del enlace de comunicaciones de un CubeSat, tomando como caso de estudio el satélite STRaND-1 y utilizando exclusivamente herramientas de software libre.

### 1.1 Objetivo general

Simular el enlace de radiofrecuencia (RF) de un CubeSat de observación mediante herramientas de software libre, utilizando telemetría real y un modelo digital que permita analizar la modulación, el canal, la recepción y la tasa de error de bit (BER, Bit Error Rate).

### 1.2 Objetivos específicos

1. Caracterizar los componentes de comunicaciones de STRaND-1 —antena, transceptor, módem y sistema de telemetría, seguimiento y comando (TT&C, Telemetry, Tracking and Command)— como referencia para un CubeSat de observación.
2. Implementar un modelo reproducible de enlace digital en banda base para las modulaciones BPSK (Binary Phase Shift Keying) y FSK (Frequency Shift Keying), con BER (Bit Error Rate), espectro y archivos IQ (componentes In-phase y Quadrature) compatibles con GNU Radio.
3. Evaluar el comportamiento del enlace bajo conformado RRC (Root Raised Cosine), desvanecimiento Rice, Doppler residual, codificación convolucional, verificación AX.25 (Amateur X.25), presupuesto de enlace y seguimiento de estación terrenal.
4. Integrar el modelo digital del enlace RF (Radio Frequency) con la telemetría real de STRaND-1 para el análisis conjunto de las condiciones de comunicación y la tasa de error de bit (BER, Bit Error Rate).

### 1.3 Alcance y trazabilidad

El trabajo es una caracterización académica reproducible, no la construcción, operación ni reparación física de un satélite. La simulación RF es un modelo equivalente en banda base: no sustituye una captura UHF real ni certifica un receptor de vuelo. La recuperación de portadora y de temporización de símbolo se implementa con lazos de Costas y Gardner (sección 5.4); la de trama sigue localizando las tramas por desplazamiento conocido. La validación contra capturas IQ reales de un SDR queda como trabajo futuro, aunque se define el formato para conservarlas (sección 8.2).

**Modulación real y modulación del modelo.** La modulación documentada del enlace descendente de STRaND-1 es **FSK a 9600 bit/s con tramas AX.25 (HDLC) y codificación NRZI** (AMSAT-UK; registro de transmisores de SatNOGS DB, hoy marcado *inactive*; recepción documentada por PY4ZBZ con módem G3RUH). Ninguna fuente consultada describe BPSK en este satélite. La BPSK coherente del modelo avanzado y de la cadena GNU Radio es, por tanto, un **modelo comparativo de banda base** elegido para estudiar conformado de pulso, sincronización y codificación; sus umbrales no son los del receptor FSK real. No están documentados —y aquí se tratan como incertidumbre— la desviación de frecuencia, el filtrado del modulador, el uso de aleatorizador G3RUH a bordo, la ganancia de la antena y el umbral de Eb/N0 de un receptor real. `parametros_enlace.py` es la fuente única de los parámetros del enlace y declara la procedencia de cada uno (documentado, deducido de datos o supuesto de diseño).

**Clases de dato.** A lo largo del informe se distinguen cuatro: *telemetría recibida* (bytes de SatNOGS, sin alterar), *magnitudes decodificadas* (con su estado de validación), *resultados simulados* (salidas de los modelos, con semilla y configuración registradas) y *valores teóricos* (curvas y presupuestos calculados). Un resultado simulado no es una medición del enlace.

El presente informe es la fuente integrada de resultados. Cada valor numérico debe poder rastrearse a un script, a sus parámetros y a los archivos de `resultados_simulacion/`. El script `generar_tablas_informe.py` actualiza las tablas marcadas del informe desde esas salidas; si cambia un modelo, se deben regenerar sus resultados y las tablas antes de publicar una conclusión.

---

## 2. Metodología y herramientas

### 2.1 Enfoque

El proyecto sigue un enfoque de simulación equivalente en banda base (*baseband equivalent model*), donde la portadora RF no se genera explícitamente sino que la señal modulada se representa mediante sus componentes I/Q. Este enfoque permite validar la cadena de modulación-canal-demodulación con bajo costo computacional, manteniendo la fidelidad necesaria para el análisis de BER, constelaciones y espectro.

**Relación entre SNR y Eb/N0.** Los barridos de las simulaciones se expresan en SNR por muestra sobre el ancho de banda de muestreo (76 800 Hz). Para una tasa de 9600 bps la conversión es:

$$\frac{E_b}{N_0}\bigg|_{dB} = \mathrm{SNR}_{dB} + 10\log_{10}\!\left(\frac{f_s}{R_b}\right) = \mathrm{SNR}_{dB} + 9{,}03\ \mathrm{dB}$$

Esta conversión es la que aplica `comparar_con_cubesats_reales.py` al superponer las curvas teóricas sobre los puntos simulados, y es imprescindible para no confundir ambas magnitudes al contrastar con la literatura.

### 2.2 Flujo de trabajo

```text
SatNOGS API
    ↓
[load_data.py] → frames hex
    ↓
[decodificar_frames_STRAND1.py] → bytes/binario
    ↓
┌──────────────────────────────┐   ┌──────────────────────────────────────┐
│ [simular_enlace_rf_fsk_bpsk] │   │ [simular_enlace_rf_bpsk_avanzado]    │
│  Modelo básico BPSK/FSK      │   │  RRC + Rice + Doppler + FEC + AX.25  │
│  AWGN, BER, archivos IQ      │   │  144 corridas                        │
└──────────────────────────────┘   └──────────────────────────────────────┘
    ↓                    ↓                       ↓
[GNU Radio]     [geometria_orbital.py] ← módulo común de geometría y ruido
                         ↓
      ┌──────────────────┼──────────────────┐
      ↓                  ↓                  ↓
[calcular_link_   [simular_enlace_   [modelo_estacion_
 budget.py]        ascendente.py]     terrena.py]
      ↓
[comparar_con_cubesats_reales.py] → 7 CubeSats documentados
      ↓
[generar_tablas_informe.py] → tablas de este informe
```

### 2.3 Herramientas

| Herramienta | Versión | Propósito |
|------------|---------|-----------|
| Python | 3.14 | Lenguaje principal de simulación |
| numpy | 2.5.1 | Procesamiento numérico y algebraico |
| scipy | 1.18.0 | Funciones especiales (erfc) |
| matplotlib | 3.11.0 | Graficación de resultados |
| pandas | 3.0.3 | Organización de datos tabulares |
| GNU Radio / GRC | 3.10.12 | Flujogramas de RF y visualización |

---

## 3. Procesamiento de datos reales de telemetría

### 3.1 Obtención de datos

Los datos se obtuvieron por dos vías distintas de la red SatNOGS, que son dos instalaciones separadas y con cuentas independientes:

1. **SatNOGS DB** (`db.satnogs.org/api/telemetry`), mediante `load_data.py`: 100 frames con estación observadora y payload en hexadecimal, almacenados en `frames_STRAND1.csv`. Es el conjunto con el que se hicieron las simulaciones de los capítulos 4 y 5.
2. **SatNOGS Network** (`network.satnogs.org/api/observations`), recorriendo cada observación del satélite y descargando sus archivos de *demoddata*. Esta vía amplía el conjunto en dos órdenes de magnitud y es la que permite el análisis de la sección 3.4.

La segunda vía se implementó porque el endpoint de telemetría de SatNOGS DB no entrega metadatos de observación y, además, exige autenticación con una clave propia de esa instalación. El listado HTML de Network no es una alternativa: su `robots.txt` prohíbe expresamente la ruta `/observations/`, y el hexadecimal que muestra el navegador lo construye JavaScript a partir de los mismos archivos de demoddata que sí ofrece la API.

### 3.2 Decodificación de frames

Conjunto ampliado con el archivo histórico de SatNOGS DB, a 28 de julio de 2026:

| Estadística | Valor |
|------------|-------|
| Frames procesados | 36 641 |
| Bytes totales | 517 878 |
| Bits totales evaluados | 4 143 024 |
| Longitud promedio de frame | 14.1 bytes |
| Entropía promedio del payload | 3.066 bits/byte |
| Entropía máxima posible para esas longitudes | 3.639 bits/byte |
| Observaciones | 3049 |
| Estaciones receptoras | 184 |
| Rango temporal | 2016-11-30 a 2026-07-13 |
| Balizas reconocidas | 32 754 (89,4 %) |
| Rango de las balizas | 2016-11-30 a 2023-01-29 |

**Dos fuentes distintas, con alcances distintos.** SatNOGS Network y SatNOGS DB
son instalaciones separadas. Network conserva las *observaciones* recientes, y
para STRaND-1 eso son apenas los meses de noviembre de 2022 a enero de 2023. DB
archiva las *tramas demoduladas* desde que el proyecto existe, y es la que
aporta el material de 2016 a 2022. Sin ese archivo, todas las magnitudes del
subsistema de energía aparecen constantes y no hay forma de distinguir un canal
que nunca midió de uno que dejó de medir; con él, la distinción se fecha
(sección 3.6).

El archivo de DB **no llega hasta el lanzamiento**: las consultas acotadas a
2013, 2014 y 2015 devuelven cero tramas. Los primeros tres años y medio de vida
del satélite no están en ninguna de las dos instalaciones, de modo que todo lo
que sigue describe el periodo 2016-2023, no la misión completa.

### 3.3 Interpretación de la entropía

La entropía medida (3.066 bits/byte) debe compararse con el **máximo posible para las longitudes de trama de este conjunto** (3.639 bits/byte), no con los 8 bits/byte de un byte arbitrario: una trama de $n$ bytes no puede superar $\log_2 n$ bits/byte, y aquí la longitud media es de 14,1 bytes.

La medida está a un 84 % de ese techo, y por tramos de longitud la proximidad va del 81 % en las tramas de 13 a 24 bytes —el tramo mayoritario, con 20 558 de las 36 641— al 97 % en las de 25 a 48. En las tramas de 1 a 4 bytes la entropía media es 1,01 frente a un máximo de 1,08; en las de 49 a 200, 5,35 frente a 6,07. Es decir, **casi todos los bytes de casi todas las tramas son distintos entre sí**, que es la firma de datos aleatorios y no la de un formato con cabeceras fijas.

Esto corrige la interpretación inicial de este trabajo, que leyó una entropía moderada como «mezcla de cabeceras de baja entropía y datos de sensores», consistente con tramas AX.25. Los datos no la sostienen: de las 36 641 tramas, solo **30 son candidatas a AX.25** por presentar un campo de direcciones plausible, y las 30 decodifican el mismo par de indicativos —`N7SKC` a `WH2XPM`—, que es tráfico terrestre de radioaficionado captado en la misma frecuencia, no una emisión del satélite. Ninguna trama del conjunto supera además la verificación de FCS de AX.25.

Las cifras de esta sección se reproducen con `analizar_entropia.py`, que recalcula la entropía desde el hexadecimal crudo de las 36 641 tramas ingeridas.

### 3.4 Decodificación de la baliza según la especificación de AMSAT-UK

STRaND-1 tiene formato de telemetría documentado: AMSAT-UK publicó en marzo de 2013 la hoja `amsat-strand-1-20130327.xlsx` con la estructura del paquete, el mapa de nodos y canales, y las **ecuaciones de calibración** que convierten cada cuenta ADC en magnitud física. SatNOGS DB, por su parte, declara para NORAD 39090 el decodificador `strand` del proyecto `satnogs-decoders`.

La estructura del paquete es:

```
C0 80 | SEQ (1B) | LENGTH (1B) | ID (1B) | I2C NODE (1B) | CHANNEL (1B) | DATA_SIZE (1B) | DATA (DATA_SIZE bytes)
```

`ID` vale `0x01` para baliza de módem y `0x02` para baliza de OBC. Los nodos documentados son `0x2C` (EPS), `0x2D` (paneles solares), `0x66` (placa de interruptores, *big endian*), `0x80` (OBC) y `0x89` (magnetómetros).

#### El decodificador oficial no sirve para obtener los valores

`satnogs-decoders` reconoce correctamente la estructura, pero su especificación Kaitai lee **un solo byte** (`read_u1`) allí donde el formato define un dato de 2, 4 u 8 bytes precedido de su tamaño. El resultado es que devuelve el byte `DATA_SIZE` como si fuera la medida:

```
C0 80 02 06 02 2C 03 02 00 00
                  ^^ ^^ ^^ ^^^^^
                  |  |  |  dato: cuenta ADC = 0x0000
                  |  |  DATA_SIZE = 2
                  |  canal 0x03 = BATTERY 0 VOLTAGE
                  nodo 0x2C = C/S EPS

  decodificador oficial  ->  battery_0_voltage_v = 2      (es el DATA_SIZE)
  especificación AMSAT   ->  -0.00945 x 0 + 9.7488 = 9.75 V
```

Esto explica un resultado que en una versión anterior de este informe se interpretó como que el satélite emitía con la carga útil vacía: **todos los campos parecían constantes porque lo que se estaba leyendo era el tamaño del campo**, que en efecto no cambia. La conclusión era un artefacto de la herramienta, no una propiedad de la señal.

Para este trabajo se implementó el decodificador siguiendo la hoja de AMSAT-UK (`backend/app/services/strand_amsat.py` en el repositorio de la plataforma de telemetría), con las ecuaciones de calibración publicadas. Se validó contra el ejemplo que la propia hoja incluye:

```
C0 00 DB DC 80 77 0C 02 80 0C 08 87 11 01 00 D0 E9 04 00 C0
                                  ^^^^^^^^^^^ 4B UNIX TIME LE = 70023
  esperado por la hoja : 70023 = THU, 01 JAN 1970 19:27:03 GMT
  obtenido             : 70023 = 1970-01-01 19:27:03 UTC
```

#### Qué canales emite realmente el satélite

Antes de interpretar valores conviene separar dos cosas que se confunden con facilidad: un canal que la especificación define pero el satélite no transmite, y un canal que sí transmite pero sin medida válida. La hoja de AMSAT-UK define 41 canales; sobre las 32 754 balizas del conjunto **solo aparecen 21**:

| Nodo | Emite | No emite nunca |
|:---|:---|:---|
| `0x2C` EPS | `battery_0/1_voltage` | ambas temperaturas de batería, ambas corrientes y sus indicadores de sentido |
| `0x2D` Paneles | 6 corrientes de panel (`adc1`, `adc4`, `adc7`, `adc10`, `adc13`, `adc31`) | las 6 temperaturas de panel, las 3 tensiones de par, las 3 corrientes de bus |
| `0x66` Interruptores | los 10 | — |
| `0x80` OBC | `obc_unix_time` | — |
| `0x89` Magnetómetros | los 3 ejes | — |

**Ninguna baliza de STRaND-1 transmite temperatura.** No es una limitación del decodificador ni del mapeo: el canal no viaja en la señal. Lo mismo ocurre con las tensiones de par de paneles y las corrientes de bus. Esto explica por qué el parámetro «Temperature» de la plataforma de telemetría no puede rellenarse nunca, y por qué se retiró de su catálogo en lugar de dejarlo mostrando permanentemente «Not available».

#### Resultados sobre las balizas reales

Aplicado a las 32 754 balizas del conjunto, el decodificador extrae **53 magnitudes distintas, de las cuales 42 varían**:

| Magnitud | Lecturas | Valores distintos | Rango |
|:---|---:|---:|:---|
| `magnetometer_z` | 523 | 245 | −386 923 a 426 153 cuentas |
| `magnetometer_x` | 533 | 241 | −420 000 a 706 153 cuentas |
| `magnetometer_y` | 533 | 232 | −450 000 a 366 153 cuentas |
| `switch_1_ppt_1_2` corriente | 186 | 72 | 240 a 265 mA |
| `battery_voltage` | 1647 | 68 | **6,31 a 9,75 V** |
| `obc_unix_time` | 4760 | 37 | **2 a 3043 s** |

Tres lecturas de estos datos:

1. **Los magnetómetros funcionan.** Son la telemetría con más variación del conjunto: más de doscientos valores distintos por eje, con signo y en rango simétrico, como corresponde a un sensor de campo magnético en órbita. La hoja de AMSAT-UK no publica ecuación de calibración para ellos —solo especifica «4B por eje, entero con signo, little endian»—, de modo que se reportan en cuentas y **no** en µT: escalarlos sin la constante del fabricante sería inventar la unidad.
2. **El reloj del OBC llega a marcar hasta 3043 s, y se degrada.** El campo de tiempo UNIX, que debería contar los segundos transcurridos desde 1970, no pasa de unos miles: el ordenador se reinicia continuamente y nunca sincroniza la hora. Pero el valor máximo que alcanza entre reinicios **cae a lo largo de la misión**, y esa evolución se detalla en la sección 3.6.
3. **Los convertidores ADC del EPS y de los paneles dejaron de leer en febrero de 2021.** Desde esa fecha su cuenta vale 0 en todas las balizas, y la ecuación de calibración convierte ese cero en el extremo de la escala —9,75 V para las baterías—, de modo que un canal muerto se presenta como una batería sana. Antes de esa fecha los mismos canales entregan medidas que varían. El fechado está en la sección 3.6.

En conjunto, el satélite **sí transmitió telemetría con contenido variable** en todos sus subsistemas instrumentados, y fue perdiéndolos por etapas. Es coherente con que SatNOGS marque hoy su transmisor como `inactive`.

#### Por qué una trama suelta no prueba nada

Durante este trabajo se identificó una baliza de 2018 con la cuenta ADC a 1023 y se tomó inicialmente como prueba de que los convertidores funcionaban en esa fecha. **El argumento no se sostiene, y conviene dejar constancia porque el error es instructivo:**

```
C0 80 06 06 02 2D 01 02 FF 03      2018-12-31
                        ^^^^^ cuenta ADC = 0x03FF = 1023
```

- Es **una sola lectura**. El criterio que sostiene todo este diagnóstico es la dispersión, y con $n = 1$ no hay dispersión que medir.
- 1023 es el **tope de escala** de un convertidor de 10 bits, es decir, el valor de riel. Es el número menos indicado para citarlo como evidencia de salud: `adc7_mx_array_current` aparece clavado justo en 1023 en los meses de 2016 y 2020 con muestra escasa.
- La cuenta cae **fuera del rango que ese mismo canal recorre en todos los demás años** (958–970 en 2016, 637–967 en 2017, 705–967 en 2020).

Lo que sí demuestra que la instrumentación funcionaba es la dispersión sobre muestras suficientes: en noviembre de 2020, `battery_0_voltage` da 9 lecturas con 9 valores distintos, y `adc10_pz_array_current` otras 9 con 9 valores distintos. Ese es el patrón de un convertidor midiendo.

Se comprobó además que las tramas no reconocidas no son balizas mal alineadas: el patrón `C0 80` no aparece en ninguno de los ocho desplazamientos de bit posibles. Sobre 2762 tramas se encontró en 9, cuando el azar predice unas 6 para un patrón de 16 bits en ese volumen de datos.

### 3.5 Contraste con el estado de la observación

SatNOGS asigna a cada observación un estado de calidad (`good`, `bad`, `failed`, `unknown`) que se decide en la red, con criterios de recepción, y es por tanto independiente del análisis de bytes de las secciones 3.3 y 3.4. Cruzar ambas cosas permite validar el diagnóstico sin razonamiento circular.

Se sincronizaron los metadatos de 2362 de las 2660 observaciones que referenciaban los frames en el momento de hacer este cruce, pidiendo cada una por su identificador a la API de SatNOGS Network. El conjunto creció después con el archivo histórico de SatNOGS DB hasta las 3049 observaciones de la sección 3.2; las cifras de este apartado corresponden por tanto al subconjunto sincronizado, que es el de la ventana 2022-2023:

| Estado de la observación | Observaciones | Frames | Balizas reconocidas | % de balizas |
|:---|---:|---:|---:|---:|
| `good` | 488 | 6225 | 5929 | **95.2 %** |
| `bad` | 1873 | 2415 | 6 | 0.2 % |
| sin sincronizar | 298 | 2301 | 2065 | 89.7 % |
| `unknown` | 1 | 1 | 0 | 0.0 % |

Las 298 observaciones «sin sincronizar» son las que aportó el último barrido y cuyos metadatos aún no se han completado desde SatNOGS Network. Su 89,7 % de balizas las sitúa junto a las `good`, lo que anticipa cuál será su estado.

La separación es prácticamente total y sostiene tres afirmaciones:

1. **Las observaciones `good` contienen señal auténtica del satélite.** El 95,2 % de sus frames son balizas que el decodificador oficial reconoce, con su flag HDLC y su estructura completa.
2. **Las observaciones `bad` no contienen telemetría.** Solo 6 de 2415 frames son balizas. El resto son los bytes de alta entropía analizados en la sección 3.3: falsos positivos que el demodulador FSK produce sobre ruido cuando no hay portadora. La trama de 23 bytes de la observación 7049034 —22 bytes distintos de 23— es un ejemplo típico.
3. **El criterio de calidad de la red y el análisis de bytes de este trabajo coinciden**, habiéndose obtenido por caminos independientes. Ninguno de los dos se apoya en el otro.

Esto delimita además el alcance de la sección 3.4: las magnitudes que allí se decodifican provienen de balizas recibidas en observaciones que la propia red califica de buenas, de modo que las anomalías detectadas —reinicios continuos del OBC, cuentas ADC del EPS a cero— no pueden atribuirse a una recepción deficiente en la estación terrena. Son lo que el satélite transmite.

El fechado de la sección 3.6 se apoya en el mismo argumento por otra vía: la transición de cuentas ADC válidas a cero ocurre entre dos meses consecutivos y se mantiene después durante veinticuatro meses seguidos, recibida por decenas de estaciones distintas. Un defecto de recepción no se comporta así.

### 3.6 Monitoreo de salud del satélite

Decodificar las variables permite pasar de la trama al **estado del sistema**, que es el objeto último de la telemetría. El criterio que sostiene este análisis es que **una variable que no varía no está midiendo**: un voltaje de batería idéntico en 578 balizas repartidas en dos meses no describe una batería estable, sino un canal muerto.

La distinción entre comportamiento normal y anómalo se apoya en tres hechos objetivos, sin necesidad de conocer los límites operativos que fijó el fabricante:

1. **Dispersión.** Los magnetómetros presentan desviación estándar de cientos de miles de cuentas (σ = 227 681 en el eje X); los convertidores del EPS y de los paneles, cero.
2. **Posición en la escala.** Una cuenta ADC de 0 produce, por la recta de calibración, el extremo del rango (9,75 V para las baterías). Un valor pegado al extremo indica saturación o ausencia de lectura, no una medida.
3. **Coherencia física.** Los magnetómetros entregan valores con signo y rango simétrico, como corresponde a un sensor de campo magnético en órbita.

| Indicador | Valor observado | Lectura |
|:---|:---|:---|
| Reloj UNIX del OBC | 2 – 3043 s, decreciente en el tiempo | El ordenador se reinicia continuamente y cada vez antes |
| Cuentas ADC del EPS y paneles | válidas hasta 2021-01, cero desde 2021-02 | Los convertidores dejaron de entregar lectura |
| Estado de los diez interruptores | `OFF` en todos | Cargas útiles y subsistemas apagados |
| Magnetómetros X / Y / Z | 241 / 232 / 245 valores distintos | Único subsistema sano hasta el final |

#### Fechado del fallo de la instrumentación de energía

El archivo histórico de SatNOGS DB permite lo que la ventana de 2022 por sí sola no permitía: distinguir un canal que nunca midió de uno que dejó de medir. El criterio es la cuenta ADC cruda, antes de calibrar, sobre todas las balizas disponibles:

Para acotar la fecha, la ventana de noviembre de 2020 a marzo de 2021 se descargó **día a día** en lugar de por muestreo, con 18 049 tramas adicionales. El resultado son tres fases netas:

| Fase | Periodo | Lecturas ADC | Con cuenta 0 | Proporción |
|:---|:---|---:|---:|---:|
| Instrumentación sana | 2016-11 a 2020-10 | 753 | 0 | **0,0 %** |
| Fallo intermitente | 2020-11 a 2021-01 | 5674 | 101 | **1,8 %** |
| Fallo permanente | 2021-02 a 2023-01 | 8501 | 8501 | **100,0 %** |

Ni una sola cuenta a cero en los primeros cuatro años de archivo; el 100 % en los veinticuatro meses finales, sin una sola excepción, hasta el cese de las balizas.

**La transición tiene tres fechas comprobables:**

- **27 de noviembre de 2020, 13:54:03 UTC** — primera lectura a cero de toda la serie, en `battery_0_voltage`.
- **31 de enero de 2021, 23:57:52 UTC** — última lectura válida jamás recibida de cualquiera de los ocho canales.
- **24 de febrero de 2021** — primer día de la muestra en que el 100 % de las lecturas son cero, condición que ya no se revierte.

El fallo definitivo cae por tanto entre el 1 y el 24 de febrero de 2021. El muestreo no permite estrecharlo más: entre esas dos fechas no hay balizas descargadas.

La fase intermitente se aprecia día a día y también dentro de un mismo pase. El 31 de enero de 2021, entre las 23:55:53 y las 23:57:52 UTC, `adc13_px_array_current` alterna entre cuenta 0 y cuenta 956:

| Día | Lecturas | A cero |
|:---|---:|---:|
| 2020-11-27 | 526 | 0,2 % |
| 2020-12-28 | 643 | 1,4 % |
| 2020-12-30 | 473 | **7,0 %** |
| 2021-01-29 | 750 | 6,0 % |
| 2021-01-31 | 791 | 1,5 % |
| 2021-02-24 | 201 | **100 %** |

Los ocho canales se ven afectados en proporción semejante durante la fase intermitente —entre el 0,9 % y el 2,7 %—, sin que ninguno se adelante a los demás:

| Canal | Lecturas a cero / total (2020-11 a 2021-01) |
|:---|---:|
| `adc10_pz_array_current` | 13 / 480 (2,7 %) |
| `adc31_mz_array_current` | 12 / 448 (2,7 %) |
| `adc4_my_array_current` | 13 / 498 (2,6 %) |
| `adc1_py_array_current` | 12 / 516 (2,3 %) |
| `adc13_px_array_current` | 16 / 800 (2,0 %) |
| `adc7_mx_array_current` | 13 / 646 (2,0 %) |
| `battery_1_voltage` | 10 / 987 (1,0 %) |
| `battery_0_voltage` | 12 / 1299 (0,9 %) |

Que los ocho fallen a la vez, con tasas del mismo orden y en la misma ventana de tres meses, apunta a una causa común aguas arriba —el bloque convertidor o su alimentación— y no a ocho sensores degradándose por separado. Las dos décimas de diferencia entre paneles y baterías no bastan para afirmar un orden de fallo entre ellos.

**Evolución del reloj de a bordo.** La misma serie histórica convierte el diagnóstico del OBC de una foto en una trayectoria:

| Periodo | Máximo del reloj |
|:---|---:|
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

El ordenador llegaba a sostener casi cincuenta minutos entre reinicios en 2019 y termina reiniciándose cada dos segundos en enero de 2023. La lectura de 866 s de julio de 2022 la recibieron **dos estaciones independientes** —UX5UL en KO50ei y LX2MT en JN39br— en el mismo segundo y con idéntico hexadecimal, lo que descarta que sea un artefacto de recepción.

El último dato es la ventana de emisión: las balizas se extienden del **30 de noviembre de 2016 al 29 de enero de 2023**, pese a que el conjunto de frames abarca hasta julio de 2026. Después de esa fecha no aparece ni una sola baliza reconocible en 3049 observaciones.

**Diagnóstico:** STRaND-1 perdió sus subsistemas por etapas. La instrumentación de energía se degradó desde noviembre de 2020 —con fallos intermitentes en los ocho canales por igual— y quedó definitivamente a cero en febrero de 2021, dejando al satélite emitiendo durante dos años más un voltaje de batería que era en realidad la ordenada al origen de una recta de calibración. El ordenador de a bordo se degradó en paralelo, de casi cincuenta minutos entre reinicios a dos segundos. Los magnetómetros siguieron entregando datos coherentes hasta el final. Las emisiones interpretables cesaron el 29 de enero de 2023.

#### Limitación conocida del conjunto

Un subconjunto de tramas presenta el **último byte alterado**. Se detecta porque produce valores imposibles: cuentas ADC por encima de 1023, que no caben en un convertidor de 10 bits y que extrapoladas por la recta de calibración dan −19 V de batería; y lecturas de magnetómetro de tres órdenes de magnitud por encima del resto, donde el eje termina en `57` en lugar del `FF` de extensión de signo que traen los otros.

**El defecto es de la estación receptora, no del satélite.** Sobre la ventana densa de noviembre de 2020 a enero de 2021, con 5674 lecturas repartidas entre doce estaciones que aportan al menos treinta cada una:

| Estación | Lecturas | Fuera de dominio |
|:---|---:|---:|
| W7KKE-CN75xa | 1810 | 92 (**5,1 %**) |
| UX5UL-KO50ei | 685 | 35 (**5,1 %**) |
| N2ACQ-FM07ag | 1826 | 73 (**4,0 %**) |
| YC9DCK-OI71oh | 32 | 1 (3,1 %) |
| EU1XX-KO33ru | 486 | **0** |
| SA2KNG Alt/Az-KP03cu | 395 | **0** |
| UY0LL-KN79xx | 227 | **0** |
| JA0CAW-PM97nw | 183 | **0** |

Cuatro estaciones producen cuentas fuera de dominio a tasas del 3 al 5 %; las otras ocho, ninguna, incluidas varias con muestras de cientos de lecturas. Si el satélite emitiera esos bytes, todas las estaciones los recibirían por igual. La conclusión es que se trata de un artefacto de demodulación de determinadas cadenas de recepción.

Esto obliga además a una cautela sobre el muestreo. En los meses cubiertos por una sola jornada —noviembre de 2019, agosto y octubre de 2020— la tasa aparente de lecturas fuera de dominio llega al 37,6 %, 22,4 % y 50,6 %, pero esas cifras describen qué estación observó ese día concreto, no el estado del satélite. En los meses con cobertura densa la tasa real baja al 4,6-6,1 %. **Las tasas por mes solo son comparables entre sí dentro de la ventana descargada día a día**, y por eso el fechado de la sección anterior se apoya en ella y no en el muestreo disperso.

Estas tramas **no llevan CRC** —su longitud es exactamente `8 + DATA_SIZE`, sin bytes sobrantes—, de modo que no hay forma estructural de detectarlas una a una. El decodificador de este trabajo conserva la cuenta cruda pero **no publica valor físico** cuando la cuenta sale del dominio de la recta de calibración, que es el único criterio objetivo disponible: no se descarta por inverosímil, se descarta por estar fuera del intervalo en el que la ecuación publicada está definida.

### 3.7 Indicadores de desempeño del enlace

| Indicador | Valor | Procedencia |
|:---|:---|:---|
| Integridad de la telemetría | 89,4 % (32 754 balizas de 36 641 frames) | Medido |
| Balizas por pase | media 14,7 · mediana 6 · máx 411 | Medido |
| Tiempo entre paquetes | mediana 2,0 s · p90 17,0 s | Medido |
| **Pérdida de paquetes dentro de ráfagas** | ver tabla de esta sección | Derivado, bajo hipótesis de contador |
| **Pureza de trama en horizonte / cenit** | **82,2 % a 0-14° · 96,9 % en cenit** | Medido |
| Observaciones con balizas | 775 de 3049 (25,4 %) | Medido |
| Estaciones que recibieron balizas | 114 | Medido |
| BER, PER y FER del modelo | tablas de §4 y §5 | Simulado |
| Margen descendente | tablas de §7 | Teórico / simulado |

#### Pérdida de paquetes estimada con el número de secuencia

La baliza lleva un contador de secuencia de 8 bits. **Hipótesis:** el satélite lo incrementa en uno por paquete emitido. La respaldan las ráfagas de 2016 a 2021, en las que llegan dos paquetes por segundo con contadores consecutivos; deja de cumplirse cuando el OBC se reinicia en bucle (desde 2022 abundan balizas con el contador clavado en 1), y esos tramos se excluyen.

Para cada *ráfaga* —balizas de una misma estación separadas menos de 30 s y con saltos de contador de hasta 32— se cuenta cuántos valores distintos del contador llegaron frente a cuántos abarca el tramo:

$$\text{pérdida} = 1 - \frac{\text{contadores distintos recibidos}}{c_{max} - c_{min} + 1}$$

<!-- TABLA:perdida_secuencia -->
| Elevacion maxima de la observacion | Rafagas | Emitidos (estimados) | Recibidos | Perdida |
|:---|---:|---:|---:|---:|
| 0-15° | 21 | 385 | 95 | 75.3 % |
| 15-30° | 30 | 852 | 317 | 62.8 % |
| 30-45° | 70 | 936 | 599 | 36.0 % |
| 45-60° | 61 | 570 | 359 | 37.0 % |
| 60-75° | 88 | 816 | 568 | 30.4 % |
| 75-90° | 139 | 992 | 636 | 35.9 % |
| **Global (todas las rafagas)** | 1403 | 30576 | 19311 | 36.8 % |
<!-- /TABLA:perdida_secuencia -->

Tres advertencias acotan lo que la cifra significa:

1. **No es la FER del paso.** Solo cuenta lo que falta *entre* paquetes recibidos. No ve lo perdido antes del primero ni después del último, ni los pasos sin ninguna recepción: es una cota inferior. Una FER empírica completa no es obtenible, porque SatNOGS solo registra las tramas demoduladas y no existe registro de las emitidas.
2. **No es atribuible solo al canal.** En la pérdida intervienen también la disponibilidad de la estación, el detector de señal, el demodulador y el decodificador.
3. **La elevación es la máxima de la observación**, no la del instante de cada trama, y solo existe para las observaciones de SatNOGS Network (2022 en adelante). Los tramos con pocas ráfagas tienen una incertidumbre grande.

*Corrección respecto de la versión anterior de este informe.* Antes se publicaba una PER del 64,2 % obtenida restando contadores de balizas consecutivas. La marca de tiempo de SatNOGS tiene 1 s de resolución y en ese segundo caben dos paquetes, que la base devuelve en cualquier orden: cada par desordenado se contaba como un «salto de 2» (un paquete perdido que no lo estaba). Contar valores distintos dentro de la ráfaga no depende del orden y da la cifra de la tabla, sensiblemente menor. La tendencia con la elevación se mantiene.

#### Coincidencias entre estaciones

Que un mismo contenido aparezca varias veces no es, por sí solo, una anomalía. STRaND-1 repite balizas idénticas (el reloj del OBC se reinicia y vuelve a emitir los mismos bytes), de modo que la igualdad de bytes no implica la misma emisión. Se define como **misma emisión** el mismo contenido recibido por estaciones distintas con marcas de tiempo a ±2 s; se conservan el origen y el instante de cada recepción, y el análisis es una capa derivada que no modifica la tabla de tramas (`tools/analizar_recepcion.py`).

<!-- TABLA:diversidad -->
| Magnitud | Valor |
|:---|:---|
| Balizas con observador | 30590 |
| Emisiones distintas recibidas | 28179 |
| Recibidas por 1 / 2 / 3 / 4 o mas estaciones | 26186 / 1697 / 210 / 86 |
| Ventanas con varias estaciones | 231 |
| Emisiones en esas ventanas: union / mejor estacion sola | 15153 / 11503 |
| Ganancia por combinacion | ×1.32 |
| M0KSF y M0KSF-BB, ventanas comunes | 30 |
| Solo M0KSF / solo M0KSF-BB / ambas | 249 / 33 / 215 |
| Ganancia de la union sobre la mejor del par | ×1.07 |
<!-- /TABLA:diversidad -->

La «ganancia por combinación» es el cociente entre las emisiones distintas recuperadas por todas las estaciones de una ventana y las que recupera la mejor estación sola. Es un resultado **observacional**: las estaciones difieren en antena, receptor, horario y disponibilidad, y los metadatos no permiten afirmar diversidad física del canal. Para el par M0KSF / M0KSF-BB, una parte apreciable de las emisiones llega a ambas: son la misma trama oída dos veces, no duplicados de ingesta (que la clave única contenido-instante-observador ya impide).

#### Un observable en lugar de RSSI

SatNOGS no publica potencia recibida por trama, de modo que el RSSI del enlace real no es accesible. Sí lo es el efecto que el RSSI produce: **la proporción de frames demodulados que resultan ser balizas válidas**. Cuando la señal es débil, el demodulador FSK de la estación entrega bytes de ruido que no llevan el flag HDLC; cuanto mejor es la relación señal-ruido, mayor es la fracción de frames que sí son balizas.

| Elevación máxima del pase | Observaciones | Con balizas | Frames que son balizas |
|:---|---:|---:|---:|
| 0 – 14° | 76 | 51,3 % | **82,2 %** |
| 15 – 29° | 103 | 49,5 % | 89,5 % |
| 30 – 44° | 140 | 50,0 % | 93,6 % |
| 45 – 59° | 116 | 45,7 % | 89,9 % |
| 60 – 74° | 101 | 51,5 % | 92,8 % |
| 75 – 89° | 147 | 57,1 % | 91,9 % |
| 90° | 3 | 66,7 % | **96,9 %** |

*(restringido a la ventana en que el satélite emitía balizas, hasta el 29 de enero de 2023)*

La pureza sube de 82,2 % a 96,9 % del horizonte al cenit. Es una medida indirecta y no sustituye a un vatímetro, pero se obtiene del mismo dato que ya se tiene y va en la dirección que exige la física del enlace.

Dos indicadores siguen **sin poder medirse** con esta fuente, y conviene declararlo:

- **RSSI y SNR absolutos del enlace real.** La API de SatNOGS no entrega potencia recibida por trama. Los valores de SNR en dB de este trabajo son de simulación; lo medido es el observable indirecto de la tabla anterior. Cerrar este hueco exige una estación terrena propia que registre potencia por paquete, no más trabajo sobre SatNOGS.
- **BER del enlace real.** Exigiría conocer los bits transmitidos, que es justamente lo que se desconoce. La BER de este trabajo es de simulación sobre bits reales usados como fuente.
- **Latencia extremo a extremo.** No hay marca de tiempo de generación utilizable a bordo: el reloj del OBC está averiado, que es uno de los hallazgos de la sección 3.6.

El desarrollo completo de esta cadena —de la señal RF al estado del satélite, con el detalle de procesamiento de señal, sincronización y comparación de protocolos— está en `docs/ANALISIS_TELEMETRIA_SALUD_CUBESAT.md`.

---

## 4. Modelo básico de simulación de enlace RF

### 4.1 Arquitectura

`simular_enlace_rf_fsk_bpsk.py` implementa la cadena mínima:

1. **Fuente:** `frames_STRAND1_gnuradio.bin` (18776 bits)
2. **Modulador BPSK:** mapeo NRZ (0→−1, 1→+1), 8 muestras/símbolo (76 800 sps)
3. **Modulador FSK:** tonos a ±2400 Hz, 8 muestras/símbolo
4. **Canal:** AWGN, SNR de −2 a 12 dB
5. **Demodulador BPSK:** integración sobre el símbolo + decisión de umbral (filtro adaptado al pulso rectangular)
6. **Demodulador FSK:** correlación con los dos tonos + decisión por máxima energía
7. **Métrica:** BER bit a bit

### 4.2 Resultados de BER

<!-- TABLA:ber_basico -->
| SNR por muestra (dB) | Eb/N0 (dB) | BER BPSK | BER FSK |
|:---|---:|---:|---:|
| -2 | 7.03 | 8.52e-04 | 1.08e-01 |
| 0 | 9.03 | 5.33e-05 | 5.33e-02 |
| 2 | 11.03 | 0 (sin errores) | 1.91e-02 |
| 4 | 13.03 | 0 (sin errores) | 3.89e-03 |
| 6 | 15.03 | 0 (sin errores) | 4.79e-04 |
| 8 | 17.03 | 0 (sin errores) | 0 (sin errores) |
| 10 | 19.03 | 0 (sin errores) | 0 (sin errores) |
| 12 | 21.03 | 0 (sin errores) | 0 (sin errores) |
<!-- /TABLA:ber_basico -->

### 4.3 Análisis

*Cómo leer esta comparación.* El eje es la SNR **por muestra**; con 8 muestras por símbolo, Eb/N0 = SNR + 9,03 dB (segunda columna de la tabla). Cada punto es una única realización de ruido sobre 18 776 bits, así que «0 errores» solo acota la BER por debajo de ≈2·10⁻⁴ con un 95 % de confianza. Y la FSK de este modelo (tonos a ±2400 Hz, detector de energía) **no es la forma de onda de STRaND-1**: es un modelo de banda base de la misma familia. La comparación es entre dos modelos, no un veredicto sobre el enlace real.

**BPSK** resulta más robusta que **FSK** en canal AWGN. La razón teórica es la distancia euclidiana entre símbolos: para BPSK antipodal es $2\sqrt{E_b}$, mientras que entre dos tonos FSK ortogonales es $\sqrt{2E_b}$, lo que da una ventaja de 3 dB en Eb/N0, a la que se suma la penalización de la detección no coherente.

Conviene señalar una limitación del modelo FSK: la separación entre tonos es de 4800 Hz, es decir $\Delta f \cdot T = 0{,}5$. Esa separación garantiza ortogonalidad para detección **coherente**, pero la detección por energía implementada requiere $\Delta f \cdot T \geq 1$ para ser estrictamente ortogonal. La FSK simulada arrastra por tanto una penalización adicional respecto a la curva teórica de FSK no coherente con la que se contrasta.

### 4.4 Ancho de banda

<!-- TABLA:ancho_banda_basico -->
| Modulacion | Ancho de banda (-20 dB) |
|:---|---:|
| BPSK | 27.0 kHz |
| FSK | 11.8 kHz |
<!-- /TABLA:ancho_banda_basico -->

La FSK ocupa menos ancho de banda porque concentra la energía en dos componentes espectrales discretas, mientras que la BPSK con pulso rectangular arrastra los lóbulos laterales del $\mathrm{sinc}^2$. La sección 5 muestra cómo el conformado RRC corrige esa desventaja de la BPSK.

---

## 5. Modelo avanzado de enlace

`simular_enlace_rf_bpsk_avanzado.py` es un modelo **BPSK de banda base (comparativo)** que añade a la cadena básica conformado RRC ($\alpha = 0{,}35$), recuperación de portadora (Costas) y de reloj (Gardner), desvanecimiento Rice, Doppler residual, código convolucional $r=1/2$, $K=7$ con Viterbi de decisión dura y tramas AX.25 con FCS.

### 5.1 Condiciones de comparación

Todas las configuraciones se comparan bajo las mismas reglas:

- **Mismos bits de entrada:** los 18 776 bits de telemetría real.
- **Misma definición de energía:** el eje es $E_b/N_0$ **por bit de información**. Con ruido complejo de varianza $\sigma^2$ por muestra, $\text{SNR}_{muestra} = (E_b/N_0)\cdot r / 8$, donde $r$ es la tasa del código: sin código, $E_b/N_0 - 9{,}03$ dB; con $r=1/2$, 3,01 dB menos. La versión anterior comparaba a igual SNR por muestra, lo que daba al código el doble de energía por bit de información.
- **Mismo canal:** el ruido y el desvanecimiento se generan con semillas comunes a todas las configuraciones (comparación pareada), y el nivel de ruido se fija con la potencia **transmitida**, no con la de la realización desvanecida.
- **Varios ensayos por punto**, con intervalos de confianza de Wilson al 95 %. Cuando no se observa ningún error, la tabla muestra «0 (< x)», donde x es la cota superior que la muestra permite afirmar.
- **Mismo criterio de conteo.** BER = bits erróneos / bits efectivamente comparados. Un *paquete* es un bloque de 64 bytes de telemetría (la carga útil de una trama AX.25); PER = paquetes erróneos o no recuperados / transmitidos. FER = (tramas con FCS inválido + tramas no recuperadas) / tramas transmitidas, y solo existe en los esquemas con trama AX.25: en el resto es **N/A**, no cero.
- **Ambigüedad de fase.** Un lazo de Costas BPSK engancha en 0° o en 180°. Se resuelve con los primeros 64 bits como palabra de sincronismo; un salto de ciclo posterior cuenta como error. Se informa además la **BER diferencial** (tras decodificar diferencialmente ambos flujos), que es la que vería un receptor insensible a la polaridad como el NRZI de STRaND-1.

<!-- TABLA:procedencia -->
| Elemento | Valor |
|:---|:---|
| Commit del codigo | d7dca58 |
| Fecha de la simulacion avanzada (UTC) | 2026-10-13T19:51:25+00:00 |
| Fecha del analisis del paso SGP4 (UTC) | 2026-10-13T19:51:31+00:00 |
| Semilla base | 20260701 |
| Semillas por corrida | ruido = (semilla_base, 1, ensayo, indice_EbN0); desvanecimiento = (semilla_base, 2, ensayo). Comunes a todas las configuraciones: comparacion pareada. |
| Ensayos por punto | 6 |
| Bits de informacion por ensayo | 18776 |
| Valores de Eb/N0 (dB) | 0, 1.5, 3, 4.5, 6, 7.5, 9, 10.5, 12 |
| Definicion de Eb/N0 | Eb/N0 por bit de informacion (antes del FEC; en AX.25, por bit de trama incluida la cabecera). SNR por muestra = Eb/N0 + 10 log10(tasa_codigo / 8). |
| Ambiguedad de fase | resuelta con los primeros 64 bits como palabra de sincronismo conocida; los saltos de ciclo posteriores cuentan como error |
| Semilla y corridas del Monte Carlo de margen | 20261013 · 5000 |
| TLE | tle/strand1_2026-08-09.tle (epoca 2026-08-09T10:55:44.461344+00:00) |
<!-- /TABLA:procedencia -->

### 5.2 Canal AWGN: validación y coste de la sincronización

<!-- TABLA:avanzado_principal -->
| Eb/N0 (dB) | SNR/muestra sin codigo (dB) | Teoria BPSK | RRC, sinc. ideal | RRC, Costas+Gardner | NRZ, Costas+Gardner | RRC + FEC |
|:---|---:|---:|---:|---:|---:|---:|
| 0.0 | -9.03 | 7.86e-02 | 7.88e-02 | 4.31e-01 | 5.03e-01 | 5.01e-01 |
| 1.5 | -7.53 | 4.64e-02 | 4.79e-02 | 2.65e-01 | 5.05e-01 | 4.80e-01 |
| 3.0 | -6.03 | 2.29e-02 | 2.21e-02 | 2.41e-02 | 4.02e-01 | 4.78e-01 |
| 4.5 | -4.53 | 8.79e-03 | 8.57e-03 | 9.24e-03 | 1.06e-01 | 7.81e-02 |
| 6.0 | -3.03 | 2.39e-03 | 2.25e-03 | 2.41e-03 | 6.88e-02 | 1.07e-04 |
| 7.5 | -1.53 | 3.99e-04 | 4.26e-04 | 4.53e-04 | 1.15e-01 | 0 (< 3.4e-05) |
| 9.0 | -0.03 | 3.36e-05 | 3.55e-05 | 4.44e-05 | 1.71e-02 | 0 (< 3.4e-05) |
| 10.5 | 1.47 | 1.08e-06 | 0 (< 3.4e-05) | 0 (< 3.4e-05) | 6.21e-03 | 0 (< 3.4e-05) |
| 12.0 | 2.97 | 9.01e-09 | 0 (< 3.4e-05) | 0 (< 3.4e-05) | 1.40e-03 | 0 (< 3.4e-05) |
<!-- /TABLA:avanzado_principal -->

Con sincronización ideal el modelo reproduce la curva teórica $Q(\sqrt{2E_b/N_0})$ dentro del intervalo de confianza en todo el barrido: es la validación del canal y de la normalización de energía. Con los lazos reales, la BPSK con RRC sigue esa curva desde 3 dB y se aparta por debajo, donde los lazos pierden el enganche. El pulso rectangular sin filtro adaptado obliga a los lazos a trabajar sobre todo el ancho de banda de muestreo y no se sostiene hasta valores mucho más altos: la ventaja del RRC no es solo espectral (el ancho de banda ocupado al 99 % pasa de ~66 kHz a ~11 kHz) sino de sincronización. Con el código, el receptor trabaja con 3 dB menos de energía por símbolo de canal a igual $E_b/N_0$, y su umbral de sincronización sube en consecuencia.

### 5.3 Ganancia de codificación

<!-- TABLA:ganancia_codificacion -->
| Objetivo | Canal | Eb/N0 sin codigo (dB) | Eb/N0 con codigo (dB) | Ganancia (dB) | Estado |
|:---|:---|:---|:---|:---|:---|
| BER 0.001 | awgn | 6.79 | 5.49 | 1.30 | medida |
| BER 0.001 | rice | N/A | N/A | N/A | no estimable: el barrido no encierra la BER objetivo en ambas curvas |
| FER 0.1 (AX.25) | awgn | 8.15 | 5.13 | 3.01 | medida |
| FER 0.1 (AX.25) | rice | N/A | 11.45 | N/A | no estimable: el barrido no encierra la FER objetivo en ambas curvas |
<!-- /TABLA:ganancia_codificacion -->

La ganancia se informa únicamente donde el barrido encierra la tasa de error objetivo en las dos curvas, y con la resolución del barrido como incertidumbre. La cifra de «≈4 dB» de versiones anteriores salía de comparar un único punto a igual SNR por muestra; a igual $E_b/N_0$ por bit de información la ganancia medida es la de la tabla. Es coherente con un Viterbi de **decisión dura** cuyo receptor, además, pierde sincronización antes que el no codificado.

### 5.4 Escenario con desvanecimiento Rice

El canal Rice se define con $K = P_{LOS}/P_{dif} = 10$ dB y potencia media total unitaria; la componente difusa es una suma de 64 sinusoides con ángulos y fases uniformes (modelo de Clarke), con frecuencia Doppler máxima de 150 Hz, que fija un tiempo de coherencia del orden de milisegundos. **Estos parámetros no proceden de medidas del enlace de STRaND-1:** el escenario es hipotético. (La implementación anterior generaba la componente difusa con la mitad de potencia —un $K$ efectivo de 13 dB— y una potencia media inferior a 1; la prueba `test_rice_potencia_unitaria_y_factor_k` fija ahora ambas propiedades.)

<!-- TABLA:avanzado_rice -->
| Eb/N0 (dB) | BER | BER diferencial | BER dif. con FEC | PER | FER AX.25 | FER AX.25 + FEC |
|:---|---:|---:|---:|---:|---:|---:|
| 0.0 | 4.85e-01 | 2.38e-01 | 4.60e-01 | 1.00e+00 | 1.00e+00 | 1.00e+00 |
| 1.5 | 4.48e-01 | 1.57e-01 | 3.89e-01 | 1.00e+00 | 1.00e+00 | 1.00e+00 |
| 3.0 | 3.93e-01 | 9.77e-02 | 2.11e-01 | 1.00e+00 | 1.00e+00 | 1.00e+00 |
| 4.5 | 1.18e-01 | 5.15e-02 | 8.77e-02 | 1.00e+00 | 1.00e+00 | 9.95e-01 |
| 6.0 | 4.86e-01 | 2.51e-02 | 2.67e-02 | 9.91e-01 | 1.00e+00 | 9.01e-01 |
| 7.5 | 3.70e-01 | 1.20e-02 | 8.24e-03 | 8.83e-01 | 9.23e-01 | 5.81e-01 |
| 9.0 | 2.35e-01 | 5.24e-03 | 3.47e-03 | 5.72e-01 | 6.85e-01 | 3.11e-01 |
| 10.5 | 6.02e-02 | 2.78e-03 | 8.52e-04 | 2.97e-01 | 3.60e-01 | 1.58e-01 |
| 12.0 | 8.70e-02 | 1.31e-03 | 5.68e-04 | 1.53e-01 | 1.71e-01 | 7.66e-02 |
<!-- /TABLA:avanzado_rice -->

En este escenario el receptor BPSK sufre saltos de ciclo: tras cada uno el flujo queda invertido y la BER sin decodificación diferencial deja de medir el canal. La BER diferencial y la FER —el verificador de trama acepta las dos polaridades— sí son interpretables y muestran un suelo de error que el código reduce pero no elimina. La lectura es de diseño: sobre un canal así, BPSK coherente sin codificación diferencial no es una opción robusta, lo que es coherente con que la baliza real use FSK con NRZI.

### 5.5 Doppler residual

El Doppler orbital completo se calcula con SGP4 en la sección 7.3 y alcanza unos ±9,8 kHz. Lo que llega al demodulador tras la precompensación de la estación es el **error de esa predicción**; aplicar el Doppler completo y restar la predicción equivale exactamente a aplicar su diferencia, que es lo que hace el modelo. Los residuales evaluados salen del propio paso: un error de tiempo de 0,1, 0,5 y 1 s en la culminación deja unos 10, 50 y 100 Hz, y se añade el caso de una portadora centrada cuya deriva (97 Hz/s) no se sigue.

<!-- TABLA:doppler_residual -->
| Eb/N0 (dB) | 0 Hz | residual 10 Hz | residual 50 Hz | residual 100 Hz | deriva 97 Hz/s |
|:---|---:|---:|---:|---:|---:|
| 0.0 | 1.81e-01 | 1.78e-01 | 1.76e-01 | 1.76e-01 | 1.77e-01 |
| 1.5 | 1.01e-01 | 1.01e-01 | 1.01e-01 | 9.94e-02 | 9.84e-02 |
| 3.0 | 4.70e-02 | 5.07e-02 | 4.89e-02 | 4.95e-02 | 4.86e-02 |
| 4.5 | 1.83e-02 | 2.02e-02 | 1.98e-02 | 1.86e-02 | 1.92e-02 |
| 6.0 | 4.83e-03 | 4.90e-03 | 5.04e-03 | 5.10e-03 | 4.81e-03 |
| 7.5 | 9.05e-04 | 1.05e-03 | 8.52e-04 | 7.63e-04 | 9.23e-04 |
| 9.0 | 8.88e-05 | 1.42e-04 | 5.33e-05 | 1.69e-04 | 1.42e-04 |
| 10.5 | 0 | 0 | 0 | 1.78e-05 | 1.78e-05 |
| 12.0 | 0 | 0 | 0 | 0 | 0 |
<!-- /TABLA:doppler_residual -->

*(BER diferencial, BPSK + RRC, canal AWGN.)* El lazo de Costas de 80 Hz absorbe 50 Hz y la deriva sin penalización apreciable; con 100 Hz el umbral de enganche sube. La versión anterior evaluaba residuales de 0,05 a 0,2 Hz, tres órdenes de magnitud por debajo de lo que la geometría del paso produce, y describía un desplazamiento fijo de 150 Hz como «Doppler orbital variable».

### 5.6 Tramas AX.25

Las tramas se construyen conforme a AX.25 2.2: direcciones de 7 bytes, control UI (0x03), PID 0xF0 y FCS CRC-16/X-25 calculado sobre los campos entre banderas. La telemetría se reparte en 37 tramas de hasta 64 bytes de información.

<!-- TABLA:ax25 -->
| Eb/N0 (dB) | BER | Tramas validas | FCS invalido | No recuperadas | FER | PER | Validas con FEC | FER con FEC |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 6.39e-01 | 0/222 | 222 | 0 | 1.00e+00 | 1.00e+00 | 0/222 | 1.00e+00 |
| 1.5 | 5.21e-02 | 0/222 | 222 | 0 | 1.00e+00 | 1.00e+00 | 0/222 | 1.00e+00 |
| 3.0 | 2.41e-02 | 0/222 | 222 | 0 | 1.00e+00 | 1.00e+00 | 1/222 | 9.95e-01 |
| 4.5 | 9.56e-03 | 0/222 | 222 | 0 | 1.00e+00 | 1.00e+00 | 156/222 | 2.97e-01 |
| 6.0 | 2.59e-03 | 50/222 | 172 | 0 | 7.75e-01 | 7.12e-01 | 217/222 | 2.25e-02 |
| 7.5 | 4.72e-04 | 162/222 | 60 | 0 | 2.70e-01 | 2.12e-01 | 222/222 | 0 (< 1.7e-02) |
| 9.0 | 4.05e-05 | 216/222 | 6 | 0 | 2.70e-02 | 2.70e-02 | 222/222 | 0 (< 1.7e-02) |
| 10.5 | 0 (< 2.6e-05) | 222/222 | 0 | 0 | 0 (< 1.7e-02) | 0 (< 1.7e-02) | 222/222 | 0 (< 1.7e-02) |
| 12.0 | 0 (< 2.6e-05) | 222/222 | 0 | 0 | 0 (< 1.7e-02) | 0 (< 1.7e-02) | 222/222 | 0 (< 1.7e-02) |
<!-- /TABLA:ax25 -->

La verificación es un cálculo real del FCS sobre los bytes recibidos. Se cuentan por separado las tramas válidas, las de FCS inválido y las no recuperadas. La delimitación de trama es ideal (desplazamiento conocido, sin búsqueda de banderas ni *bit stuffing*): es una limitación declarada.

### 5.7 Sincronización (Costas + Gardner)

Se introduce un desfase de reloj reproducible de 0,35 muestras y el receptor lo recupera con dos lazos que no conocen los bits: un **Costas de segundo orden** (detector `signo(I)·Q`, 80 Hz) y un **Gardner** no asistido por decisión con interpolación lineal. `tests/test_sincronizacion.py` verifica que ambos recuperan una BPSK RRC con desfase y 100 Hz de Doppler sin errores en ausencia de ruido.

### 5.8 Estimación de SNR desde las muestras IQ

Fijar la SNR de una simulación no es estimarla. `estimar_snr_iq.py` estima $E_s/N_0$ desde la señal recibida, sin conocer los bits, con el estimador **M2M4** sobre la salida del filtro adaptado a tasa de símbolo: $S = \sqrt{2M_2^2 - M_4}$, $N = M_2 - S$, con $M_2 = E\{|y|^2\}$ y $M_4 = E\{|y|^4\}$. Supone símbolos BPSK de amplitud constante, ruido gaussiano complejo y muestreo en el instante de símbolo.

<!-- TABLA:estimador_snr -->
| Canal | Reloj | Es/N0 real (dB) | Ventana (simbolos) | Ventanas validas | Media estimada (dB) | Sesgo (dB) | Desviacion (dB) |
|:---|---:|---:|---:|---:|---:|---:|---:|
| awgn | gardner | 0 | 64 | 968/1024 | 0.45 | 0.45 | 2.62 |
| awgn | gardner | 0 | 1024 | 64/64 | 0.16 | 0.16 | 0.78 |
| awgn | gardner | 6 | 64 | 1024/1024 | 6.12 | 0.12 | 1.20 |
| awgn | gardner | 6 | 1024 | 64/64 | 5.96 | -0.04 | 0.24 |
| awgn | gardner | 12 | 64 | 1024/1024 | 12.10 | 0.10 | 0.86 |
| awgn | gardner | 12 | 1024 | 64/64 | 11.96 | -0.04 | 0.19 |
| rice | gardner | 0 | 64 | 923/1024 | -0.07 | -0.07 | 2.79 |
| rice | gardner | 0 | 1024 | 64/64 | -0.89 | -0.89 | 0.91 |
| rice | gardner | 6 | 64 | 1023/1024 | 4.75 | -1.25 | 2.11 |
| rice | gardner | 6 | 1024 | 64/64 | 4.24 | -1.76 | 0.64 |
| rice | gardner | 12 | 64 | 1024/1024 | 9.06 | -2.94 | 2.48 |
| rice | gardner | 12 | 1024 | 64/64 | 7.82 | -4.18 | 0.76 |
<!-- /TABLA:estimador_snr -->

En AWGN el sesgo es de décimas de dB y la dispersión cae con el tamaño de la ventana; con 64 símbolos y baja SNR una parte de las ventanas no tiene solución real y se informa como no válida. Con desvanecimiento, la variación de amplitud dentro de la ventana se interpreta como ruido y el estimador **subestima** la SNR, tanto más cuanto mayor es esta. El resultado caracteriza al estimador sobre IQ **sintético**; no es una medida del canal real.

---

## 6. Implementación en GNU Radio

### 6.1 Flujograma de visualización IQ (`simulacion_visualizar_iq.grc`)

Visualiza en tiempo real las señales IQ generadas en la simulación, con control interactivo de ruido AWGN.

| Bloque | Configuración |
|--------|--------------|
| File Source | `resultados_simulacion/strand1_bpsk_iq_clean_complex64.bin`, Complex |
| Throttle | 76800 |
| Noise Source | Gaussiano, amplitud por QT GUI Range |
| QT GUI Time / Frequency / Constellation Sink | 76800 sps, 8 muestras/símbolo |

### 6.2 Flujograma de cadena completa BPSK (`simulacion_cadena_completa.grc`)

Cadena de transmisión BPSK completa desde los bytes de telemetría real hasta la demodulación, con cinco sinks visuales (tiempo, espectro, constelación, histograma y conteo de errores).

### 6.3 Limitaciones de la implementación GNU Radio

- El flujograma de visualización asume temporización y fase ideales: no incluye los lazos de Costas y Gardner que sí implementa el modelo Python (sección 5.4). Sirve para inspeccionar la señal y la constelación, no para medir la robustez de la sincronización.
- El bloque `Integrate` asume alineación perfecta de los límites de símbolo con la ventana de integración.
- Los archivos `.py` versionados contienen un ajuste manual (`import gnuradio.qtgui` en lugar de `import gnuradio`) necesario para que se ejecuten fuera de GRC. Al regenerarlos desde el `.grc` hay que reaplicarlo.

---

## 7. Link budget

### 7.1 Enlace descendente

`calcular_link_budget.py` modela el enlace descendente UHF a 437.568 MHz desde el CubeSat (LEO 775 km) hasta una estación terrena **hipotética** de radioaficionado. La cadena de unidades es:

$$P_{rx}\,[\text{dBm}] = P_{tx} + G_{tx} - L_{tx} + G_{rx} - L_{rx} - L_{FSPL} - L_{atm} - L_{pol} - L_{apunt}$$

$$N_0\,[\text{dBm/Hz}] = 10\log_{10}(k\,T_{sys}) + 30,\qquad C/N_0\,[\text{dB-Hz}] = P_{rx} - N_0,\qquad E_b/N_0\,[\text{dB}] = C/N_0 - 10\log_{10}R_b$$

$$\text{margen} = E_b/N_0 - \big[(E_b/N_0)_{teórica}(\text{BER objetivo}) + L_{impl}\big]$$

El umbral ya no es un número escrito a mano: se obtiene de la curva teórica de cada esquema para la BER objetivo. El margen principal se refiere al esquema **documentado** (FSK, cota no coherente $P_b = \tfrac12 e^{-E_b/2N_0}$) y el de BPSK coherente se informa aparte como modelo comparativo. $L_{impl}$ es una **reserva de diseño** para la degradación del demodulador real, no una pérdida física del trayecto; no se suma cuando el umbral procede del receptor simulado, que ya incluye esa degradación. La columna *Procedencia* distingue lo documentado para STRaND-1 de los supuestos de diseño.

<!-- TABLA:link_budget_parametros -->
| Parametro | Valor | Unidad | Procedencia |
|:---|---:|---:|---:|
| Frecuencia | 437.568 | MHz | documentado |
| Tasa de bits | 9600 | bit/s | documentado |
| Altura orbital | 775 | km | deducido |
| Potencia TX (satelite) | 30.0 | dBm | documentado |
| Ganancia antena TX | 0.0 | dBi | supuesto |
| Perdida cables TX | 0.5 | dB | supuesto |
| Ganancia antena RX | 15.0 | dBi | supuesto |
| Perdida cables RX | 2.0 | dB | supuesto |
| Figura de ruido RX | 2.0 | dB | supuesto |
| Temperatura de antena | 150.0 | K | supuesto |
| Temperatura de sistema | 371.3 | K | calculado |
| Perdida atmosferica | 0.5 | dB | supuesto |
| Perdida por polarizacion | 1.0 | dB | supuesto |
| Perdida por apuntamiento | 1.0 | dB | supuesto |
| Reserva de implementacion | 2.0 | dB | supuesto |
| Eb/N0 teorica, FSK no coherente | 13.35 | dB | calculado |
| Eb/N0 teorica, BPSK coherente | 9.59 | dB | calculado |
| BER objetivo | 1e-05 | - | calculado |
<!-- /TABLA:link_budget_parametros -->

La temperatura de sistema se calcula refiriendo el ruido a la entrada del receptor:

$$T_{sys} = \frac{T_{ant}}{L} + \frac{L-1}{L}T_0 + T_{rx}$$

donde $L$ es la pérdida del cable entre la antena y el LNA. Los cables no solo atenúan la señal: aportan su propio ruido térmico y atenúan el de la antena. Con 2 dB de cable la diferencia frente a sumar simplemente $T_{ant} + T_{rx}$ es de 0,65 dB de margen.

<!-- TABLA:link_budget -->
| Elevacion (deg) | Distancia (km) | FSPL (dB) | P_rx (dBm) | C/N0 (dB-Hz) | Eb/N0 (dB) | Margen FSK no coh. (dB) | Margen BPSK, modelo (dB) |
|:---|---:|---:|---:|---:|---:|---:|---:|
| 5 | 2728.6 | 153.99 | -113.99 | 58.91 | 19.09 | 3.74 | 7.5 |
| 15 | 1983.5 | 151.22 | -111.22 | 61.68 | 21.86 | 6.51 | 10.27 |
| 25 | 1517.6 | 148.89 | -108.89 | 64.01 | 24.19 | 8.84 | 12.6 |
| 30 | 1355.8 | 147.91 | -107.91 | 64.99 | 25.17 | 9.82 | 13.58 |
| 35 | 1227.3 | 147.05 | -107.05 | 65.85 | 26.03 | 10.68 | 14.44 |
| 45 | 1042.1 | 145.63 | -105.63 | 67.27 | 27.45 | 12.1 | 15.86 |
| 55 | 922.2 | 144.56 | -104.56 | 68.34 | 28.51 | 13.16 | 16.92 |
| 60 | 879.3 | 144.15 | -104.15 | 68.75 | 28.93 | 13.58 | 17.34 |
| 65 | 845.3 | 143.81 | -103.81 | 69.09 | 29.27 | 13.92 | 17.68 |
| 75 | 799.2 | 143.32 | -103.32 | 69.58 | 29.76 | 14.41 | 18.17 |
| 85 | 777.6 | 143.08 | -103.08 | 69.82 | 30.0 | 14.65 | 18.41 |
| 90 | 775.0 | 143.05 | -103.05 | 69.85 | 30.02 | 14.67 | 18.43 |
<!-- /TABLA:link_budget -->

Con el umbral teórico de FSK no coherente, el margen a 5° de elevación queda dentro del intervalo de 3-6 dB que la literatura recomienda como reserva (Larson & Wertz) y crece hacia el cenit; con el umbral de BPSK es unos 3,8 dB mayor, que es la diferencia entre las dos curvas a la BER objetivo. La versión anterior de este informe daba un único margen (7,1 dB a 5°) calculado con el umbral de BPSK y lo presentaba como el del satélite. **Un margen positivo en este cálculo no garantiza la recepción real:** la estación es hipotética, la mayoría de los parámetros son supuestos y el umbral de un receptor FSK real (discriminador de FM) no está documentado. La sección 7.3 cuantifica cuánto depende la conclusión de esos supuestos.

### 7.2 Enlace ascendente

`simular_enlace_ascendente.py` modela un enlace de comandos **hipotético** a 1200 bit/s en 435 MHz, con 10 W de transmisión desde la estación terrena y antena isotrópica a bordo. No representa el enlace ascendente real de STRaND-1 —eoPortal cita una asignación en VHF, 145,860 MHz—, cuyo módem y umbral no se han caracterizado en este trabajo: los valores sirven como ejercicio de dimensionamiento.

<!-- TABLA:uplink -->
| Elevacion (deg) | Distancia (km) | FSPL (dB) | C/N0 (dB-Hz) | Eb/N0 (dB) | Margen (dB) | Tasa max (kbps) |
|:---|---:|---:|---:|---:|---:|---:|
| 5 | 2728.6 | 153.94 | 66.04 | 35.25 | 23.25 | 253 |
| 15 | 1983.5 | 151.17 | 68.81 | 38.02 | 26.02 | 480 |
| 25 | 1517.6 | 148.84 | 71.13 | 40.34 | 28.34 | 819 |
| 30 | 1355.8 | 147.86 | 72.11 | 41.32 | 29.32 | 1027 |
| 35 | 1227.3 | 147.00 | 72.98 | 42.19 | 30.19 | 1253 |
| 45 | 1042.1 | 145.58 | 74.40 | 43.61 | 31.61 | 1737 |
| 55 | 922.2 | 144.51 | 75.46 | 44.67 | 32.67 | 2219 |
| 60 | 879.3 | 144.10 | 75.88 | 45.08 | 33.08 | 2441 |
| 65 | 845.3 | 143.76 | 76.22 | 45.43 | 33.43 | 2641 |
| 75 | 799.2 | 143.27 | 76.70 | 45.91 | 33.91 | 2954 |
| 85 | 777.6 | 143.03 | 76.94 | 46.15 | 34.15 | 3120 |
| 90 | 775.0 | 143.00 | 76.97 | 46.18 | 34.18 | 3142 |
<!-- /TABLA:uplink -->

En este escenario el ascendente dispone de mucho más margen que el descendente por la combinación de mayor potencia transmitida (10 W frente a 1 W), antena directiva en el extremo transmisor y una tasa ocho veces menor. La columna de tasa máxima indica la velocidad que agotaría ese margen manteniendo la Eb/N0 requerida: entre 253 kbps y 3,1 Mbps. No es una capacidad de Shannon, sino la tasa límite del enlace con el esquema de modulación y el objetivo de BER fijados.

### 7.3 Margen y Doppler a lo largo de un paso SGP4

`margen_paso_sgp4.py` encadena TLE versionado → SGP4 → posición relativa → distancia y velocidad radial → Doppler y su derivada → seguimiento del rotor → $P_{rx}$ → $C/N_0$ → $E_b/N_0$ → margen. Busca los pasos completos de las 48 h siguientes a la época del TLE y analiza el de mayor culminación con resolución de 1 s. La pérdida de apuntamiento no es aquí la reserva fija del barrido, sino la que resulta del rotor.

<!-- TABLA:doppler_paso -->
| Magnitud | Valor |
|:---|:---|
| Paso analizado (inicio UTC) | 2026-08-10T10:13:24.461344+00:00 |
| Culminacion | 84.07° |
| Antiguedad del TLE en el paso | 23.3 h |
| Doppler (elevacion >= 5°) | -9820 a +9808 Hz |
| Tasa de cambio maxima | 97.1 Hz/s |
| Coherencia v_radial vs d(distancia)/dt | diferencia maxima 0.51 m/s |
| Residual con error de tiempo de 0.1 s | max 9.7 Hz · rms 4.0 Hz |
| Residual con error de tiempo de 0.5 s | max 48.5 Hz · rms 20.1 Hz |
| Residual con error de tiempo de 1 s | max 97.1 Hz · rms 40.3 Hz |
| Residual con error de tiempo de 2 s | max 194.2 Hz · rms 80.5 Hz |
| Error de apuntamiento maximo del rotor | 0.20° (0.00 dB) |
<!-- /TABLA:doppler_paso -->

Convención de signo: $f_D = -v_r f/c$, con $v_r < 0$ en acercamiento, de modo que el Doppler es positivo al inicio del paso y negativo al final. SGP4 entrega el estado en TEME y la rotación a terrestre se hace con GMST sobre el elipsoide WGS-84, sin movimiento polar ni refracción. El *residual* se calcula restando al Doppler del paso el que predice el mismo TLE desplazado en el tiempo: es un modelo del error a lo largo de la traza, y los desplazamientos evaluados son escenarios, no una medida del error real del TLE.

<!-- TABLA:margen_paso -->
| Umbral | Tipo | Eb/N0 umbral (dB) | Min | p5 | p50 | Medio | Max | % tiempo > 0 | Duracion > 0 (s) |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fsk_no_coherente | teorico | 15.35 | 4.79 | 5.21 | 9.86 | 10.18 | 15.75 | 100.0 | 730 |
| fsk_coherente | teorico | 14.60 | 5.54 | 5.96 | 10.61 | 10.93 | 16.50 | 100.0 | 730 |
| bpsk_coherente | teorico | 11.59 | 8.55 | 8.97 | 13.62 | 13.94 | 19.51 | 100.0 | 730 |
| simulado_ber1e-3_rrc | calibrado receptor simulado | 6.79 | 13.35 | 13.78 | 18.42 | 18.74 | 24.31 | 100.0 | 730 |
| simulado_fer10_ax25 | calibrado receptor simulado | 8.15 | 11.99 | 12.41 | 17.06 | 17.38 | 22.95 | 100.0 | 730 |
| simulado_fer10_ax25_fec | calibrado receptor simulado | 5.13 | 15.01 | 15.44 | 20.08 | 20.40 | 25.97 | 100.0 | 730 |
<!-- /TABLA:margen_paso -->

*(Estadísticas con elevación ≥ 5°.)* Las tres primeras filas son márgenes respecto de **umbrales teóricos** más la reserva de implementación; las `simulado_*` son márgenes respecto del **umbral calibrado del receptor BPSK simulado** (sección 5), sin reserva adicional, y solo son aplicables a ese receptor.

**Sensibilidad.** Cada parámetro supuesto se varía dentro del rango asignado en `parametros_enlace.py`; el Monte Carlo los varía a la vez y añade hasta 4 dB al umbral para representar el desconocimiento del receptor FSK real.

<!-- TABLA:sensibilidad -->
| Parametro | Valor base | Incertidumbre | Procedencia | Δ margen con − (dB) | Δ margen con + (dB) |
|:---|---:|---:|---:|---:|---:|
| p_tx_dbm | 30 dBm | ±6 | documentado | -6.00 | +6.00 |
| g_tx_dbi | 0 dBi | ±2 | supuesto | -2.00 | +2.00 |
| g_rx_dbi | 15 dBi | ±2 | supuesto | -2.00 | +2.00 |
| l_pol_db | 1 dB | ±2 | supuesto | +2.00 | -2.00 |
| l_impl_db | 2 dB | ±2 | supuesto | +2.00 | -2.00 |
| l_rx_db | 2 dB | ±1 | supuesto | +1.28 | -1.21 |
| nf_rx_db | 2 dB | ±1 | supuesto | +1.28 | -1.21 |
| t_ant_k | 150 K | ±100 | supuesto | +0.81 | -0.68 |
| l_tx_db | 0.5 dB | ±0.5 | supuesto | +0.50 | -0.50 |
| l_atm_db | 0.5 dB | ±0.5 | supuesto | +0.50 | -0.50 |
| **Monte Carlo conjunto** | 5000 corridas | todos | - | p5: -4.67 | p95: +10.22 |
<!-- /TABLA:sensibilidad -->

La potencia transmitida domina: si la telemetría se emite en el modo de 0,25 W que eoPortal describe para baliza/CW, el margen baja 6 dB. Los rangos son de diseño, no errores medidos; el resultado dice cuánto depende la conclusión de los supuestos, no la probabilidad real de recibir.

---

## 8. Modelo de estación terrena con seguimiento

`modelo_estacion_terrena.py` simula un paso orbital completo sobre una traza de círculo máximo. Para un desplazamiento a lo largo de la traza $u = \omega t$ medido desde la culminación, la trigonometría esférica da $\cos\gamma = \cos\gamma_{min}\cos u$, de donde se obtienen elevación, azimut y distancia oblicua exactas para órbita circular. La geometría procede de `geometria_orbital.py`, el mismo módulo que usan los dos scripts de link budget.

<!-- TABLA:estacion_terrena -->
| Magnitud | Valor |
|:---|:---|
| Duracion del paso (horizonte a horizonte) | 15.0 min |
| Duracion util (elevacion > 5°) | 12.4 min |
| Elevacion de culminacion | 85.0° |
| Distancia oblicua | 778 - 2725 km |
| Temperatura de sistema | 308 - 376 K |
| C/N0 promedio | 65.8 dB-Hz |
| C/N0 minimo / maximo | 59.9 / 71.6 dB-Hz |
| Error de apuntamiento maximo | 0.77° |
| Perdida por apuntamiento maxima | 0.01 dB |
<!-- /TABLA:estacion_terrena -->

El hallazgo relevante es dinámico: cerca de la culminación de un paso casi cenital el azimut del satélite cambia más deprisa de lo que el rotor modelado (5 °/s) puede seguir. Con la antena preposicionada en el punto de adquisición, el error máximo fuera de boresight y la pérdida asociada son los de la tabla anterior, despreciables con un haz de 30°. La conclusión práctica es que la Yagi modelada tolera el límite de velocidad; una antena más directiva debe evaluarse de nuevo con el cálculo del error angular verdadero y no con una resta directa de azimutes.

### 8.1 Paso orbital con SGP4 y TLE real

El resto de los modelos usa una órbita circular para los barridos genéricos; `orbita_sgp4.py` añade una ruta reproducible con el propagador SGP4 (`sgp4`) para estudiar un paso concreto. El módulo lee el TLE de STRaND-1 conservado en `tle/` con su época, y calcula azimut, elevación, distancia, velocidad radial y Doppler con la conversión TEME→terrestre vía GMST.

El TLE de referencia (`tle/strand1_2026-08-09.tle`, NORAD 39090, época 2026-08-09T10:55:44 UTC) se conserva versionado junto al código para que el Doppler sea reproducible. `simular_paso_sgp4.py` propaga la ventana indicada y escribe `resultados_simulacion/paso_sgp4_strand1.json` con el TLE y la estación utilizados:

| Magnitud (estación Bogotá, 4.7110° N, 74.0721° O, 2600 m) | Valor |
|:---|:---|
| Ventana propagada | 6 h con paso de 10 s (2161 muestras) |
| Muestras visibles sobre 5° | 40 |
| Elevación máxima | 34.05° |
| Doppler en la ventana visible | −9054.4 a +2877.4 Hz |

El Doppler instantáneo en la época del TLE (+2877,4 Hz) se usa como desplazamiento de la captura IQ de referencia de la sección 8.2, encadenando la caracterización orbital con la validación SDR. La prueba `tests/test_orbita_sgp4.py` verifica la carga del TLE, su época UTC y la coherencia de la geometría resultante.

### 8.2 Formato de validación de captura IQ

La simulación no sustituye una recepción SDR. Para que una captura real pueda contrastarse contra el modelo sin ambigüedad, se define un par inmutable: el binario IQ y un manifiesto JSON con su contexto de adquisición (formato, tasa de muestreo, frecuencia central, fecha/hora UTC, satélite, receptor y antena). El script `validar_captura_iq.py` comprueba que esos metadatos existan, calcula duración, potencia, componente DC y pico espectral, y produce un informe que puede citarse junto al experimento (ver `docs/FORMATO_CAPTURA_SDR.md`).

Como no se dispone aún de una recepción física, se genera una **captura de referencia** (`generar_captura_iq_referencia.py`) que conserva la misma cadena del modelo —telemetría real de STRaND-1, BPSK RRC a 9600 bps, 76 800 muestras/s— con el Doppler SGP4 de la sección 8.1 aplicado y su secuencia de bits de referencia. El manifiesto declara explícitamente que se trata de una referencia sintetizada, no de una recepción: los campos `receiver` y `antenna` quedarán vacíos de hardware real hasta que se sustituya por una captura SDR. El validador reporta el pico espectral en +2877,5 Hz, coincidente con el Doppler calculado, y la traza de la validación queda en `captura/strand1_2026-08-09_validacion.json`.

---

## 9. Comparación con CubeSats reales

### 9.1 CubeSats de referencia

<!-- TABLA:cubesats -->
| CubeSat | Pais | Ano | Formato | Frecuencia (MHz) | Modulacion | Tasa (bps) | Verificado en fuente |
|:---|---:|---:|---:|---:|---:|---:|---:|
| STRaND-1 | Reino Unido | 2013 | 3U | 437.568 | FSK | 9600 | si |
| Libertad 1 | Colombia | 2007 | 1U | 437.405 | AFSK | 1200 | pendiente |
| FACSAT-1 | Colombia | 2018 | 3U | 437.375 | BPSK | 9600 | pendiente |
| Delfi-C3 | Paises Bajos | 2008 | 3U | 145.870 | BPSK | 1200 | pendiente |
| ESTCube-1 | Estonia | 2013 | 1U | 437.250 | BPSK | 9600 | pendiente |
| AAUSAT-II | Dinamarca | 2008 | 1U | 437.425 | AFSK | 1200 | pendiente |
| ITUPSAT 1 | Turquia | 2009 | 1U | 437.325 | BPSK | 9600 | pendiente |
<!-- /TABLA:cubesats -->

### 9.2 Concordancia por parámetro

<!-- TABLA:concordancia -->
| Parametro | Valor del modelo | Referencia | Relacion |
|:---|:---|:---|:---|
| Frecuencia de operacion | 437.568 MHz (UHF) | STRaND-1: 437.568 MHz (AMSAT-UK, SatNOGS DB) | Coincide por construccion: el modelo usa la frecuencia documentada del satelite. |
| Modulacion | BPSK coherente (modelo comparativo) y FSK de banda base | STRaND-1: FSK 9600, AX.25/HDLC, NRZI (AMSAT-UK, SatNOGS DB) | Parcial. La familia FSK coincide; la BPSK del modelo avanzado NO es la modulacion del satelite. La desviacion y el filtrado del modulador real no estan documentados. |
| Tasa de bits | 9600 bit/s | STRaND-1: 9600 bit/s (AMSAT-UK, SatNOGS DB) | Coincide por construccion. |
| Potencia de transmision | 1 W (30 dBm) | STRaND-1: 1 W nominal; 0.25 W en modo baliza/CW (eoPortal) | Coincide con el valor nominal. El modo en que se emite la telemetria no esta confirmado: -6 dB entra en la sensibilidad. |
| BER vs SNR - BPSK | BER 5.3e-05 a SNR por muestra de 0 dB (Eb/N0 9.03 dB)<br>0 errores en 18776 bits desde 2 dB | Teoria BPSK coherente: BER 3.4e-5 a Eb/N0 = 9 dB | Compatible con la teoria dentro del intervalo de confianza de una muestra de 18776 bits. No es una comparacion con el satelite: no existe BER medida del enlace real. |
| Margen de enlace (link budget) | 3.7 dB a elev=5 deg<br>14.7 dB a elev=90 deg<br>(FSK no coherente, umbral teorico) | Sin dato publicado del margen de STRaND-1. | No comparable con una medida. El valor es una prediccion con estacion hipotetica y parametros supuestos (ver sensibilidad). |
| Ancho de banda estimado | BPSK rectangular: ~27.0 kHz (-20 dB)<br>FSK: ~11.8 kHz (-20 dB)<br>BPSK + RRC (α=0.35): ~11.1 kHz (99 % ocupado) | Canalizacion UHF amateur: 25 kHz | El modelo con RRC cabe en el canal. El ancho de banda real de la emision de STRaND-1 no se ha medido en este trabajo. |
<!-- /TABLA:concordancia -->

La columna *Relación* describe qué puede afirmarse de cada parámetro. Frecuencia, tasa y potencia nominal coinciden **por construcción** —el modelo las toma de la documentación—; la modulación coincide solo en la familia FSK; el margen y la BER no son comparables con medidas porque no existen. De la tabla 9.1 solo la fila de STRaND-1 se ha contrastado con sus fuentes en esta revisión; las demás proceden de la recopilación inicial y quedan pendientes de verificar.

### 9.3 Comparación de protocolos

La elección de esquema de modulación y de protocolo de enlace condiciona el presupuesto de potencia, el ancho de banda ocupado y la complejidad del receptor. La comparación sitúa las decisiones de STRaND-1 en su contexto.

**Capa física:**

| Esquema | Eficiencia espectral | Eb/N0 para BER 10⁻⁵ | Complejidad de receptor | Uso en CubeSats |
|:---|:---|:---|:---|:---|
| BPSK | 1 bit/símbolo | ~9,6 dB (coherente) | Alta: recuperación de portadora | Usado en varios CubeSats |
| FSK | 1 bit/símbolo | ~13,4 dB (no coherente) | Baja: detección de energía | Extendido a 1200–9600 bps |
| GFSK | 1 bit/símbolo | ~12,5 dB | Baja-media | Habitual en transceptores comerciales |
| GMSK | 1 bit/símbolo | ~9,6 dB (coherente, ideal) | Media-alta | AX.25 a 9600 bps |

Los valores de Eb/N0 de la tabla son cotas teóricas en AWGN; los de FSK, GFSK y GMSK con demodulación por discriminador de FM —la habitual en 9600 bit/s de radioaficionado— son mayores y dependen del receptor. BPSK y GMSK coherentes comparten eficiencia en potencia, pero GMSK añade envolvente constante, lo que permite saturar el amplificador —una ventaja apreciable con el presupuesto de energía de un 3U—. La contrapartida de BPSK es espectral, y el conformado RRC la resuelve: baja de 66,1 kHz a 11,2 kHz, por debajo del ancho de banda de FSK.

**Capa de enlace y aplicación:**

| Protocolo | Ámbito | Overhead | Detección de errores | Adecuación |
|:---|:---|:---|:---|:---|
| AX.25 | Enlace, radioaficionado | 16+ B por trama | FCS CRC-16/X-25 | Muy usado en CubeSats universitarios; ineficiente en tramas cortas |
| CCSDS | Enlace y espacio profundo | Variable, mayor | Reed-Solomon, turbo, LDPC | Estándar de agencias; complejo para un 3U |
| CSP | Red, interno del satélite | 4 B de cabecera | Delegada a capa inferior | Diseñado para CubeSats; ligero, direccionamiento tipo IP |
| Baliza STRaND-1 | Enlace | 6 B de cabecera | CRC-ITT declarado | Overhead mínimo; sin interoperabilidad |

La baliza de STRaND-1 emplea 6 bytes de cabecera sobre datos de 2 a 8 bytes: entre un 43 % y un 75 % de overhead. AX.25 resultaría peor para cargas tan cortas, ya que su cabecera mínima supera los 16 bytes, lo que explica la decisión de diseño. El coste es la falta de interoperabilidad: cada decodificador debe implementarse a medida y, como se documenta en la sección 3.4, incluso la implementación de referencia puede contener errores.

---

## 10. Plataforma de visualización e interpretación

Las secciones anteriores producen resultados en forma de tablas y figuras estáticas. Para que la cadena completa —de la señal RF al estado del satélite— pueda recorrerse y cuestionarse sin ejecutar los scripts, se desarrolló una aplicación web que ingiere la telemetría, la decodifica y la muestra con su procedencia a la vista. Está en el directorio `telemetria_strand1/` del proyecto.

### 10.1 Arquitectura

| Capa | Tecnología | Función |
|:---|:---|:---|
| Almacenamiento | PostgreSQL | Persistencia de frames, observaciones, campos decodificados y reglas |
| API | FastAPI (Python 3.14) | 17 endpoints REST, documentación OpenAPI automática en `/docs` |
| Interfaz | React + TypeScript + Vite | Ocho pantallas, sin dependencias de servicios externos |
| Ingesta | `tools/` | Descarga de SatNOGS Network y del archivo histórico de SatNOGS DB |

Los routers de la API separan las responsabilidades por dominio: `frames` (datos crudos y sus métricas), `observations` (metadatos de la red), `telemetry` (parámetros decodificados), `decoder` (decodificación bajo demanda de un hexadecimal arbitrario), `anomalies` (reglas configurables de umbral), `export` (descarga en CSV y JSON de cada conjunto) y `analytics`.

### 10.2 El modelo de datos como garantía metodológica

La decisión de diseño central de la plataforma no es tecnológica sino epistemológica: **el modelo de datos hace estructuralmente imposible presentar una interpretación como si fuera una medida.** Los datos viven en cuatro capas explícitas:

| Capa | Contenido | Depende de |
|:---|:---|:---|
| `RAW` | `Frame.raw_hex`, tal como lo entrega SatNOGS. Nunca se altera | Nada |
| `PROCESSED` | Longitud, entropía, ratio de imprimibles, bytes distintos | Solo de los bytes |
| `DECODED` | `DecodedField`, magnitudes físicas con su unidad | De un `ProtocolDefinition` **validado** |
| `UNKNOWN` | Estado por defecto: `unclassified` | — |

Un frame sin protocolo identificado permanece en `unclassified` y **no recibe interpretación alguna**. Mientras la tabla `protocol_definitions` esté vacía, ningún parámetro puede pasar a `decoded`: es el mecanismo que impide que la aplicación invente el significado de los bytes. La instalación por defecto no trae ninguna definición, y la de STRaND-1 se registra explícitamente con su referencia bibliográfica —la hoja de AMSAT-UK— y la marca `validated`.

Esta separación es la que permitió detectar el error de la sección 3.4. Cuando el decodificador oficial devolvía el campo `DATA_SIZE` en lugar de la medida, la interfaz mostraba valores constantes; al conservarse la capa `PROCESSED` intacta junto a la `DECODED`, pudo comprobarse que los bytes sí variaban y que el fallo estaba en la interpretación, no en la señal.

### 10.3 Lo que la interfaz muestra, y lo que declara no saber

La pantalla de parámetros de telemetría distingue tres estados, cada uno con su motivo escrito:

- **`Decoded`** — el valor procede de una baliza decodificada con una definición validada.
- **`Medido`** — la magnitud se mide sobre los bytes sin suponer ningún formato. Es el caso de la entropía del payload, que tiene valor incluso cuando no hay protocolo con el que decodificar nada. Se distingue en color de `Decoded` porque pertenece a otra capa.
- **`Not decoded` / `Not available`** — el parámetro no se rellena, y se explica por qué: o no hay definición de protocolo validada, o el canal no aparece en las balizas recibidas.

Ese último estado es el que documenta el hallazgo de que STRaND-1 no transmite ningún canal de temperatura. Un parámetro que el satélite nunca envía no se muestra estimado ni interpolado: se muestra vacío, con el motivo al lado.

La tabla de campos decodificados añade dos columnas que un panel convencional omitiría y que aquí son parte del argumento:

- **Valores distintos.** Un campo que nunca cambia no está midiendo nada. La interfaz lo etiqueta `Constante` en lugar de presentarlo como una lectura estable, que es exactamente la confusión que produjo el «9,75 V de batería» de la sección 3.6.
- **Rango típico (percentiles 5 y 95)** junto al mínimo y el máximo. Cuando el máximo queda más de un orden de magnitud por encima del percentil 95, se marca con un aviso que explica el caso concreto: en los campos `*_adc` el criterio es objetivo —una cuenta por encima de 1023 no cabe en un convertidor de 10 bits—, y en el resto se declara que puede tratarse de una cola larga real o de una trama con bytes alterados, sin zanjar cuál, porque estas balizas no llevan CRC con el que distinguirlas.

### 10.4 Uso docente

El interés didáctico de la plataforma no está en mostrar telemetría, sino en **hacer visible el razonamiento que la valida**. Un estudiante puede:

1. Tomar un hexadecimal cualquiera de la pantalla de frames y pegarlo en el decodificador, que responde con la estructura del paquete campo a campo —nodo I2C, canal, tamaño del dato, cuenta ADC— y la ecuación de calibración aplicada.
2. Comprobar por sí mismo que una magnitud constante no es una medida, contrastando la columna de valores distintos con el estado del canal.
3. Exportar cualquier conjunto en CSV o JSON y rehacer el análisis con sus propias herramientas, que es la condición para que el resultado sea verificable y no haya que creerlo.

Frente a un panel que muestre «Batería: 9,75 V» sin más, la plataforma obliga a preguntarse de dónde sale ese número. En este caso la respuesta resultó ser que no salía de ninguna medida, sino de la ordenada al origen de una recta de calibración aplicada a un convertidor averiado —y esa pregunta, no el número, es lo que el proyecto pretende enseñar a hacer.

---

## 11. Gemelo digital: del registro al estado visible

Las secciones anteriores presentan la telemetría como series y tablas. Esta última construye sobre la misma base de datos un **gemelo digital**: una representación tridimensional del satélite cuyo estado visual lo gobiernan los registros, con reproducción temporal y detección de anomalías. El código vive en `gemelo_digital/` y se expone al frontend por la API descrita en §10.1.

### 11.1 Lo que los datos permiten y lo que no

El diseño no se eligió: lo impusieron tres propiedades del conjunto, medidas antes de escribir la primera línea de visualización con `gemelo_digital/analisis_estructura.py`.

**Ningún instante contiene el estado completo.** De las 21 833 marcas temporales con al menos una medida, ninguna trae más de **tres** magnitudes físicas: 24 170 tramas aportan dos, 5 269 aportan tres y 1 786 aportan una. La baliza rota entre canales, de modo que un pivote a formato ancho produce una matriz casi vacía.

**No es una serie regular.** Hay tramas en 657 días de un intervalo de 3 511, el **18,7 %**. La separación mediana entre tramas consecutivas es de 1 segundo —son ráfagas dentro de un pase— y la máxima de 365 días.

**Casi todas las magnitudes están muertas en el tramo reciente.** Desde 2022, `battery_voltage` solo toma dos valores separados por 4 mV. La ventana con variación real es 2020-2021.

De ahí que el gemelo declare **38 magnitudes** disponibles, de las que el clasificador considera aprovechables 32 y con variación insuficiente 6 —las corrientes de los interruptores, con 10 a 12 valores distintos en todo el archivo.

### 11.2 Reconstrucción de estado, con la edad a la vista

Como no existe un instante con el estado completo, el gemelo lo reconstruye arrastrando la última lectura conocida de cada magnitud. Eso es una **inferencia, no una medida**, y por tanto cada valor viaja con su **edad**: los segundos transcurridos desde que se midió de verdad.

| Frescura de la lectura | Umbral | Presentación |
|---|---|---|
| Fresca | ≤ 600 s (un pase) | opacidad plena |
| Vieja | ≤ 86 400 s (un día) | atenuada |
| Obsoleta | > 1 día | muy atenuada |

Sobre `battery_voltage`, la reconstrucción es fresca en el **82,1 %** de los eventos, vieja en 3 155 y obsoleta en 754. Ese último número es el que justifica la decisión: en 754 instantes el panel muestra un voltaje cuya medida tiene más de un día, y sin declararlo estaría afirmando algo que no sabe.

### 11.3 Reproducción sobre un eje comprimido

Reproducir el archivo contra el reloj real no funciona: con el 81,3 % del intervalo sin datos y huecos de hasta un año, la proyección pasaría casi todo el tiempo en negro. El motor agrupa los eventos en **588 pases** —sesiones separadas por más de 30 minutos— y construye un eje en el que el tiempo corre real dentro del pase y el hueco entre pases se recorta a 2 segundos.

Así, **2 250 días de archivo caben en 46,1 horas de eje virtual**: 164 838 s de duración acumulada de los pases más 587 saltos de 2 s. Se conserva lo que tiene significado físico —la cadencia de las balizas dentro de un pase— y se descarta el silencio.

### 11.4 Detección de anomalías: por qué basta lo simple

Se evaluaron Z-score, IQR, umbral dinámico, Isolation Forest y métodos de series temporales. Los tres últimos presuponen muestreo regular y un vector de estado, y aquí no hay ninguno de los dos. Se adoptaron dos reglas:

**Z-score robusto (mediana + MAD).** La media y la desviación típica se contaminan con los propios valores atípicos que se buscan; la mediana y la desviación absoluta mediana no. El factor 1,4826 devuelve la MAD a escala de desviación típica bajo normalidad.

**Canal enrielado.** Si la amplitud de la ventana no llega a una milésima de su propia escala, el convertidor no se está moviendo. Esta regla es imprescindible porque **en el fallo real la MAD vale cero y el z-score queda indefinido**: un canal muerto tiene dispersión nula, que es lo contrario de lo que un detector de atípicos persigue.

La ventana es de 51 lecturas, no de un intervalo fijo, porque el muestreo es irregular. Cuando esas 51 lecturas abarcan más de 30 días la referencia no es comparable y el punto se marca `sin_referencia` en lugar de contrastarse con un pasado ajeno.

Sobre `battery_voltage`, las 5 269 lecturas se reparten en 2 818 con el canal enrielado, 1 875 normales, 247 anomalías, 210 sin referencia y 119 advertencias. Cada etiqueta gobierna un estado del modelo 3D: `NOMINAL`, `ADVERTENCIA`, `CRITICO`, `INSTRUMENTACION_PERDIDA` y `SIN_REFERENCIA`.

### 11.5 El modelo 3D y la regla que lo gobierna

El modelo es un 3U a escala con cuerpo, cuatro paneles, dos antenas de latiguillo y tres testigos de subsistema, en React Three Fiber. La regla que lo rige es una sola: **ningún elemento visual se mueve si no hay una lectura que lo mueva.**

| Elemento | Lo gobierna | Sin dato |
|---|---|---|
| Color del cuerpo | etiqueta de anomalía | gris de «sin referencia» |
| Brillo de cada panel | corriente del panel, en mA | **gris**, no verde |
| Testigos de subsistema | corriente del interruptor | apagado |
| Opacidad | edad de la lectura | 25 % |
| Inclinación | magnetómetros (dato real) | sin inclinar |
| Giro | **sintético**, rotulado en la interfaz | — |

El gris de «sin dato» tiene que ser visible, porque la mayor parte del tiempo el satélite no está diciendo nada. Un panel pintado de verde por omisión convertiría el gemelo en una animación decorativa.

La rotación es el único elemento sintético, y la interfaz lo declara: **STRaND-1 no transmite actitud**. La inclinación sí procede de los magnetómetros, que fijan dos de los tres grados de libertad; el giro restante es un barrido constante. Conviene además filtrar `magnetometer_y`, cuyo **15,3 %** de lecturas desborda los ±10⁶ y llega a ±2,1 · 10⁹, cifras que no caben en el sensor.

### 11.6 Demostración: el fallo de febrero de 2021

El suceso que el gemelo reproduce no se inyectó: **está en los datos**. El detector lo sitúa por su cuenta.

| Magnitud del evento | Valor |
|---|---|
| Variable afectada | `battery_voltage` |
| Inicio | 2021-02-24 11:14:57 UTC |
| Valor esperado | 7,1795 V |
| Valor registrado | 9,7488 V |
| Diferencia | **+2,5693 V** |
| Estado resultante | `INSTRUMENTACION_PERDIDA` |

La fecha coincide con el primer día íntegramente a cero establecido en §3.6 por una vía independiente. El contraste entre ventanas explica por qué el fallo pasó desapercibido:

| | Sano (nov 2020 – ene 2021) | Muerto (desde mar 2021) |
|---|---:|---:|
| Lecturas | 1 896 | 2 363 |
| Recorrido | 0,148 – 9,753 V | 9,749 – 9,753 V |
| Desviación típica | **1,618** | **0,002** |
| Valores distintos | 520 | 2 |

**El valor sube, no baja.** Ninguna alarma por batería descargada se dispararía nunca. Lo que delata el fallo no es el nivel, es que la dispersión se desploma tres órdenes de magnitud —y esa es precisamente la magnitud que la regla de canal enrielado vigila.

Para validar la otra mitad del detector, `gemelo_digital/demo_pico.py --sintetico` inyecta sobre la ventana sana un transitorio de una sola lectura, **rotulado como artificial**: 9,049 V alterados a 18,756 V. El z-score robusto devuelve |z| = 34,3 y lo clasifica como anomalía. Ninguna de las dos reglas es suficiente por separado: el z-score caza el transitorio, el enrielamiento caza el fallo permanente.

### 11.7 Realidad virtual: alcance no cubierto

La arquitectura se eligió pensando en un visor —WebGL permite WebXR sobre la misma escena, sin segunda cadena de herramientas—, y se llegó a integrar. **Se retiró después por no disponer de hardware con el que verificarla**, y no se presenta como funcional.

Queda constancia de dos obstáculos, útiles para quien la reintegre. El primero es que WebXR solo se expone en **contexto seguro**: `localhost` lo es, pero un visor que acceda por la red local a `http://<ip>:5173` no, y entonces `navigator.xr` no existe siquiera. La vía limpia es un túnel USB —en un Quest, `adb reverse tcp:5173 tcp:5173`—, que deja al visor viendo `localhost`. El segundo es que el texto tridimensional de la biblioteca empleada resuelve sus fuentes contra un CDN externo, de modo que sin conexión la escena queda esperando indefinidamente; retirarla eliminó la última dependencia de red externa de la aplicación.

### 11.8 Reproducibilidad

| Comando | Qué produce |
|---|---|
| `python -m gemelo_digital.analisis_estructura` | Inventario de columnas, tipos y veredicto por magnitud |
| `python -m gemelo_digital.demo_fases_2_4` | Reconstrucción de estado, reproducción y detección |
| `python -m gemelo_digital.demo_pico --sintetico` | Demostración completa del fallo y del pico artificial |

El motor es independiente de la interfaz: no importa nada de la web y se gobierna desde consola, de modo que las cifras de esta sección se comprueban sin levantar el frontend.

---

## 12. Discusión

### 12.1 Hallazgos principales

1. **La modulación documentada de STRaND-1 es FSK a 9600 bit/s con NRZI; la BPSK del modelo es comparativa.** En los modelos de banda base, BPSK coherente necesita unos 3,8 dB menos de $E_b/N_0$ que FSK no coherente a la BER objetivo, que es la diferencia entre los dos márgenes de enlace que se informan.
2. **El conformado RRC reduce el ancho de banda ocupado de ~66 kHz a ~11 kHz** y, con su filtro adaptado, permite a los lazos de sincronización sostener la curva teórica desde 3 dB de $E_b/N_0$.
3. **La ganancia del código convolucional, medida a igual $E_b/N_0$ por bit de información, es la de la tabla de la sección 5.3**, menor que los «~4 dB» de versiones anteriores, que comparaban a igual SNR por muestra.
4. **El Doppler orbital del paso analizado es de ±9,8 kHz con hasta 97 Hz/s**; el receptor modelado tolera residuales de decenas de hercios tras la precompensación.
5. **El margen descendente predicho es positivo pero depende de supuestos**: la sensibilidad de la sección 7.3 muestra que la potencia de transmisión y el umbral del receptor real, ambos sin confirmar, pueden anularlo.
6. **El límite de velocidad del rotor de azimut no limita el enlace** con una antena de 30° de haz.
7. **Se decodificó telemetría real de STRaND-1 con la especificación de AMSAT-UK**: 32 754 balizas y 53 magnitudes, de las que 42 varían. Los magnetómetros están operativos (más de doscientos valores distintos por eje) y la batería fue medida de verdad entre 2016 y 2020, con el voltaje oscilando entre **6,31 y 8,94 V** como corresponde a ciclos de carga y descarga en órbita. El decodificador oficial de `satnogs-decoders` no sirve para este fin: lee un solo byte por canal y devuelve el campo `DATA_SIZE` en lugar de la medida.
8. **El estado de calidad que asigna SatNOGS y el análisis de bytes de este trabajo coinciden**, obtenidos por caminos independientes: el 95,2 % de los frames de observaciones `good` son balizas reconocibles, frente al 0,2 % de las `bad`. Que las anomalías del satélite —reloj del OBC degradándose, cuentas ADC del EPS a cero— aparezcan precisamente en las balizas de observaciones `good` descarta que sean un defecto de recepción.
9. **La telemetría fecha el fallo del subsistema de energía en febrero de 2021, tras tres meses de degradación.** El archivo histórico de SatNOGS DB no contiene ni una sola cuenta ADC a cero en las 753 lecturas de 2016 a octubre de 2020. La primera aparece el **27 de noviembre de 2020**, y durante tres meses el fallo es intermitente: 101 ceros en 5674 lecturas (1,8 %), repartidos por igual entre los ocho canales. La última lectura válida es del **31 de enero de 2021 a las 23:57:52 UTC**; desde el 24 de febrero de 2021 son cero las 8501 lecturas siguientes, sin una sola excepción, durante veinticuatro meses. En paralelo, el reloj del OBC pasa de sostener 3043 s entre reinicios en 2019 a quedarse fijo en 2 s en enero de 2023, cuando las balizas cesan pese a que las observaciones continúan hasta julio de 2026. El único subsistema coherente hasta el final fue el magnetómetro.
10. **El eslabón débil de la cadena no está en la radio, sino en la interpretación.** El modelo predice margen positivo, las estaciones reciben correctamente el 95,2 % de las balizas en observaciones buenas y el formato está publicado desde 2013; aun así la telemetría llevaba años sin interpretarse porque la implementación de referencia leía mal un campo del paquete.
11. **Una magnitud constante puede ser un canal muerto disfrazado de sistema sano.** Los 9,75 V de batería que STRaND-1 emitió durante sus dos últimos años no son una medida: son la ordenada al origen de la recta de calibración de AMSAT-UK, el valor que la ecuación devuelve cuando la cuenta ADC vale 0. Como las rectas son decrecientes, una cuenta nula no produce «cero» sino el extremo superior de la escala. Detectarlo exigió comparar con el archivo histórico; sin él, la lectura natural del dato habría sido «batería estable a 9,75 V».
12. **Una sola trama no demuestra el estado de un canal.** Durante el trabajo se tomó una baliza de 2018 con cuenta ADC 1023 como prueba de que los convertidores funcionaban. No lo era: es una única lectura, 1023 es el tope de escala de un convertidor de 10 bits —el valor de riel— y cae fuera del rango que ese canal recorre en todos los demás años. El diagnóstico solo se sostiene sobre la dispersión de muestras suficientes, no sobre ejemplares escogidos.

### 12.2 Limitaciones del modelo

- **Sincronización con umbral operativo:** la recuperación de portadora y temporización es real (Costas + Gardner, sección 5.4), pero por debajo de unos 3 dB de $E_b/N_0$ los lazos pierden el enganche y la BER deja de ser interpretable como error de canal. Un receptor de vuelo añadiría una secuencia de adquisición (preámbulo) para bajar ese umbral; aquí el demodulador parte directamente de los datos.
- **Sincronización de trama ideal:** el verificador de AX.25 comprueba el FCS sobre bytes recibidos reales, pero localiza las tramas por desplazamiento conocido; no hay búsqueda de banderas ni *bit stuffing*.
- **FEC limitado a código convolucional:** no se implementaron LDPC ni turbo códigos, ni decisión blanda en el Viterbi.
- **Canal sin multitrayecto completo:** se modelan Rice y Doppler, pero no reflexiones múltiples ni despolarización por rotación de Faraday.
- **Modelo orbital por barrido genérico con órbita circular:** los barridos de elevación (link budget, estación terrena) siguen usando órbita circular y Tierra esférica. El propagador SGP4 con TLE reales (sección 8.1) se usa para pasos concretos, no para los barridos.
- **Amplificador ideal:** no se modelan compresión AM-AM, AM-PM ni distorsión armónica del PA.
- **FSK con tonos no ortogonales** para el detector de energía empleado ($\Delta f\cdot T = 0{,}5$), lo que penaliza su curva frente a la teórica.
- **El receptor del modelo es BPSK**: no se ha simulado un demodulador FSK con discriminador como el que usan las estaciones reales, de modo que los umbrales medidos no son los del enlace de STRaND-1.
- **Sin ruido de fase, no linealidad del amplificador ni desbalance I/Q.** No se han añadido porque no hay parámetros del transmisor de STRaND-1 que los sustenten; introducirlos con valores arbitrarios aumentaría la complejidad sin aumentar la validez.
- **Sin modelo ionosférico.** En UHF la rotación de Faraday gira el plano de polarización una cantidad variable con el contenido electrónico; entre un monopolo lineal y una Yagi lineal eso produce desvanecimientos de polarización que aquí se representan solo con una reserva fija de 1 dB. El centelleo ionosférico, relevante en latitudes ecuatoriales como la de la estación hipotética, tampoco se modela. La atenuación por lluvia es despreciable a 437 MHz y no procede trasladarla de enlaces en bandas milimétricas.
- **Adaptación de modulación y codificación: no aplicable.** La baliza es un enlace de un solo sentido sin canal de retorno operativo por el que el satélite conozca la calidad de recepción, así que no puede adaptar su forma de onda durante el paso. Una política adaptativa solo podría estudiarse como escenario de diseño de otro sistema.
- **Un solo satélite:** los resultados corresponden a STRaND-1; generalizar requiere verificación independiente.

### 12.3 Trabajo futuro

1. Bajar el umbral de sincronización con una secuencia de adquisición (preámbulo) y cuantificar su efecto sobre la región de trabajo del receptor.
2. Incorporar decisión blanda en el decodificador Viterbi (≈2 dB adicionales) y evaluar LDPC.
3. Implementar el decodificador AX.25 completo con búsqueda de banderas y *bit stuffing*.
4. Sustituir la captura de referencia sintetizada (sección 8.2) por una captura IQ real de un SDR sobre un paso de STRaND-1, conservando el manifiesto definido y completando la validación BER contra la secuencia de bits de referencia.

---

## 13. Conclusiones

1. Se caracterizó el subsistema de comunicaciones del CubeSat STRaND-1 en sus cuatro componentes: antena (monopolo UHF; ganancia supuesta de 0 dBi), transceptor (1 W nominal a 437.568 MHz), módem (FSK a 9600 bit/s con NRZI según AMSAT-UK y SatNOGS; BPSK coherente solo como modelo comparativo) y TT&C (balizas de 15,0 bytes de media, con la estructura HDLC que define la especificación de AMSAT-UK).

2. El modelo en banda base reproduce la curva teórica de BPSK en AWGN dentro del intervalo de confianza cuando la sincronización es ideal, lo que valida el canal y la normalización de energía.

3. El modelo avanzado cuantifica, bajo condiciones de canal comunes y con intervalos de confianza: la reducción del ancho de banda por conformado RRC, la ganancia del código convolucional (sección 5.3), el coste de la sincronización real y la tolerancia al Doppler residual.

4. El presupuesto de enlace descendente da margen positivo respecto del umbral teórico de FSK no coherente, tanto en el barrido por elevación como a lo largo de un paso SGP4, pero la conclusión depende de parámetros supuestos (sección 7.3). El ascendente es un escenario hipotético.

5. El modelo de estación terrena sobre un paso completo de 15,0 minutos, con 12,4 minutos útiles sobre 5°, muestra que el límite de velocidad del rotor en azimut se evalúa contra una traza de círculo máximo y una antena de 30° de haz. Los valores vigentes —incluida la pérdida máxima de 0,01 dB— se regeneran desde `modelo_estacion_terrena.py` y `resultados_simulacion/estacion_terrena_seguimiento.json`.

6. La comparación con CubeSats de referencia sitúa el modelo en su contexto; solo los datos de STRaND-1 se han verificado en fuente (sección 9).

6 bis. **Qué se ha demostrado y qué no.** Por simulación: el comportamiento del modelo BPSK de banda base y del presupuesto de enlace bajo supuestos declarados. Por observación de telemetría real: el contenido y la evolución de las balizas, la coincidencia de recepciones entre estaciones y una cota inferior de la pérdida de paquetes dentro de las ráfagas recibidas. **No se puede afirmar todavía:** la BER, la FER, la SNR ni el margen del enlace real de STRaND-1, ni el umbral de un receptor FSK real; faltan una captura IQ de un SDR y una estación instrumentada.

7. Todos los scripts y flujogramas se desarrollaron con software libre y las tablas de este informe se generan automáticamente desde los datos, lo que hace el trabajo reproducible y auditable.

---

## 14. Referencias

1. AMSAT-UK. (2013). *STRAND-1 Packet Format* [hoja de cálculo]. Recuperado de https://ukamsat.files.wordpress.com/2013/03/amsat-strand-1-20130327.xlsx — especificación de la baliza: estructura del paquete, mapa de nodos I2C y canales, y ecuaciones de calibración de cada magnitud.
2. Bouwmeester, J., & Guo, J. (2010). Survey of worldwide pico- and nanosatellite missions, distributions and subsystem technology. *Acta Astronautica*, 67(7–8), 854–862.
3. Cal Poly SLO. (2022). *CubeSat Design Specification (CDS) Rev. 14*. California Polytechnic State University.
4. Fortescue, P., Swinerd, G., & Stark, J. (2011). *Spacecraft systems engineering* (4th ed.). John Wiley & Sons.
5. Larson, W. J., & Wertz, J. R. (Eds.). (1999). *Space mission analysis and design* (3rd ed.). Microcosm Press.
6. Maral, G., Bousquet, M., & Sun, Z. (2020). *Satellite communications systems* (6th ed.). John Wiley & Sons.
7. Pratt, T., Bostian, C., & Allnutt, J. (2003). *Satellite communications* (2nd ed.). John Wiley & Sons.
8. Proakis, J. G., & Salehi, M. (2008). *Digital communications* (5th ed.). McGraw-Hill.
9. Sklar, B. (2001). *Digital communications: Fundamentals and applications* (2nd ed.). Prentice Hall.
10. TAPR / ARRL. (1998). *AX.25 Link Access Protocol for Amateur Packet Radio, Version 2.2*.
11. UIT-R. (2012). *Recomendación SM.328-11: Espectros y anchuras de banda de las emisiones*.
12. GNU Radio Project. (2024). *GNU Radio Manual and C++ API Reference*.
13. SatNOGS. (2026). *SatNOGS DB — STRaND-1 telemetry data*. https://db.satnogs.org/
14. ISIS — Innovative Solutions in Space. *TRXUV Transceiver datasheet*.
15. GomSpace. *NanoCom TRX Transceiver datasheet*.
16. *(Pendiente de verificación: no localizada en la búsqueda del 2026-10-13; confirmar o retirar.)* Álvarez, R., & Restrepo, C. (2020). Desarrollo de tecnología espacial en Colombia: retos y perspectivas para la ingeniería nacional. *Revista Colombiana de Tecnología Avanzada*, 1(35), 1–10.
17. *(Pendiente de verificación: no localizada en la búsqueda del 2026-10-13; confirmar o retirar.)* Gómez, J. A., & Llano, G. (2018). Introducción al diseño de sistemas de comunicación para pequeños satélites. *Ingeniería y Ciencia*, 14(27), 123–148.
18. AMSAT-UK. (2013). *STRaND-1 Telemetry*. https://amsat-uk.org/satellites/telemetry/strand-1/strand-1-telemetry/ — «amateur radio AX.25 packet radio downlink on 437.568 MHz […] 9600 bps FSK modulated data with HDLC frame, NRZI encoding» (consultado el 2026-10-13).
19. SatNOGS DB. *Transmisores de NORAD 39090*: «UHF 9k6 FSK TLM», 437,568 MHz, modo FSK, 9600 baudios, estado *inactive*. https://db.satnogs.org/api/transmitters/?satellite__norad_cat_id=39090 (consultado el 2026-10-13).
20. eoPortal. *STRaND-1 (Surrey Training, Research and Nanosatellite Demonstrator 1)*. https://www.eoportal.org/satellite-missions/strand-1 — potencia de RF nominal de 1 W (0,25 W en modo baliza/CW), antenas monopolo, órbita de ~786 km (consultado el 2026-10-13). Cita 437,575 MHz como asignación del enlace descendente.
21. Zurmely, R. (PY4ZBZ). *STRaND-1*. https://qsl.net/py4zbz/strand.htm — recepción documentada de la telemetría a 9600 baudios con módem G3RUH; fuente de radioaficionado, usada como evidencia complementaria de observación.
22. Kenyon, S., Bridges, C. P., et al. (2011). STRaND-1: use of a $500 smartphone as the central avionics of a nanosatellite. *62nd International Astronautical Congress* (IAC-11, sesión B4.6B), Ciudad del Cabo. https://iafastro.directory/iac/archive/browse/IAC-11/B4/6B/10937/ *(No se ha podido consultar el texto completo; se cita como fuente primaria de la misión pendiente de revisión.)*
23. Pauluzzi, D. R., & Beaulieu, N. C. (2000). A comparison of SNR estimation techniques for the AWGN channel. *IEEE Transactions on Communications*, 48(10), 1681–1691.

---
## Apéndice A: Estructura del proyecto

```text
cubesat/
├── README.md
├── GUIA_GNURADIO.md
├── geometria_orbital.py                  # Geometria orbital y ruido (modulo comun)
├── load_data.py                          # Descarga de telemetria de SatNOGS
├── decodificar_frames_STRAND1.py         # Decodificacion de frames a bytes/binario
├── generar_iq_bpsk_desde_bin.py          # Generacion de archivos IQ
├── simular_enlace_rf_fsk_bpsk.py         # Modelo basico BPSK/FSK
├── simular_enlace_rf_bpsk_avanzado.py    # Modelo avanzado (RRC, Rice, Doppler, FEC, AX.25)
├── calcular_link_budget.py               # Link budget descendente
├── simular_enlace_ascendente.py          # Link budget ascendente
├── modelo_estacion_terrena.py            # Estacion terrena con seguimiento
├── comparar_con_cubesats_reales.py       # Comparacion con 7 CubeSats
├── analizar_entropia.py                  # Entropia de las tramas contra el techo log2(n)
├── generar_tablas_informe.py             # Regenera las tablas de este informe
│
├── gemelo_digital/                       # Motor del gemelo digital (seccion 11)
│   ├── datos.py                          # Carga desde PostgreSQL a DataFrames
│   ├── analisis_estructura.py            # Inventario de columnas y veredicto por magnitud
│   ├── estado.py                         # Reconstruccion por ultimo valor conocido, con edad
│   ├── reproduccion.py                   # Reproduccion temporal sobre eje comprimido
│   ├── anomalias.py                      # Z-score robusto y regla de canal enrielado
│   ├── demo_fases_2_4.py                 # Demostracion del motor de datos
│   └── demo_pico.py                      # Demostracion del fallo de febrero de 2021
├── simulacion_visualizar_iq.grc / .py    # GNU Radio: visualizacion IQ
├── simulacion_cadena_completa.grc / .py  # GNU Radio: cadena BPSK completa
├── orbita_sgp4.py                        # Propagacion SGP4 + geometria estacion-satelite
├── simular_paso_sgp4.py                  # Paso orbital con SGP4 y TLE versionado
├── validar_captura_iq.py                 # Validacion de captura IQ + manifiesto
├── generar_captura_iq_referencia.py      # Captura de referencia desde telemetria real
├── tle/strand1_2026-08-09.tle            # TLE de STRaND-1 con su epoca
├── captura/                              # Par inmutable: IQ de referencia + manifiesto
├── tests/                                # Pruebas automatizadas (pytest)
│   ├── test_orbita_sgp4.py
│   ├── test_sincronizacion.py
│   └── test_validar_captura_iq.py
├── frames_STRAND1.csv / .json            # Telemetria descargada
├── resumen_telemetria_STRAND1.json
├── frames_STRAND1_gnuradio.bin
├── docs/
│   ├── DISENO_MODELO_SIMULACION_ENLACE_RF.md
│   ├── CARACTERIZACION_COMPONENTES_COMMS.md
│   ├── ANALISIS_TELEMETRIA_SALUD_CUBESAT.md   # Cadena RF -> estado del satelite
│   ├── FORMATO_CAPTURA_SDR.md            # Formato de captura IQ + manifiesto
│   └── INFORME_TECNICO_FINAL.md
└── resultados_simulacion/
    ├── configuracion_modelo_rf.json
    ├── resultados_ber_fsk_bpsk.csv / curva_ber_fsk_bpsk.png
    ├── strand1_bpsk_iq_clean_complex64.bin / strand1_fsk_iq_clean_complex64.bin
    ├── resultados_simulacion_avanzada.csv / .json
    ├── simulacion_avanzada_resultados.png / espectro_rrc_comparacion.png
    ├── paso_sgp4_strand1.json            # Geometria SGP4 del paso (seccion 8.1)
    ├── link_budget_resultados.csv / link_budget_completo.json / link_budget_margen_enlace.png
    ├── enlace_ascendente_resultados.json / .png
    ├── estacion_terrena_seguimiento.json / .png
    ├── comparacion_ber_teorica_vs_simulada.png
    ├── comparacion_parametros_cubesats_reales.csv / .json
    └── cubesats_reales_referencia.csv / .json
```

---

*Documento generado como parte del proyecto aplicado de Ingeniería Electrónica — UNAD, 2026.*
