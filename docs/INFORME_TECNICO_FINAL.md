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

Este informe documenta el desarrollo de un modelo reproducible para la caracterización del subsistema electrónico de comunicaciones de un CubeSat, usando como referencia el satélite STRaND-1 (NORAD 39090). El trabajo integra: (1) procesamiento de telemetría real descargada de SatNOGS —36 641 tramas de 3049 observaciones, de noviembre de 2016 a julio de 2026—, con la decodificación de 32 754 balizas según la especificación publicada por AMSAT-UK, su conversión a magnitudes físicas y el diagnóstico del estado del satélite a partir de ellas, que permite fechar entre noviembre de 2020 y febrero de 2021 la degradación y el fallo definitivo de la instrumentación de su subsistema de energía; (2) simulación de enlace RF en banda base para modulaciones BPSK y FSK bajo canal AWGN; (3) un modelo avanzado que añade conformado de pulso RRC, desvanecimiento Rice, error residual de Doppler, codificación convolucional con decodificación Viterbi, tramas AX.25 verificadas por FCS y sincronización realista de portadora y símbolo con lazos de Costas y Gardner; (4) flujogramas en GNU Radio para visualización IQ y demodulación; (5) cálculo de link budget descendente y ascendente en UHF; (6) un modelo de estación terrena con seguimiento automático sobre un paso orbital completo, complementado con una ruta SGP4 con TLE real versionado y con el formato de validación para capturas IQ de un SDR; (7) comparación con parámetros documentados de 7 CubeSats reales y con los protocolos de enlace habituales en la industria; y (8) una plataforma web —FastAPI, React y PostgreSQL— que ingiere, decodifica y presenta la telemetría con un modelo de datos por capas que impide estructuralmente mostrar una interpretación como si fuera una medida; y (9) un gemelo digital que reconstruye el estado del satélite a partir de esos registros, lo reproduce en un eje temporal comprimido y lo representa en tres dimensiones, con detección de anomalías que fecha por sí sola el fallo de la instrumentación de energía y con la edad de cada lectura siempre a la vista. Todos los scripts, flujogramas y componentes se desarrollan con herramientas de software libre.

El resultado central es que la cadena completa —señal RF, demodulación, bits, tramas, paquetes, variables y estado del sistema— puede recorrerse íntegramente con datos de una red abierta de estaciones voluntarias, y que el eslabón que falla no es el enlace, sino la interpretación de los bytes.

---

## 1. Introducción

Los CubeSats se han consolidado como plataformas accesibles para misiones espaciales universitarias, pero el diseño de su subsistema de comunicaciones sigue siendo un desafío técnico que requiere validación mediante simulación antes de la implementación física. Este proyecto aborda la necesidad de contar con documentación técnica en español que describa, simule y caracterice cada componente del enlace de comunicaciones de un CubeSat, tomando como caso de estudio el satélite STRaND-1 y utilizando exclusivamente herramientas de software libre.

### 1.1 Objetivo general

Caracterizar y simular el subsistema electrónico de comunicaciones de un CubeSat de observación mediante herramientas de software libre, usando telemetría real y un modelo digital de enlace RF que permita analizar modulación, canal, recepción y tasa de error de bit.

### 1.2 Objetivos específicos

1. Caracterizar antena, transceptor, módem y TT&C de STRaND-1 como caso de referencia.
2. Obtener, conservar y decodificar telemetría real de SatNOGS hasta campos físicos y diagnósticos verificables del estado del satélite.
3. Implementar un modelo digital equivalente en banda base para comparar BPSK y FSK mediante BER, espectro y señales IQ de apoyo para GNU Radio.
4. Evaluar el enlace con conformado RRC, desvanecimiento, Doppler residual, FEC, AX.25, presupuesto de enlace y seguimiento de estación terrena.
5. Contrastar el modelo con parámetros documentados de CubeSats reales y generar las tablas del informe desde las salidas de los scripts.
6. Hacer trazable la interpretación de la telemetría en una plataforma web y un gemelo digital, distinguiendo datos crudos, datos procesados, valores decodificados e inferencias.

### 1.3 Alcance y trazabilidad

