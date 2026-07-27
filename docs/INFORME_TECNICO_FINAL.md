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

Este informe documenta el desarrollo de un modelo reproducible para la caracterización del subsistema electrónico de comunicaciones de un CubeSat, usando como referencia el satélite STRaND-1 (NORAD 39090). El trabajo integra: (1) procesamiento de telemetría real descargada de SatNOGS, (2) simulación de enlace RF en banda base para modulaciones BPSK y FSK bajo canal AWGN, (3) un modelo avanzado que añade conformado de pulso RRC, desvanecimiento Rice, error residual de Doppler, codificación convolucional con decodificación Viterbi y tramas AX.25 verificadas por FCS, (4) flujogramas en GNU Radio para visualización IQ y demodulación, (5) cálculo de link budget descendente y ascendente en UHF, (6) un modelo de estación terrena con seguimiento automático sobre un paso orbital completo, y (7) comparación con parámetros documentados de 7 CubeSats reales. Todos los scripts y flujogramas se desarrollan con herramientas de software libre.

---

## 1. Introducción

Los CubeSats se han consolidado como plataformas accesibles para misiones espaciales universitarias, pero el diseño de su subsistema de comunicaciones sigue siendo un desafío técnico que requiere validación mediante simulación antes de la implementación física. Este proyecto aborda la necesidad de contar con documentación técnica en español que describa, simule y caracterice cada componente del enlace de comunicaciones de un CubeSat, tomando como caso de estudio el satélite STRaND-1 y utilizando exclusivamente herramientas de software libre.

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

Se utilizó la API pública de SatNOGS para descargar 100 frames de telemetría del satélite STRaND-1 (NORAD 39090). El script `load_data.py` realiza la consulta y almacena los resultados en `frames_STRAND1.csv` con los campos: timestamp, estación observadora y payload en hexadecimal.

### 3.2 Decodificación de frames

| Estadística | Valor |
|------------|-------|
| Frames procesados | 100 |
| Bytes totales | 2347 |
| Bits totales evaluados | 18776 |
| Longitud promedio de frame | 23.5 bytes |
| Entropía promedio del payload | 4.049 bits/byte |
| Rango temporal | 2025-04-24 a 2026-05-06 |

### 3.3 Interpretación de la entropía

La entropía promedio de 4.049 bits/byte indica que los frames contienen una mezcla de datos estructurados (campos de cabecera, checksum) con baja entropía y datos de telemetría numérica con entropía moderada. Este valor es consistente con tramas AX.25 típicas que contienen identificadores fijos y datos de sensores variables.

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

`simular_enlace_rf_bpsk_avanzado.py` añade, como etapas componibles sobre la misma cadena, conformado de pulso RRC ($\alpha = 0{,}35$), desvanecimiento Rice con perfil Jakes ($K = 10$ dB), error residual de Doppler, codificación convolucional $r=1/2$, $K=7$ con decodificación Viterbi, y construcción y verificación de tramas AX.25. Se evalúan 18 configuraciones en 8 puntos de SNR (144 corridas).

El barrido de SNR de este modelo (−10 a 4 dB) es más bajo que el del modelo básico porque con el conformado de pulso correcto el enlace deja de cometer errores a partir de 0 dB, y la ganancia del código solo se aprecia por debajo de −2 dB. Los cuatro puntos superiores solapan con el modelo básico y permiten verificar que ambos coinciden.

### 5.1 Resultados principales

<!-- TABLA:avanzado_principal -->
| Configuracion | BER a -8 dB | BER a -6 dB | BER a -4 dB | BER a -2 dB | Ancho de banda (99 %) |
|:---|---:|---:|---:|---:|---:|
| BPSK rectangular (NRZ) | 5.28e-02 | 2.43e-02 | 6.02e-03 | 7.46e-04 | 66.1 kHz |
| BPSK + RRC (α=0.35) | 5.66e-02 | 2.28e-02 | 6.55e-03 | 6.39e-04 | 11.2 kHz |
| BPSK rectangular (NRZ) + fading Rice | 6.77e-02 | 2.94e-02 | 1.12e-02 | 2.66e-03 | 66.1 kHz |
| BPSK + FEC conv. (r=1/2, K=7) | 3.78e-03 | 2.13e-04 | 0 (sin errores) | 0 (sin errores) | 66.0 kHz |
<!-- /TABLA:avanzado_principal -->

**Conformado RRC.** La BER con RRC es estadísticamente indistinguible de la del pulso rectangular, pero el ancho de banda ocupado al 99 % baja de ~66 kHz a ~11 kHz, un factor de 5,9. Es el resultado esperado: el filtro adaptado conserva la relación señal-ruido en el instante de decisión y solo reordena la energía en el tiempo. El valor medido se acerca al límite teórico $R_b(1+\alpha) = 12{,}96$ kHz, y sitúa la señal cómodamente dentro de la canalización UHF de 25 kHz.

**Desvanecimiento Rice.** Con $K = 10$ dB la componente de línea de vista domina y la penalización es de aproximadamente 1 dB, coherente con un enlace LEO-tierra en visión directa sin obstrucciones.

**Codificación convolucional.** El código aporta unos 4 dB de ganancia de codificación en la región de BER $10^{-3}$. Por debajo de −8 dB de SNR el decodificador cruza su umbral y empeora respecto al enlace sin codificar (BER 1,19e−01 frente a 1,04e−01 a −10 dB): es el comportamiento clásico de un decodificador Viterbi de decisión dura cuando la tasa de error de entrada supera su capacidad de corrección.

### 5.2 Sensibilidad al error residual de Doppler

El desplazamiento Doppler para una órbita LEO a 437 MHz alcanza ±150 Hz (±10 kHz sobre la portadora real; aquí se modela el residuo en banda base). La estación terrena lo pre-compensa a partir de la predicción TLE, de modo que lo que llega al demodulador no es el Doppler completo sino el **error de esa predicción**. La tabla recoge esa sensibilidad:

<!-- TABLA:doppler_residual -->
| Residual de Doppler | BER a -8 dB | BER a -4 dB | BER a 0 dB | BER a 4 dB |
|:---|---:|---:|---:|---:|
| 0 Hz | 5.28e-02 | 6.02e-03 | 0 (sin errores) | 0 (sin errores) |
| 0.05 Hz | 6.58e-02 | 1.03e-02 | 2.66e-04 | 0 (sin errores) |
| 0.1 Hz | 1.22e-01 | 4.33e-02 | 9.11e-03 | 5.86e-04 |
| 0.2 Hz | 3.88e-01 | 3.65e-01 | 3.59e-01 | 3.61e-01 |
<!-- /TABLA:doppler_residual -->

El resultado es exigente y merece destacarse: sobre un registro de 1,96 s (los 18 776 bits a 9600 bps), un residual de solo 0,2 Hz introduce un piso de error irreducible en torno a 3,6e−01. La causa es que el modelo no incorpora recuperación de portadora: la fase acumulada $2\pi f_{res} T$ gira sin corrección durante todo el registro, y basta con que supere $\pi/2$ para que las decisiones se inviertan. **Esta es la justificación cuantitativa de por qué un receptor real necesita un lazo de Costas**, y es la primera recomendación de trabajo futuro.

### 5.3 Tramas AX.25

Las tramas se construyen conforme a AX.25 2.2: campo de dirección de 7 bytes por indicativo con los caracteres desplazados un bit y el bit de fin de dirección en el último byte, control UI (0x03), PID 0xF0 y FCS CRC-16/X-25 (polinomio 0x1021 reflejado, inicialización 0xFFFF, salida complementada, byte bajo primero). El FCS cubre únicamente los campos entre banderas, como exige la norma. La telemetría se reparte en 37 tramas de hasta 64 bytes de información.

<!-- TABLA:ax25 -->
| SNR (dB) | BER | Tramas validas por FCS (de 37) |
|:---|---:|---:|
| -10 | 1.04e-01 | 0 |
| -8 | 5.75e-02 | 0 |
| -6 | 2.34e-02 | 0 |
| -4 | 6.44e-03 | 1 |
| -2 | 1.17e-03 | 15 |
| 0 | 0 (sin errores) | 37 |
| 2 | 0 (sin errores) | 37 |
| 4 | 0 (sin errores) | 37 |
<!-- /TABLA:ax25 -->