El trabajo es una caracterización académica reproducible, no la construcción, operación ni reparación física de un satélite. La simulación RF es un modelo equivalente en banda base: no sustituye una captura UHF real ni certifica un receptor de vuelo. La recuperación de portadora y de temporización de símbolo se implementa con lazos de Costas y Gardner (sección 5.4); la de trama sigue localizando las tramas por desplazamiento conocido. La validación contra capturas IQ reales de un SDR queda como trabajo futuro, aunque se define el formato para conservarlas (sección 8.2).

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
| **Packet Error Rate** | **64,2 %** (10 411 paquetes perdidos de 16 221 emitidos) | Medido |
| **PER en horizonte / cenit** | **79,1 % a 0-14° · 52,1 % a 75-89°** | Medido |
| **Pureza de trama en horizonte / cenit** | **82,2 % a 0-14° · 96,9 % en cenit** | Medido |
| Observaciones con balizas | 775 de 3049 (25,4 %) | Medido |
| Estaciones que recibieron balizas | 114 | Medido |
| BER BPSK / FSK | 0 para SNR ≥ 2 dB / ≥ 8 dB | Simulado (§4) |
| Margen descendente | 7,1 dB a 5° · 18,0 dB en cenit | Modelo (§7) |
| C/N₀ en un paso completo | 60,9 – 72,6 dB-Hz | Modelo (§8) |

#### Packet Error Rate medida sobre el número de secuencia

La baliza de STRaND-1 lleva un contador de secuencia de 8 bits que el satélite incrementa **en cada paquete emitido**. Entre dos balizas recibidas consecutivamente en un mismo pase, la diferencia de contadores dice cuántos paquetes emitió el satélite en ese intervalo, y por tanto cuántos no llegaron. Eso permite una PER genuina, no una cota:

$$\text{PER} = \frac{\sum (\Delta_i - 1)}{\sum \Delta_i}, \qquad \Delta_i = (s_{i+1} - s_i) \bmod 256$$

Se descartan las transiciones con $\Delta = 0$ —paquete repetido, recibido por dos estaciones— y con $\Delta > 32$, que corresponden a huecos entre pases y no a pérdidas dentro de uno. Sobre 775 pases y 5810 transiciones útiles:

| Elevación máxima del pase | Transiciones | Emitidos | Perdidos | PER |
|:---|---:|---:|---:|---:|
| 0 – 14° | 85 | 407 | 322 | **79,1 %** |
| 15 – 29° | 325 | 1086 | 761 | 70,1 % |
| 30 – 44° | 904 | 1738 | 834 | 48,0 % |
| 45 – 59° | 402 | 935 | 533 | 57,0 % |
| 60 – 74° | 530 | 1187 | 657 | 55,3 % |
| 75 – 89° | 645 | 1346 | 701 | **52,1 %** |
| **Global** | **5810** | **16 221** | **10 411** | **64,2 %** |

La PER cae 27 puntos del horizonte al cenit, que es la forma que predice el modelo de link budget de la sección 7: el margen pasa de 7,1 dB a 5° a 18,0 dB en cenit. La corrección de esta medida frente a la versión anterior de este informe está en que antes se contaban como pérdidas todos los huecos de secuencia, incluidos los que separan pases distintos; acotando $\Delta$ el resultado baja del 72,6 % declarado entonces al 64,2 % real.

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
| SNR (dB) | BER BPSK | BER FSK |
|:---|---:|---:|
| -2 | 8.52e-04 | 1.08e-01 |
| 0 | 5.33e-05 | 5.33e-02 |
| 2 | 0 (sin errores) | 1.91e-02 |
| 4 | 0 (sin errores) | 3.89e-03 |
| 6 | 0 (sin errores) | 4.79e-04 |
| 8 | 0 (sin errores) | 0 (sin errores) |
| 10 | 0 (sin errores) | 0 (sin errores) |
| 12 | 0 (sin errores) | 0 (sin errores) |
<!-- /TABLA:ber_basico -->

### 4.3 Análisis

**BPSK** resulta claramente más robusta que **FSK** en canal AWGN. La razón teórica es la distancia euclidiana entre símbolos: para BPSK antipodal es $2\sqrt{E_b}$, mientras que entre dos tonos FSK ortogonales es $\sqrt{2E_b}$, lo que da una ventaja de 3 dB en Eb/N0, a la que se suma la penalización de la detección no coherente.

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

`simular_enlace_rf_bpsk_avanzado.py` añade, como etapas componibles sobre la misma cadena, conformado de pulso RRC ($\alpha = 0{,}35$), desvanecimiento Rice con perfil Jakes ($K = 10$ dB), error residual de Doppler, codificación convolucional $r=1/2$, $K=7$ con decodificación Viterbi, construcción y verificación de tramas AX.25, y un receptor con **sincronización realista** (lazo de Costas para la portadora y lazo de Gardner para la temporización de símbolo, descritos en 5.4). Se evalúan 18 configuraciones en 8 puntos de SNR (144 corridas).