La verificación es un cálculo real del FCS sobre los bytes recibidos, no una comparación con la trama transmitida. La transición es abrupta —de 1 trama válida a −4 dB a las 37 a 0 dB— porque el FCS es una comprobación de todo o nada: un solo bit erróneo invalida la trama completa. Con tramas de 40 a 104 bytes, una BER de $10^{-3}$ ya corrompe la mayoría.

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

- No hay recuperación de portadora ni sincronización de símbolo: se asume temporización y fase ideales.
- El bloque `Integrate` asume alineación perfecta de los límites de símbolo con la ventana de integración.
- Los archivos `.py` versionados contienen un ajuste manual (`import gnuradio.qtgui` en lugar de `import gnuradio`) necesario para que se ejecuten fuera de GRC. Al regenerarlos desde el `.grc` hay que reaplicarlo.

---

## 7. Link budget

### 7.1 Enlace descendente

`calcular_link_budget.py` modela el enlace descendente UHF a 437.568 MHz desde el CubeSat (LEO 600 km) hasta una estación terrena típica de radioaficionado.

<!-- TABLA:link_budget_parametros -->
| Parametro | Valor | Unidad |
|:---|---:|---:|
| Frecuencia | 437.568 | MHz |
| Tasa de datos | 9600 | bps |
| Altura orbital | 600 | km |
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
| 5 | 2328.0 | 152.61 | 60.29 | 20.47 | 8.47 |
| 15 | 1625.8 | 149.49 | 63.41 | 23.59 | 11.59 |
| 25 | 1213.2 | 146.95 | 65.95 | 26.13 | 14.13 |
| 30 | 1075.1 | 145.9 | 67.0 | 27.18 | 15.18 |
| 35 | 967.3 | 144.98 | 67.92 | 28.1 | 16.1 |
| 45 | 814.8 | 143.49 | 69.41 | 29.59 | 17.59 |
| 55 | 717.6 | 142.39 | 70.52 | 30.69 | 18.69 |
| 60 | 683.2 | 141.96 | 70.94 | 31.12 | 19.12 |
| 65 | 655.9 | 141.61 | 71.3 | 31.47 | 19.47 |
| 75 | 619.3 | 141.11 | 71.8 | 31.97 | 19.97 |
| 85 | 602.1 | 140.86 | 72.04 | 32.22 | 20.22 |
| 90 | 600.0 | 140.83 | 72.07 | 32.25 | 20.25 |
<!-- /TABLA:link_budget -->

El margen mínimo, **8,5 dB a 5° de elevación**, supera el margen recomendado de 3-6 dB para comunicaciones por satélite (Larson & Wertz), lo que confirma la viabilidad del enlace a 9600 bps incluso cerca del horizonte. En cenit el margen alcanza 20,3 dB.

### 7.2 Enlace ascendente

`simular_enlace_ascendente.py` modela el enlace de comandos a 1200 bps en 435 MHz, con 10 W de transmisión desde la estación terrena y antena isotrópica a bordo.

<!-- TABLA:uplink -->
| Elevacion (deg) | Distancia (km) | FSPL (dB) | C/N0 (dB-Hz) | Eb/N0 (dB) | Margen (dB) | Tasa max (kbps) |
|:---|---:|---:|---:|---:|---:|---:|
| 5 | 2328.0 | 152.56 | 67.42 | 36.63 | 24.63 | 348 |
| 15 | 1625.8 | 149.44 | 70.54 | 39.74 | 27.74 | 714 |
| 25 | 1213.2 | 146.90 | 73.08 | 42.29 | 30.29 | 1282 |
| 30 | 1075.1 | 145.85 | 74.13 | 43.34 | 31.34 | 1633 |
| 35 | 967.3 | 144.93 | 75.05 | 44.25 | 32.25 | 2017 |
| 45 | 814.8 | 143.44 | 76.54 | 45.74 | 33.74 | 2842 |
| 55 | 717.6 | 142.34 | 77.64 | 46.85 | 34.85 | 3664 |
| 60 | 683.2 | 141.91 | 78.07 | 47.28 | 35.28 | 4043 |
| 65 | 655.9 | 141.55 | 78.42 | 47.63 | 35.63 | 4386 |
| 75 | 619.3 | 141.06 | 78.92 | 48.13 | 36.13 | 4921 |
| 85 | 602.1 | 140.81 | 79.16 | 48.37 | 36.37 | 5205 |
| 90 | 600.0 | 140.78 | 79.19 | 48.40 | 36.40 | 5242 |
<!-- /TABLA:uplink -->