El barrido de SNR de este modelo (−10 a 4 dB) es más bajo que el del modelo básico porque el conformado de pulso correcto, el filtro adaptado y la recuperación de portadora permiten que la BPSK deje de cometer errores a partir de 2 dB. Los puntos superiores solapan con el modelo básico y permiten verificar que ambos coinciden: a 0 dB ambos dan BER $5{,}33\times10^{-5}$.

### 5.1 Resultados principales

<!-- TABLA:avanzado_principal -->
| Configuracion | BER a -8 dB | BER a -6 dB | BER a -4 dB | BER a -2 dB | Ancho de banda (99 %) |
|:---|---:|---:|---:|---:|---:|
| BPSK rectangular (NRZ) | 5.71e-01 | 1.47e-01 | 8.99e-02 | 4.52e-02 | 66.1 kHz |
| BPSK + RRC (α=0.35) | 6.18e-02 | 2.38e-02 | 6.76e-03 | 8.52e-04 | 11.2 kHz |
| BPSK rectangular (NRZ) + fading Rice | 4.17e-01 | 4.99e-01 | 7.98e-01 | 5.51e-02 | 66.1 kHz |
| BPSK + FEC conv. (r=1/2, K=7) | 4.92e-01 | 4.42e-01 | 5.85e-02 | 1.54e-03 | 66.0 kHz |
<!-- /TABLA:avanzado_principal -->

**Conformado RRC.** Con sincronización realista la ventaja del conformado deja de ser solo espectral. Con pulso rectangular sin filtro adaptado el receptor con sincronización trabaja sobre 9 dB más de ruido (todo el ancho de banda de muestreo de 76,8 kHz) y pierde el enganche: a −8 dB su BER es 5,7e−01. Con RRC y su filtro adaptado la BER a −8 dB es 6,2e−02 —prácticamente la misma que la del modelo de sincronización ideal— y además el ancho de banda ocupado al 99 % baja de ~66 kHz a ~11 kHz, un factor de 5,9, cerca del límite teórico $R_b(1+\alpha) = 12{,}96$ kHz y dentro de la canalización UHF de 25 kHz. El filtro adaptado no solo conserva la relación señal-ruido en el instante de decisión: es lo que da al lazo de temporización un espectro limpio donde engancharse.

**Desvanecimiento Rice.** Con $K = 10$ dB la componente de línea de vista domina, pero en presencia de desvanecimiento los lazos de sincronización se ven forzados al mínimo. A −2 dB la penalización es de unos 3 dB (5,5e−02 frente a 4,5e−02 del NRZ sin desvanecer); por debajo, los desvanecimientos profundos hacen perder el enganche y la BER deja de ser interpretable como error de canal. Es la primera manifestación de un **umbral de sincronización**: la región útil del receptor empieza alrededor de −6 dB.

**Codificación convolucional.** El código aporta ganancia en cuanto el lazo de temporización sostiene la sincronización: a −2 dB reduce la BER de 4,5e−02 (sin codificar) a 1,5e−03, unas 29 veces (≈4 dB). Por debajo de −5 dB la BER de entrada al decodificador supera su umbral de decisión dura y la decodificación empeora el resultado, el comportamiento clásico del Viterbi cuando la tasa de error excede su capacidad de corrección.

### 5.2 Sensibilidad al error residual de Doppler

El desplazamiento Doppler para una órbita LEO a 437 MHz alcanza ±150 Hz (±10 kHz sobre la portadora real; aquí se modela el residuo en banda base). La estación terrena lo pre-compensa a partir de la predicción TLE, de modo que lo que llega al demodulador no es el Doppler completo sino el **error de esa predicción**. La tabla recoge esa sensibilidad:

<!-- TABLA:doppler_residual -->
| Residual de Doppler | BER a -8 dB | BER a -4 dB | BER a 0 dB | BER a 4 dB |
|:---|---:|---:|---:|---:|
| 0 Hz | 5.71e-01 | 8.99e-02 | 1.73e-02 | 3.20e-04 |
| 0.05 Hz | 3.61e-01 | 9.49e-02 | 1.56e-02 | 7.46e-04 |
| 0.1 Hz | 5.00e-01 | 9.33e-02 | 1.60e-02 | 3.73e-04 |
| 0.2 Hz | 4.98e-01 | 5.04e-01 | 1.69e-02 | 4.79e-04 |
<!-- /TABLA:doppler_residual -->

La tabla corresponde a la configuración NRZ sin filtro adaptado, la más exigente para los lazos. En el modelo de sincronización ideal (sin recuperación de portadora) un residual de 0,2 Hz bastaba para producir un piso de error irreducible de 3,6e−01 sobre el registro de 1,96 s, porque la fase acumulada $2\pi f_{res} T$ giraba sin corrección y bastaba superar $\pi/2$ para invertir las decisiones. **Con el lazo de Costas (ancho de banda de 80 Hz) ese residual se recupera**: en la región de enganche (0 dB) la BER es 1,7e−02 tanto con 0,2 Hz como con 0 Hz, y a 4 dB baja a 5e−04. La tabla muestra que la sensibilidad al Doppler residual dejó de ser el eslabón crítico: el límite operativo lo marca ahora el umbral de sincronización (deslizamientos de ciclo por debajo de ~−6 dB), no la deriva de portadora.

### 5.3 Tramas AX.25

Las tramas se construyen conforme a AX.25 2.2: campo de dirección de 7 bytes por indicativo con los caracteres desplazados un bit y el bit de fin de dirección en el último byte, control UI (0x03), PID 0xF0 y FCS CRC-16/X-25 (polinomio 0x1021 reflejado, inicialización 0xFFFF, salida complementada, byte bajo primero). El FCS cubre únicamente los campos entre banderas, como exige la norma. La telemetría se reparte en 37 tramas de hasta 64 bytes de información.

<!-- TABLA:ax25 -->
| SNR (dB) | BER | Tramas validas por FCS (de 37) |
|:---|---:|---:|
| -10 | 4.71e-01 | 0 |
| -8 | 6.34e-01 | 0 |
| -6 | 2.52e-02 | 0 |
| -4 | 6.48e-03 | 0 |
| -2 | 1.13e-03 | 17 |
| 0 | 0 (sin errores) | 37 |
| 2 | 0 (sin errores) | 37 |
| 4 | 0 (sin errores) | 37 |
<!-- /TABLA:ax25 -->

La verificación es un cálculo real del FCS sobre los bytes recibidos, no una comparación con la trama transmitida. La transición es abrupta —de 0 tramas válidas a −4 dB a 17 a −2 dB y las 37 a partir de 0 dB— porque el FCS es una comprobación de todo o nada: un solo bit erróneo invalida la trama completa. Con tramas de 40 a 104 bytes, una BER de $10^{-3}$ ya corrompe la mayoría; a −4 dB la BER de 6,5e−03 deja a todas las tramas con al menos un bit erróneo.

### 5.4 Sincronización realista (Costas + Gardner)

El modelo anterior concedía al demodulador fase y temporización exactas. Para retirar ese privilegio se introduce un desfase de temporización reproducible de $0{,}35$ muestras (definido en `TIMING_OFFSET_SAMPLES`) en el canal, y el receptor lo recupera con dos lazos que no conocen los bits transmitidos:

- **Lazo de Costas de segundo orden** para la portadora: detector `signo(I)·Q` con ancho de banda de bucle de 80 Hz, implementado como PLL discreto con coeficientes deducidos de la frecuencia natural. Recupera la fase y la frecuencia residual sin necesitar una secuencia conocida.
- **Recuperación de temporización de Gardner** no asistida por decisión: compara las muestras temprana y tardía (separadas medio símbolo) con la muestra central y ajusta el instante de muestreo símbolo a símbolo, con interpolación lineal y avance limitado para estabilidad bajo ruido.

El costo es el esperado de quitar la sincronización ideal: a muy baja SNR los lazos pierden el enganche y la BER satura (deslizamientos de ciclo), de modo que la región útil del receptor empieza alrededor de −6 dB. El beneficio es doble: **se cuantifica el umbral de sincronización** de la cadena y **se elimina la sensibilidad al Doppler residual** de décimas de hercio que dominaba el modelo anterior (sección 5.2). La prueba automatizada `tests/test_sincronizacion.py` verifica que ambos lazos recuperan una BPSK RRC con desfase y Doppler residual sin errores.

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

`calcular_link_budget.py` modela el enlace descendente UHF a 437.568 MHz desde el CubeSat (LEO 775 km) hasta una estación terrena típica de radioaficionado.