El uplink dispone de mucho más margen que el downlink (24,6 dB frente a 8,5 dB en el peor caso) por la combinación de mayor potencia transmitida (10 W frente a 1 W), antena directiva en el extremo transmisor y una tasa ocho veces menor. La columna de tasa máxima indica la velocidad que agotaría ese margen manteniendo la Eb/N0 requerida: entre 348 kbps y 5,2 Mbps. No es una capacidad de Shannon, sino la tasa límite del enlace con el esquema de modulación y el objetivo de BER fijados.

---

## 8. Modelo de estación terrena con seguimiento

`modelo_estacion_terrena.py` simula un paso orbital completo sobre una traza de círculo máximo. Para un desplazamiento a lo largo de la traza $u = \omega t$ medido desde la culminación, la trigonometría esférica da $\cos\gamma = \cos\gamma_{min}\cos u$, de donde se obtienen elevación, azimut y distancia oblicua exactas para órbita circular. La geometría procede de `geometria_orbital.py`, el mismo módulo que usan los dos scripts de link budget.

<!-- TABLA:estacion_terrena -->
| Magnitud | Valor |
|:---|:---|
| Duracion del paso (horizonte a horizonte) | 12.8 min |
| Duracion util (elevacion > 5°) | 10.4 min |
| Elevacion de culminacion | 85.0° |
| Distancia oblicua | 602 - 2326 km |
| Temperatura de sistema | 308 - 376 K |
| C/N0 promedio | 68.4 dB-Hz |
| C/N0 minimo / maximo | 62.2 / 74.8 dB-Hz |
| Error de apuntamiento maximo | 2.62° |
| Perdida por apuntamiento maxima | 0.09 dB |
<!-- /TABLA:estacion_terrena -->

El hallazgo relevante es dinámico. En la culminación del paso el satélite exige una velocidad de barrido en azimut de **8,23 °/s**, mientras que el rotor modelado alcanza 5 °/s. El resultado es un retraso de hasta 20° en azimut. Sin embargo, como ese retraso ocurre a 82,5° de elevación —donde un grado de azimut abarca mucho menos arco sobre el cielo—, el error real fuera de boresight es de solo 2,62°, que con un haz de 30° cuesta 0,09 dB. La conclusión práctica es que una Yagi de haz ancho tolera sin problema el límite de velocidad del rotor; una antena más directiva no lo haría, y ahí el cálculo del error angular verdadero (y no la resta directa de azimutes) resulta imprescindible.

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
| Margen de enlace (link budget) | 8.5 dB a elev=5 deg<br>20.2 dB a elev=90 deg | Margen tipico requerido: 3-6 dB | Alta |
| Ancho de banda estimado | BPSK rectangular: ~27.0 kHz (-20 dB)<br>FSK: ~11.8 kHz (-20 dB)<br>BPSK + RRC (α=0.35): ~11.2 kHz (99 % ocupado) | BPSK 9600 bps: ancho de banda nulo ~19.2 kHz | Alta con conformado de pulso |
<!-- /TABLA:concordancia -->

La concordancia es alta en los siete parámetros evaluados. El ancho de banda, que en versiones anteriores del modelo quedaba en concordancia moderada por el uso de pulsos rectangulares, converge al valor teórico $R_b(1+\alpha)$ una vez incorporado el conformado RRC.

---

## 10. Discusión

### 10.1 Hallazgos principales