<!-- TABLA:link_budget_parametros -->
| Parametro | Valor | Unidad |
|:---|---:|---:|
| Frecuencia | 437.568 | MHz |
| Tasa de datos | 9600 | bps |
| Altura orbital | 775 | km |
| Potencia TX (satelite) | 30.0 | dBm |
| Ganancia antena TX | 0.0 | dBi |
| Perdida cables TX | 0.5 | dB |
| Ganancia antena RX | 15.0 | dBi |
| Perdida cables RX | 2.0 | dB |
| Figura de ruido RX | 2.0 | dB |
| Temperatura de antena | 150.0 | K |
| Temperatura de sistema | 371.3 | K |
| Perdida atmosferica | 0.5 | dB |
| Perdida por polarizacion | 1.0 | dB |
| Perdida por apuntamiento | 1.0 | dB |
| Perdida de implementacion | 2.0 | dB |
| Eb/N0 requerida | 10.0 | dB |
| BER objetivo | 1e-05 | - |
<!-- /TABLA:link_budget_parametros -->

La temperatura de sistema se calcula refiriendo el ruido a la entrada del receptor:

$$T_{sys} = \frac{T_{ant}}{L} + \frac{L-1}{L}T_0 + T_{rx}$$

donde $L$ es la pérdida del cable entre la antena y el LNA. Los cables no solo atenúan la señal: aportan su propio ruido térmico y atenúan el de la antena. Con 2 dB de cable la diferencia frente a sumar simplemente $T_{ant} + T_{rx}$ es de 0,65 dB de margen.

<!-- TABLA:link_budget -->
| Elevacion (deg) | Distancia (km) | FSPL (dB) | C/N0 (dB-Hz) | Eb/N0 (dB) | Margen (dB) |
|:---|---:|---:|---:|---:|---:|
| 5 | 2728.6 | 153.99 | 58.91 | 19.09 | 7.09 |
| 15 | 1983.5 | 151.22 | 61.68 | 21.86 | 9.86 |
| 25 | 1517.6 | 148.89 | 64.01 | 24.19 | 12.19 |
| 30 | 1355.8 | 147.91 | 64.99 | 25.17 | 13.17 |
| 35 | 1227.3 | 147.05 | 65.85 | 26.03 | 14.03 |
| 45 | 1042.1 | 145.63 | 67.27 | 27.45 | 15.45 |
| 55 | 922.2 | 144.56 | 68.34 | 28.51 | 16.51 |
| 60 | 879.3 | 144.15 | 68.75 | 28.93 | 16.93 |
| 65 | 845.3 | 143.81 | 69.09 | 29.27 | 17.27 |
| 75 | 799.2 | 143.32 | 69.58 | 29.76 | 17.76 |
| 85 | 777.6 | 143.08 | 69.82 | 30.0 | 18.0 |
| 90 | 775.0 | 143.05 | 69.85 | 30.02 | 18.02 |
<!-- /TABLA:link_budget -->

El margen mínimo, **7,1 dB a 5° de elevación**, supera el margen recomendado de 3-6 dB para comunicaciones por satélite (Larson & Wertz), lo que confirma la viabilidad del enlace a 9600 bps incluso cerca del horizonte. En cenit el margen alcanza 18,0 dB.

### 7.2 Enlace ascendente

`simular_enlace_ascendente.py` modela el enlace de comandos a 1200 bps en 435 MHz, con 10 W de transmisión desde la estación terrena y antena isotrópica a bordo.

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

El uplink dispone de mucho más margen que el downlink (23,3 dB frente a 7,1 dB en el peor caso) por la combinación de mayor potencia transmitida (10 W frente a 1 W), antena directiva en el extremo transmisor y una tasa ocho veces menor. La columna de tasa máxima indica la velocidad que agotaría ese margen manteniendo la Eb/N0 requerida: entre 253 kbps y 3,1 Mbps. No es una capacidad de Shannon, sino la tasa límite del enlace con el esquema de modulación y el objetivo de BER fijados.

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
| C/N0 promedio | 66.8 dB-Hz |
| C/N0 minimo / maximo | 60.9 / 72.6 dB-Hz |
| Error de apuntamiento maximo | 0.77° |
| Perdida por apuntamiento maxima | 0.01 dB |
<!-- /TABLA:estacion_terrena -->