1. **BPSK supera a FSK** en el canal AWGN evaluado, consistente con la teoría de modulaciones binarias.
2. **El conformado RRC reduce el ancho de banda ocupado en un factor de 5,9 sin coste en BER**, llevando la señal dentro de la canalización UHF de 25 kHz.
3. **El código convolucional aporta ~4 dB de ganancia** en la región de BER $10^{-3}$, y exhibe el umbral característico del decodificador Viterbi por debajo de −8 dB.
4. **La tolerancia al error residual de Doppler es de décimas de hercio** sin recuperación de portadora, lo que cuantifica la necesidad de un lazo de Costas en un receptor real.
5. **El enlace descendente UHF a 9600 bps es viable** con margen mínimo de 8,5 dB a 5° de elevación.
6. **El límite de velocidad del rotor de azimut es tolerable** con antenas de haz ancho: 0,09 dB de pérdida en el peor instante de un paso casi cenital.
7. **La telemetría real de STRaND-1** presenta entropía moderada (4,049 bits/byte), compatible con tramas que mezclan campos fijos y datos variables.

### 10.2 Limitaciones del modelo

- **Sincronización ideal:** no hay recuperación de portadora ni de temporización de símbolo. Es la limitación de mayor impacto y la que explica la sensibilidad extrema al Doppler residual de la sección 5.2.
- **Sincronización de trama ideal:** el verificador de AX.25 comprueba el FCS sobre bytes recibidos reales, pero localiza las tramas por desplazamiento conocido; no hay búsqueda de banderas ni *bit stuffing*.
- **FEC limitado a código convolucional:** no se implementaron LDPC ni turbo códigos, ni decisión blanda en el Viterbi.
- **Canal sin multitrayecto completo:** se modelan Rice y Doppler, pero no reflexiones múltiples ni despolarización por rotación de Faraday.
- **Modelo orbital simplificado:** órbita circular y Tierra esférica; no se usa un propagador SGP4 con TLE reales.
- **Amplificador ideal:** no se modelan compresión AM-AM, AM-PM ni distorsión armónica del PA.
- **FSK con tonos no ortogonales** para el detector de energía empleado ($\Delta f\cdot T = 0{,}5$), lo que penaliza su curva frente a la teórica.
- **Un solo satélite:** los resultados corresponden a STRaND-1; generalizar requiere verificación independiente.

### 10.3 Trabajo futuro

1. Implementar un lazo de Costas para recuperación de portadora y cuantificar la mejora en la tolerancia al Doppler residual.
2. Añadir sincronización de símbolo (Gardner o Mueller-Müller).
3. Incorporar decisión blanda en el decodificador Viterbi (≈2 dB adicionales) y evaluar LDPC.
4. Implementar el decodificador AX.25 completo con búsqueda de banderas y *bit stuffing*.
5. Sustituir la órbita circular por un propagador SGP4 alimentado con TLE reales de STRaND-1.
6. Validar el modelo contra capturas IQ reales de un SDR sobre un paso del satélite.

---

## 11. Conclusiones

1. Se caracterizó el subsistema de comunicaciones del CubeSat STRaND-1 en sus cuatro componentes: antena (monopolo λ/4, 0 dBi, UHF), transceptor (1 W a 437.568 MHz), módem (BPSK coherente y FSK a 9600 bps) y TT&C (tramas AX.25 con telemetría de 23,5 bytes promedio).

2. El modelo en banda base reproduce los resultados esperados de la teoría de comunicaciones digitales, y la coincidencia entre el modelo básico y el avanzado en la región de SNR común valida ambas implementaciones de forma cruzada.

3. El modelo avanzado demuestra tres efectos cuantificados: reducción de ancho de banda de 5,9× por conformado RRC sin coste en BER, ~4 dB de ganancia por codificación convolucional con su umbral de Viterbi, y una tolerancia al Doppler residual de décimas de hercio que justifica la necesidad de recuperación de portadora.

4. El link budget descendente muestra un margen mínimo de 8,5 dB a 5° de elevación y el ascendente de 24,6 dB, ambos por encima de los 3-6 dB recomendados por la literatura.

5. El modelo de estación terrena sobre un paso completo de 12,8 minutos muestra que el límite de velocidad del rotor en azimut, aun siendo insuficiente en la culminación (8,23 °/s requeridos frente a 5 °/s disponibles), solo cuesta 0,09 dB con una antena de 30° de haz.