El hallazgo relevante es dinámico. En la culminación del paso el satélite exige una velocidad de barrido en azimut de **8,23 °/s**, mientras que el rotor modelado alcanza 5 °/s. Con la antena preposicionada en el punto de adquisición, la salida vigente del modelo conserva un error máximo fuera de boresight de **0,77°** y una pérdida máxima de **0,01 dB** con un haz de 30°. La conclusión práctica es que la Yagi modelada tolera el límite de velocidad; una antena más directiva debe evaluarse de nuevo con el cálculo del error angular verdadero y no con una resta directa de azimutes.

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
| CubeSat | Pais | Ano | Formato | Frecuencia (MHz) | Modulacion | Tasa (bps) |
|:---|---:|---:|---:|---:|---:|---:|
| STRaND-1 | Reino Unido | 2013 | 3U | 437.568 | BPSK | 9600 |
| Libertad 1 | Colombia | 2007 | 1U | 437.405 | AFSK | 1200 |
| FACSAT-1 | Colombia | 2018 | 3U | 437.375 | BPSK | 9600 |
| Delfi-C3 | Paises Bajos | 2008 | 3U | 145.870 | BPSK | 1200 |
| ESTCube-1 | Estonia | 2013 | 1U | 437.250 | BPSK | 9600 |
| AAUSAT-II | Dinamarca | 2008 | 1U | 437.425 | AFSK | 1200 |
| ITUPSAT 1 | Turquia | 2009 | 1U | 437.325 | BPSK | 9600 |
<!-- /TABLA:cubesats -->

### 9.2 Concordancia por parámetro

<!-- TABLA:concordancia -->
| Parametro | Valor simulado | Referencia real | Concordancia |
|:---|:---|:---|:---|
| Frecuencia de operacion | 437.568 MHz (UHF) | STRaND-1: 437.568 MHz | Alta |
| Modulacion | BPSK y FSK | STRaND-1: BPSK | Alta |
| Tasa de simbolos (baudios) | 9600 bps | STRaND-1: 9600 bps | Alta |
| Potencia de transmision | 1 W (30 dBm) | STRaND-1: 1 W | Alta |
| BER vs SNR - BPSK | BER ~5.3e-05 a SNR=0 dB<br>BER ~0 a SNR >= 2 dB (con 18776 bits) | BPSK teorica: BER ~3.9e-4 a Eb/N0=4 dB | Esperada dentro del modelo |
| Margen de enlace (link budget) | 7.1 dB a elev=5 deg<br>18.0 dB a elev=90 deg | Margen tipico requerido: 3-6 dB | Alta |
| Ancho de banda estimado | BPSK rectangular: ~27.0 kHz (-20 dB)<br>FSK: ~11.8 kHz (-20 dB)<br>BPSK + RRC (α=0.35): ~11.2 kHz (99 % ocupado) | BPSK 9600 bps: ancho de banda nulo ~19.2 kHz | Alta con conformado de pulso |
<!-- /TABLA:concordancia -->

La concordancia es alta en los siete parámetros evaluados. El ancho de banda, que en versiones anteriores del modelo quedaba en concordancia moderada por el uso de pulsos rectangulares, converge al valor teórico $R_b(1+\alpha)$ una vez incorporado el conformado RRC.

### 9.3 Comparación de protocolos

La elección de esquema de modulación y de protocolo de enlace condiciona el presupuesto de potencia, el ancho de banda ocupado y la complejidad del receptor. La comparación sitúa las decisiones de STRaND-1 en su contexto.

**Capa física:**

| Esquema | Eficiencia espectral | Eb/N0 para BER 10⁻⁵ | Complejidad de receptor | Uso en CubeSats |
|:---|:---|:---|:---|:---|
| BPSK | 1 bit/símbolo | ~9,6 dB (coherente) | Alta: recuperación de portadora | Muy extendido a 9600 bps |
| FSK | 1 bit/símbolo | ~13,4 dB (no coherente) | Baja: detección de energía | Extendido a 1200–9600 bps |
| GFSK | 1 bit/símbolo | ~12,5 dB | Baja-media | Habitual en transceptores comerciales |
| GMSK | 1 bit/símbolo | ~9,6 dB | Media-alta | AX.25 a 9600 bps |

Los resultados de la sección 4 cuantifican esa diferencia sobre el mismo flujo de bits reales: BPSK alcanza BER nula desde 2 dB de SNR por muestra y FSK necesita 8 dB. BPSK y GMSK comparten eficiencia en potencia, pero GMSK añade envolvente constante, lo que permite saturar el amplificador —una ventaja apreciable con el presupuesto de energía de un 3U—. La contrapartida de BPSK es espectral, y el conformado RRC la resuelve: baja de 66,1 kHz a 11,2 kHz, por debajo del ancho de banda de FSK.

**Capa de enlace y aplicación:**

| Protocolo | Ámbito | Overhead | Detección de errores | Adecuación |
|:---|:---|:---|:---|:---|
| AX.25 | Enlace, radioaficionado | 16+ B por trama | FCS CRC-16/X-25 | Estándar de facto universitario; ineficiente en tramas cortas |
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

1. **BPSK supera a FSK** en el canal AWGN evaluado, consistente con la teoría de modulaciones binarias.
2. **El conformado RRC reduce el ancho de banda ocupado en un factor de 5,9 sin coste en BER**, llevando la señal dentro de la canalización UHF de 25 kHz.
3. **El código convolucional aporta ~4 dB de ganancia** en cuanto la sincronización sostiene el enlace (a −2 dB reduce la BER 29 veces), y exhibe el umbral característico del decodificador Viterbi de decisión dura cuando la tasa de error de entrada supera su capacidad de corrección.
4. **El lazo de Costas recupera el error residual de Doppler de décimas de hercio**: la sensibilidad extrema al residual que mostraba el modelo de sincronización ideal desaparece, y el límite operativo pasa a ser el umbral de sincronización (deslizamientos de ciclo por debajo de ~−6 dB).
5. **El enlace descendente UHF a 9600 bps es viable** con margen mínimo de 7,1 dB a 5° de elevación.
6. **El límite de velocidad del rotor de azimut es tolerable** con antenas de haz ancho: 0,09 dB de pérdida en el peor instante de un paso casi cenital.
7. **Se decodificó telemetría real de STRaND-1 con la especificación de AMSAT-UK**: 32 754 balizas y 53 magnitudes, de las que 42 varían. Los magnetómetros están operativos (más de doscientos valores distintos por eje) y la batería fue medida de verdad entre 2016 y 2020, con el voltaje oscilando entre **6,31 y 8,94 V** como corresponde a ciclos de carga y descarga en órbita. El decodificador oficial de `satnogs-decoders` no sirve para este fin: lee un solo byte por canal y devuelve el campo `DATA_SIZE` en lugar de la medida.
8. **El estado de calidad que asigna SatNOGS y el análisis de bytes de este trabajo coinciden**, obtenidos por caminos independientes: el 95,2 % de los frames de observaciones `good` son balizas reconocibles, frente al 0,2 % de las `bad`. Que las anomalías del satélite —reloj del OBC degradándose, cuentas ADC del EPS a cero— aparezcan precisamente en las balizas de observaciones `good` descarta que sean un defecto de recepción.
9. **La telemetría fecha el fallo del subsistema de energía en febrero de 2021, tras tres meses de degradación.** El archivo histórico de SatNOGS DB no contiene ni una sola cuenta ADC a cero en las 753 lecturas de 2016 a octubre de 2020. La primera aparece el **27 de noviembre de 2020**, y durante tres meses el fallo es intermitente: 101 ceros en 5674 lecturas (1,8 %), repartidos por igual entre los ocho canales. La última lectura válida es del **31 de enero de 2021 a las 23:57:52 UTC**; desde el 24 de febrero de 2021 son cero las 8501 lecturas siguientes, sin una sola excepción, durante veinticuatro meses. En paralelo, el reloj del OBC pasa de sostener 3043 s entre reinicios en 2019 a quedarse fijo en 2 s en enero de 2023, cuando las balizas cesan pese a que las observaciones continúan hasta julio de 2026. El único subsistema coherente hasta el final fue el magnetómetro.
10. **El eslabón débil de la cadena no está en la radio, sino en la interpretación.** El enlace tiene 7,1 dB de margen en el peor caso, las estaciones reciben correctamente el 95,2 % de las balizas en observaciones buenas y el formato está publicado desde 2013; aun así la telemetría llevaba años sin interpretarse porque la implementación de referencia leía mal un campo del paquete.
11. **Una magnitud constante puede ser un canal muerto disfrazado de sistema sano.** Los 9,75 V de batería que STRaND-1 emitió durante sus dos últimos años no son una medida: son la ordenada al origen de la recta de calibración de AMSAT-UK, el valor que la ecuación devuelve cuando la cuenta ADC vale 0. Como las rectas son decrecientes, una cuenta nula no produce «cero» sino el extremo superior de la escala. Detectarlo exigió comparar con el archivo histórico; sin él, la lectura natural del dato habría sido «batería estable a 9,75 V».
12. **Una sola trama no demuestra el estado de un canal.** Durante el trabajo se tomó una baliza de 2018 con cuenta ADC 1023 como prueba de que los convertidores funcionaban. No lo era: es una única lectura, 1023 es el tope de escala de un convertidor de 10 bits —el valor de riel— y cae fuera del rango que ese canal recorre en todos los demás años. El diagnóstico solo se sostiene sobre la dispersión de muestras suficientes, no sobre ejemplares escogidos.