6. La comparación con 7 CubeSats reales muestra concordancia alta en los siete parámetros evaluados.

7. Todos los scripts y flujogramas se desarrollaron con software libre y las tablas de este informe se generan automáticamente desde los datos, lo que hace el trabajo reproducible y auditable.

---

## 12. Referencias

1. Bouwmeester, J., & Guo, J. (2010). Survey of worldwide pico- and nanosatellite missions, distributions and subsystem technology. *Acta Astronautica*, 67(7–8), 854–862.
2. Cal Poly SLO. (2022). *CubeSat Design Specification (CDS) Rev. 14*. California Polytechnic State University.
3. Fortescue, P., Swinerd, G., & Stark, J. (2011). *Spacecraft systems engineering* (4th ed.). John Wiley & Sons.
4. Larson, W. J., & Wertz, J. R. (Eds.). (1999). *Space mission analysis and design* (3rd ed.). Microcosm Press.
5. Maral, G., Bousquet, M., & Sun, Z. (2020). *Satellite communications systems* (6th ed.). John Wiley & Sons.
6. Pratt, T., Bostian, C., & Allnutt, J. (2003). *Satellite communications* (2nd ed.). John Wiley & Sons.
7. Proakis, J. G., & Salehi, M. (2008). *Digital communications* (5th ed.). McGraw-Hill.
8. Sklar, B. (2001). *Digital communications: Fundamentals and applications* (2nd ed.). Prentice Hall.
9. TAPR / ARRL. (1998). *AX.25 Link Access Protocol for Amateur Packet Radio, Version 2.2*.
10. UIT-R. (2012). *Recomendación SM.328-11: Espectros y anchuras de banda de las emisiones*.
11. GNU Radio Project. (2024). *GNU Radio Manual and C++ API Reference*.
12. SatNOGS. (2026). *SatNOGS DB — STRaND-1 telemetry data*. https://db.satnogs.org/
13. ISIS — Innovative Solutions in Space. *TRXUV Transceiver datasheet*.
14. GomSpace. *NanoCom TRX Transceiver datasheet*.
15. Álvarez, R., & Restrepo, C. (2020). Desarrollo de tecnología espacial en Colombia: retos y perspectivas para la ingeniería nacional. *Revista Colombiana de Tecnología Avanzada*, 1(35), 1–10.
16. Gómez, J. A., & Llano, G. (2018). Introducción al diseño de sistemas de comunicación para pequeños satélites. *Ingeniería y Ciencia*, 14(27), 123–148.

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
├── generar_tablas_informe.py             # Regenera las tablas de este informe
├── simulacion_visualizar_iq.grc / .py    # GNU Radio: visualizacion IQ
├── simulacion_cadena_completa.grc / .py  # GNU Radio: cadena BPSK completa
├── frames_STRAND1.csv / .json            # Telemetria descargada
├── resumen_telemetria_STRAND1.json
├── frames_STRAND1_gnuradio.bin
├── docs/
│   ├── DISENO_MODELO_SIMULACION_ENLACE_RF.md
│   ├── CARACTERIZACION_COMPONENTES_COMMS.md
│   └── INFORME_TECNICO_FINAL.md
└── resultados_simulacion/
    ├── configuracion_modelo_rf.json
    ├── resultados_ber_fsk_bpsk.csv / curva_ber_fsk_bpsk.png
    ├── strand1_bpsk_iq_clean_complex64.bin / strand1_fsk_iq_clean_complex64.bin
    ├── resultados_simulacion_avanzada.csv / .json
    ├── simulacion_avanzada_resultados.png / espectro_rrc_comparacion.png
    ├── link_budget_resultados.csv / link_budget_completo.json / link_budget_margen_enlace.png
    ├── enlace_ascendente_resultados.json / .png
    ├── estacion_terrena_seguimiento.json / .png
    ├── comparacion_ber_teorica_vs_simulada.png
    ├── comparacion_parametros_cubesats_reales.csv / .json
    └── cubesats_reales_referencia.csv / .json
```

---

*Documento generado como parte del proyecto aplicado de Ingeniería Electrónica — UNAD, 2026.*