### 12.2 Limitaciones del modelo

- **Sincronización con umbral operativo:** la recuperación de portadora y temporización es real (Costas + Gardner, sección 5.4), pero por debajo de ~−6 dB los lazos pierden el enganche y la BER deja de ser interpretable como error de canal. Un receptor de vuelo añadiría una secuencia de adquisición (preámbulo) para bajar ese umbral; aquí el demodulador parte directamente de los datos.
- **Sincronización de trama ideal:** el verificador de AX.25 comprueba el FCS sobre bytes recibidos reales, pero localiza las tramas por desplazamiento conocido; no hay búsqueda de banderas ni *bit stuffing*.
- **FEC limitado a código convolucional:** no se implementaron LDPC ni turbo códigos, ni decisión blanda en el Viterbi.
- **Canal sin multitrayecto completo:** se modelan Rice y Doppler, pero no reflexiones múltiples ni despolarización por rotación de Faraday.
- **Modelo orbital por barrido genérico con órbita circular:** los barridos de elevación (link budget, estación terrena) siguen usando órbita circular y Tierra esférica. El propagador SGP4 con TLE reales (sección 8.1) se usa para pasos concretos, no para los barridos.
- **Amplificador ideal:** no se modelan compresión AM-AM, AM-PM ni distorsión armónica del PA.
- **FSK con tonos no ortogonales** para el detector de energía empleado ($\Delta f\cdot T = 0{,}5$), lo que penaliza su curva frente a la teórica.
- **Un solo satélite:** los resultados corresponden a STRaND-1; generalizar requiere verificación independiente.

### 12.3 Trabajo futuro

1. Bajar el umbral de sincronización con una secuencia de adquisición (preámbulo) y cuantificar su efecto sobre la región de trabajo del receptor.
2. Incorporar decisión blanda en el decodificador Viterbi (≈2 dB adicionales) y evaluar LDPC.
3. Implementar el decodificador AX.25 completo con búsqueda de banderas y *bit stuffing*.
4. Sustituir la captura de referencia sintetizada (sección 8.2) por una captura IQ real de un SDR sobre un paso de STRaND-1, conservando el manifiesto definido y completando la validación BER contra la secuencia de bits de referencia.

---

## 13. Conclusiones

1. Se caracterizó el subsistema de comunicaciones del CubeSat STRaND-1 en sus cuatro componentes: antena (monopolo λ/4, 0 dBi, UHF), transceptor (1 W a 437.568 MHz), módem (BPSK coherente y FSK a 9600 bps) y TT&C (balizas de 15,0 bytes de media, con la estructura HDLC que define la especificación de AMSAT-UK).

2. El modelo en banda base reproduce los resultados esperados de la teoría de comunicaciones digitales, y la coincidencia entre el modelo básico y el avanzado en la región de SNR común valida ambas implementaciones de forma cruzada.

3. El modelo avanzado demuestra tres efectos cuantificados: reducción de ancho de banda de 5,9× por conformado RRC sin coste en BER, ~4 dB de ganancia por codificación convolucional con su umbral de Viterbi, y una tolerancia al Doppler residual de décimas de hercio que justifica la necesidad de recuperación de portadora.

4. El link budget descendente muestra un margen mínimo de 7,1 dB a 5° de elevación y el ascendente de 23,3 dB, ambos por encima de los 3-6 dB recomendados por la literatura.

5. El modelo de estación terrena sobre un paso completo de 15,0 minutos, con 12,4 minutos útiles sobre 5°, muestra que el límite de velocidad del rotor en azimut se evalúa contra una traza de círculo máximo y una antena de 30° de haz. Los valores vigentes —incluida la pérdida máxima de 0,01 dB— se regeneran desde `modelo_estacion_terrena.py` y `resultados_simulacion/estacion_terrena_seguimiento.json`.

6. La comparación con 7 CubeSats reales muestra concordancia alta en los siete parámetros evaluados.

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
16. Álvarez, R., & Restrepo, C. (2020). Desarrollo de tecnología espacial en Colombia: retos y perspectivas para la ingeniería nacional. *Revista Colombiana de Tecnología Avanzada*, 1(35), 1–10.
17. Gómez, J. A., & Llano, G. (2018). Introducción al diseño de sistemas de comunicación para pequeños satélites. *Ingeniería y Ciencia*, 14(27), 123–148.

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
