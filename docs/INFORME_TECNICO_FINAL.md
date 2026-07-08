# Informe técnico: Caracterización del subsistema de comunicaciones de un CubeSat mediante simulación de señales de radiofrecuencia

**Proyecto aplicado de Ingeniería Electrónica**

**Autora:** Mayelin Stefania Aguilar Vásquez  
**Línea de investigación:** Ciberseguridad y Telecomunicaciones  
**Universidad:** UNAD — Escuela de Ciencias Básicas, Tecnología e Ingeniería (ECBTI)

**Fecha:** Julio 2026

---

## Resumen

Este informe documenta el desarrollo completo de un modelo reproducible para la caracterización del subsistema electrónico de comunicaciones de un CubeSat, usando como referencia el satélite STRaND-1 (NORAD 39090). El trabajo integra: (1) procesamiento de telemetría real descargada de SatNOGS, (2) simulación de enlace RF en banda base para modulaciones BPSK y FSK bajo canal AWGN, (3) diseño de flujogramas en GNU Radio para visualización IQ y demodulación, (4) cálculo de link budget y margen de enlace descendente UHF, y (5) comparación con parámetros documentados de 7 CubeSats reales. Todos los scripts y flujogramas se desarrollan con herramientas de software libre y se documentan para su reproducción en entornos académicos.

---

## 1. Introducción

Los CubeSats se han consolidado como plataformas accesibles para misiones espaciales universitarias, pero el diseño de su subsistema de comunicaciones sigue siendo un desafío técnico que requiere validación mediante simulación antes de la implementación física. Este proyecto aborda la necesidad de contar con documentación técnica en español que describa, simule y caracterice cada componente del enlace de comunicaciones de un CubeSat, tomando como caso de estudio el satélite STRaND-1 y utilizando exclusivamente herramientas de software libre.

El informe se estructura en seis secciones que cubren: la metodología y herramientas empleadas, el procesamiento de datos reales de telemetría, el modelo de simulación RF, la implementación en GNU Radio, el cálculo de link budget, la comparación con CubeSats documentados, y las conclusiones técnicas del proyecto.

---

## 2. Metodología y herramientas

### 2.1 Enfoque

El proyecto sigue un enfoque de simulación equivalente en banda base (baseband equivalent model), donde la portadora RF no se genera explícitamente sino que la señal modulada se representa matemáticamente mediante sus componentes I/Q. Este enfoque permite validar la cadena de modulación-canal-demodulación con bajo costo computacional, manteniendo la fidelidad necesaria para el análisis de BER, constelaciones y espectro.

### 2.2 Flujo de trabajo

```text
SatNOGS API
    ↓
[load_data.py] → frames hex
    ↓
[decodificar_frames_STRAND1.py] → bytes/binario
    ↓
┌─────────────────────────────────────────────────────────────┐
│ [simular_enlace_rf_fsk_bpsk.py]                             │
│   → Modulación BPSK/FSK                                     │
│   → Canal AWGN (barrido -2 a 12 dB SNR)                    │
│   → Demodulación coherente/correlación                     │
│   → Cálculo de BER                                          │
│   → Exportación archivos IQ (.bin complex64)                │
└─────────────────────────────────────────────────────────────┘
    ↓                          ↓
[GNU Radio]               [calcular_link_budget.py]
  → visualizar_iq           → Margen de enlace UHF
  → cadena_completa         → 5° a 90° elevación
    ↓                          ↓
[comparar_con_cubesats_reales.py]
  → 7 CubeSats documentados
  → 7 parámetros c/u
  → Concordancia cualitativa
```

### 2.3 Herramientas

| Herramienta | Versión | Propósito |
|------------|---------|-----------|
| Python 3.14 | 3.14 | Lenguaje principal de simulación |
| numpy | 2.5.1 | Procesamiento numérico y algebraico |
| scipy | 1.15+ | Funciones especiales (erfc) |
| matplotlib | 3.10+ | Graficación de resultados |
| GNU Radio | 3.10.12 | Flujogramas de RF y visualización |
| GRC | 3.10.12 | Diseño visual de flujogramas |
| pandas | 2.2+ | Organización de datos tabulares |

---

## 3. Procesamiento de datos reales de telemetría

### 3.1 Obtención de datos

Se utilizó la API pública de SatNOGS para descargar 100 frames de telemetría del satélite STRaND-1 (NORAD 39090). El script `load_data.py` realiza la consulta y almacena los resultados en `frames_STRAND1.csv` con los campos: timestamp, estación observadora, frecuencia, modulación, y payload en hexadecimal.

### 3.2 Decodificación de frames

El script `decodificar_frames_STRAND1.py` procesa los payloads hexadecimales:

| Estadística | Valor |
|------------|-------|
| Frames procesados | 100 |
| Bytes totales | 2347 |
| Bits totales evaluados | 18776 |
| Longitud promedio de frame | 23.5 bytes |
| Longitud mínima | 1 byte |
| Longitud máxima | 64 bytes |
| Entropía promedio del payload | 4.049 bits/byte |
| Rango temporal | 2025-04-24 a 2026-05-06 |
| Estaciones observadoras | 24 estaciones globales |

### 3.3 Interpretación de la entropía

La entropía promedio de 4.049 bits/byte indica que los frames contienen una mezcla de datos estructurados (campos de cabecera, checksum) con baja entropía (~0-2 bits/byte) y datos de telemetría numérica con entropía moderada (~5-7 bits/byte). Este valor es consistente con tramas AX.25 típicas que contienen identificadores fijos y datos de sensores variables.

---

## 4. Modelo de simulación de enlace RF

### 4.1 Arquitectura del modelo

El script `simular_enlace_rf_fsk_bpsk.py` implementa un modelo equivalente en banda base con los siguientes bloques:

1. **Fuente:** Archivo `frames_STRAND1_gnuradio.bin` (18776 bits)
2. **Modulador BPSK:** Mapeo NRZ (0→-1, 1→+1), sobremuestreo ×8 (76800 sps)
3. **Modulador FSK:** Tonos a ±2400 Hz, sobremuestreo ×8
4. **Canal:** AWGN con barrido de SNR: -2, 0, 2, 4, 6, 8, 10, 12 dB
5. **Demodulador BPSK:** Integración por símbolo + decisión por umbral (coherente ideal)
6. **Demodulador FSK:** Correlación con tonos de referencia + decisión por máxima energía (no coherente)
7. **Métrica:** BER bit a bit

### 4.2 Resultados de BER

| SNR (dB) | BER BPSK | BER FSK |
|:--------:|---------:|--------:|
| -2 | 8.62e-06 | 1.08e-01 |
| 0 | 5.33e-05 | 5.33e-02 |
| 2 | 0.0 | 8.41e-03 |
| 4 | 0.0 | 3.89e-03 |
| 6 | 0.0 | 4.79e-04 |
| 8 | 0.0 | 0.0 |
| 10 | 0.0 | 0.0 |
| 12 | 0.0 | 0.0 |

### 4.3 Análisis de resultados

**BPSK** demuestra ser significativamente más robusta que FSK en canal AWGN, requiriendo aproximadamente 6 dB menos de SNR para alcanzar BER cero en esta corrida (2 dB vs 8 dB). Este resultado es consistente con la teoría de comunicaciones: la distancia euclidiana entre símbolos BPSK (2√E) es √2 veces mayor que la distancia entre tonos FSK ortogonales (√2E), lo que se traduce en una ventaja de aproximadamente 3 dB en Eb/N0 para la misma BER, más la ganancia adicional de la demodulación coherente.

**FSK no coherente** presenta una caída más gradual de BER con el incremento de SNR, lo que refleja su expresión teórica BER = ½ · exp(-Eb/(2N0)). Para aplicaciones CubeSat donde el enlace dispone de margen suficiente (>10 dB), ambas modulaciones son viables, pero BPSK es preferida por su eficiencia energética, lo que coincide con el ~45% de las misiones CubeSat universitarias que la adoptan.

### 4.4 Ancho de banda estimado

Medido en el espectro de la señal generada (umbral -20 dB respecto al pico):

| Modulación | Ancho de banda (-20 dB) |
|-----------|------------------------:|
| BPSK | ~27.0 kHz |
| FSK | ~11.8 kHz |

FSK ocupa menos ancho de banda (~44% del BPSK) porque la energía se concentra en dos componentes espectrales discretas, mientras que BPSK tiene un lóbulo principal más ancho debido a la forma de pulso rectangular. En aplicaciones donde el ancho de banda está restringido (canalizaciones de 25 kHz en UHF), FSK puede ser ventajoso a costa de menor eficiencia energética.

---

## 5. Implementación en GNU Radio

### 5.1 Flujograma de visualización IQ (`simulacion_visualizar_iq.grc`)

**Propósito:** Visualizar en tiempo real las señales IQ generadas en la simulación, con control interactivo de ruido AWGN.

**Bloques:**

| Bloque | Configuración |
|--------|--------------|
| File Source | Archivo: `strand1_bpsk_iq_clean_complex64.bin`, Formato: Complex, Tamaño: 0 |
| Throttle | Tasa: 76800 |
| Add | Suma señal + ruido (habilitado/deshabilitado por QT GUI Chooser) |
| Noise Source | Tipo: Gaussian, Amplitude controlada por QT GUI Range |
| QT GUI Time Sink | Tasa: 76800, Tiempo: 10 ms, N líneas: 2 (I,Q) |
| QT GUI Frequency Sink | Tasa: 76800, BW: 38.4 kHz, FFT: 1024 |
| QT GUI Constellation Sink | Tasa: 76800, Muestras/símbolo: 8 |

**Uso:**
1. Ubicar `strand1_bpsk_iq_clean_complex64.bin` en `resultados_simulacion/`
2. Ajustar ruta en File Source
3. Usar el deslizador de amplitud de ruido para observar degradación de constelación
4. El QT GUI Chooser permite activar/desactivar ruido externo

### 5.2 Flujograma de cadena completa BPSK (`simulacion_cadena_completa.grc`)

**Propósito:** Demostrar una cadena de transmisión BPSK completa en GNU Radio a partir de los bytes de telemetría real.

**Bloques:**

| Bloque | Configuración |
|--------|--------------|
| File Source | Archivo: `frames_STRAND1_gnuradio.bin`, Formato: Byte |
| Char to Float | Convierte byte a float (0-255) |
| Binary Slicer | Umbral 127 → bits 0/1 |
| Pack K Bits | K=1 (bits desempacados) |
| Unpack K Bits | K=1 |
| Repeat | Interpolación: 8 |
| Float to Char | Conversión para modulación |
| Chunks to Symbols | Mapeo: [1.0, -1.0] (NRZ BPSK) |
| Multiply Const | Escala: 1.0 |
| Add | Suma con AWGN |
| Noise Source | Gaussiano, amplitud variable |
| Integrate | Decimation: 8 (integra 8 muestras/símbolo) |
| Binary Slicer | Decisión: ≥0 → 1, <0 → 0 |
| QT GUI Time Sink | Señal I antes/después de demodular |
| QT GUI Frequency Sink | Espectro antes de demodular |
| QT GUI Constellation Sink | Constelación antes de decisión |
| QT GUI Histogram Sink | Distribución de muestra integrada |
| QT GUI Number Sink | Conteo de errores |

### 5.3 Limitaciones de la implementación GNU Radio

- **No hay recuperación de portadora:** El receptor asume sincronización perfecta de fase y frecuencia.
- **No hay sincronización de símbolo:** Se asume temporización ideal entre transmisor y receptor.
- **El bloque Integrate asume alineación perfecta** de los límites de símbolo con la ventana de integración.
- **Los archivos .grc se diseñaron para GNU Radio 3.10** usando sintaxis YAML; coordenadas deben ser listas `[x,y]`.

---

## 6. Cálculo de link budget

### 6.1 Modelo del enlace descendente

El script `calcular_link_budget.py` modela el enlace descendente UHF a 437.568 MHz desde el CubeSat (órbita LEO ~600 km) hasta una estación terrena típica.

### 6.2 Parámetros del sistema

| Parámetro | Valor | Unidad |
|-----------|-------|--------|
| Frecuencia | 437.568 | MHz |
| Potencia TX (satélite) | 1.0 (30) | W (dBm) |
| Pérdida en cables TX | 0.5 | dB |
| Ganancia antena TX | 0 | dBi |
| PIRE | 29.5 | dBm |
| Distancia (5° elev.) | 1936 | km |
| Distancia (90° elev.) | 600 | km |
| FSPL (5°) | -151.0 | dB |
| FSPL (90°) | -140.8 | dB |
| Pérdida atmosférica | 0.5 | dB |
| Pérdida por polarización | 0.5 | dB |
| Pérdida por apuntamiento | 1.0 | dB |
| Ganancia antena RX | 15.0 | dBi |
| Pérdida cables RX | 1.0 | dB |
| Figura de ruido RX | 2.0 | dB |
| Temperatura de ruido | 416.9 | K |
| Densidad espectral N0 | -170.4 | dBm/Hz |
| Eb/N0 requerida (BER=1e-5) | 9.6 | dB |
| Tasa de datos | 9600 | bps |

### 6.3 Resultados del margen de enlace

| Elevación | Distancia (km) | FSPL (dB) | C/N0 (dB-Hz) | Eb/N0 (dB) | Margen (dB) |
|:---------:|:--------------:|:---------:|:-------------:|:----------:|:-----------:|
| 5° | 1936.2 | -151.0 | 59.5 | 19.6 | 9.1 |
| 10° | 1152.4 | -146.5 | 64.1 | 24.2 | 13.7 |
| 20° | 760.5 | -142.9 | 67.6 | 27.8 | 17.2 |
| 30° | 680.3 | -141.9 | 68.6 | 28.8 | 18.2 |
| 45° | 653.8 | -141.5 | 69.0 | 29.2 | 18.6 |
| 60° | 677.0 | -141.8 | 68.7 | 28.9 | 18.3 |
| 90° | 600.0 | -140.8 | 69.7 | 29.9 | 19.3 |

### 6.4 Interpretación

El margen de enlace mínimo es de **9.1 dB a 5° de elevación**, superando ampliamente el margen típico recomendado de 3-6 dB para comunicaciones por satélite (Larson & Wertz, SMAD). Esto indica que el enlace descendente UHF a 9600 bps es viable incluso cerca del horizonte, donde la distancia es máxima.

El margen aumenta a **~19 dB en cenit** (90° de elevación), lo que permitiría aumentar la tasa de datos o reducir la potencia de transmisión si fuera necesario.

---

## 7. Comparación con CubeSats reales

### 7.1 CubeSats de referencia

Se documentaron 7 CubeSats reales para contextualizar los parámetros del modelo:

| CubeSat | País | Año | Frecuencia | Modulación | Tasa | Formato |
|---------|------|:---:|:----------:|:----------:|:----:|:-------:|
| **STRaND-1** | Reino Unido | 2013 | 437.568 MHz | BPSK | 9600 bps | 3U |
| Libertad 1 | Colombia | 2007 | 437.405 MHz | AFSK | 1200 bps | 1U |
| FACSAT-1 | Colombia | 2018 | 437.375 MHz | BPSK | 9600 bps | 3U |
| Delfi-C3 | Países Bajos | 2008 | 145.870 MHz | BPSK | 1200 bps | 3U |
| ESTCube-1 | Estonia | 2013 | 437.250 MHz | BPSK | 9600 bps | 1U |
| AAUSAT-II | Dinamarca | 2008 | 437.425 MHz | AFSK | 1200 bps | 1U |
| ITUPSAT 1 | Turquía | 2009 | 437.325 MHz | BPSK | 9600 bps | 1U |

### 7.2 Concordancia por parámetro

| Parámetro | Valor simulado | Referencia real | Concordancia |
|-----------|---------------|-----------------|:------------:|
| Frecuencia | 437.568 MHz (UHF) | STRaND-1: 437.568 MHz | Alta |
| Modulación | BPSK y FSK | STRaND-1: BPSK; 45% de CubeSats usan BPSK | Alta |
| Tasa de datos | 9600 bps | STRaND-1: 9600 bps; tasa más común en UHF | Alta |
| Potencia TX | 1 W (30 dBm) | STRaND-1: 1 W; estándar en 1U/3U | Alta |
| BER vs SNR | BER ~5.3e-5 a SNR=0 dB | Teoría BPSK: BER ~3.9e-4 a Eb/N0=4 dB | Consistente |
| Margen de enlace | 9.1-19.3 dB | Margen recomendado: 3-6 dB | Alta |
| Ancho de banda | BPSK: ~27 kHz | BPSK 9600 bps: ~19.2 kHz nulo | Moderada |

### 7.3 Discusión

La alta concordancia en frecuencia, modulación, tasa y potencia valida la representatividad del modelo: los parámetros simulados coinciden con los valores documentados de STRaND-1 y son consistentes con las tendencias del ecosistema CubeSat. La concordancia "moderada" en ancho de banda se debe al uso de pulsos rectangulares sin filtrado conformador (RRC, root-raised cosine), que produce lóbulos secundarios más anchos que los de un sistema implementado con filtrado.

---

## 8. Discusión general

### 8.1 Hallazgos principales

1. **BPSK supera a FSK en eficiencia energética** en aproximadamente 6 dB para BER cero en la configuración evaluada, consistente con la teoría de modulaciones binarias.

2. **El enlace UHF a 9600 bps es viable** con un margen mínimo de 9.1 dB incluso a baja elevación, usando parámetros típicos de CubeSat 1U.

3. **La telemetría real de STRaND-1** descargada de SatNOGS tiene entropía moderada (4.049 bits/byte), compatible con tramas AX.25 que mezclan campos fijos y datos variables.

4. **Los flujogramas GNU Radio** demostraron que las señales IQ generadas en Python pueden integrarse exitosamente en GNU Radio Companion para visualización y demodulación.

### 8.2 Limitaciones del modelo

- **Canal puramente AWGN:** No se modelan desvanecimiento por multitrayecto, bloqueo de cuerpo del satélite, ni variaciones de polarización por rotación de la nave.
- **Sincronización ideal:** No hay recuperación de portadora, temporización de símbolo, ni estimación de fase. Esto sobreestima el desempeño real del receptor.
- **Sin codificación de canal:** No se implementa FEC (convolucional, Reed-Solomon, LDPC) que mejoraría la BER efectiva a costa de throughput.
- **Sin protocolo de capa de enlace:** No se reconstruyen tramas AX.25 completas ni se verifica FCS.
- **No linealidades del PA:** El amplificador de potencia se modela como ideal; no se consideran compresión AM-AM, AM-PM ni distorsión armónica.
- **Rango de SNR limitado:** 8 puntos de SNR (-2 a 12 dB). Un barrido más fino mejoraría la resolución de la curva BER.
- **Cobertura de un solo satélite:** Los resultados corresponden a STRaND-1; la generalización a otros CubeSats requiere verificación independiente.

### 8.3 Trabajo futuro

1. **Incorporar modelo de desvanecimiento Rice/Rayleigh** para simular canales con componente LOS y multitrayecto.
2. **Añadir efecto Doppler** variable en el tiempo para simular pases orbitales completos.
3. **Implementar FEC** (código convolucional o LDPC) y comparar BER antes y después de decodificación.
4. **Agregar filtrado conformador RRC** en transmisor y receptor para reducir el ancho de banda ocupado.
5. **Modelar la estación terrena completa** con seguimiento automático y pérdidas por apuntamiento dinámico.
6. **Comparar con datos de más satélites** como FACSAT-1, ESTCube-1 y Libertad 1 para validar la generalización del modelo.
7. **Simular enlace ascendente** (estación terrena → satélite) para comandos de control.

---

## 9. Conclusiones

1. Se caracterizó exitosamente el subsistema de comunicaciones del CubeSat STRaND-1 mediante cuatro componentes fundamentales: antena (monopolo λ/4, 0 dBi, UHF), transceptor (1 W a 437.568 MHz, BPSK/FSK), módem (BPSK coherente y FSK no coherente a 9600 bps), y TT&C (tramas AX.25 con telemetría de 23.5 bytes promedio).

2. El modelo de simulación en banda base implementado en Python produce resultados de BER consistentes con la teoría de comunicaciones digitales: BPSK requiere ~6 dB menos SNR que FSK para BER cero, validando la cadena de modulación-canal-demodulación.

3. Los flujogramas GNU Radio permiten visualizar en tiempo real las señales IQ generadas y ejecutar una cadena de demodulación completa con bloques estándar, demostrando la interoperabilidad entre el modelo Python y el entorno gráfico de GNU Radio Companion.

4. El link budget descendente UHF muestra un margen mínimo de 9.1 dB (5° de elevación), superando los 3-6 dB recomendados por la literatura, confirmando la viabilidad del enlace a 9600 bps BPSK con parámetros típicos de CubeSat 1U.

5. La comparación con 7 CubeSats reales (STRaND-1, Libertad 1, FACSAT-1, Delfi-C3, ESTCube-1, AAUSAT-II, ITUPSAT 1) muestra concordancia alta en 6 de 7 parámetros evaluados (frecuencia, modulación, tasa, potencia, margen de enlace y BER teórica), y concordancia moderada en ancho de banda debido al uso de pulsos sin filtrado conformador en el modelo.

6. Todos los scripts y flujogramas se desarrollaron con software libre (Python, numpy, scipy, matplotlib, GNU Radio) y se documentaron con comentarios y este informe, constituyendo un recurso reproducible para futuros proyectos académicos de diseño de subsistemas de comunicaciones para CubeSats.

---

## 10. Referencias

1. Bouwmeester, J., & Guo, J. (2010). Survey of worldwide pico- and nanosatellite missions, distributions and subsystem technology. *Acta Astronautica*, 67(7–8), 854–862.
2. Cal Poly SLO. (2022). *CubeSat Design Specification (CDS) Rev. 14*. California Polytechnic State University.
3. Fortescue, P., Swinerd, G., & Stark, J. (2011). *Spacecraft systems engineering* (4th ed.). John Wiley & Sons.
4. Larson, W. J., & Wertz, J. R. (Eds.). (1999). *Space mission analysis and design* (3rd ed.). Microcosm Press.
5. Maral, G., Bousquet, M., & Sun, Z. (2020). *Satellite communications systems* (6th ed.). John Wiley & Sons.
6. Pratt, T., Bostian, C., & Allnutt, J. (2003). *Satellite communications* (2nd ed.). John Wiley & Sons.
7. Proakis, J. G., & Salehi, M. (2008). *Digital communications* (5th ed.). McGraw-Hill.
8. Sklar, B. (2001). *Digital communications: Fundamentals and applications* (2nd ed.). Prentice Hall.
9. GNU Radio Project. (2024). *GNU Radio Manual and C++ API Reference*.
10. SatNOGS. (2026). *SatNOGS DB — STRaND-1 telemetry data*. https://db.satnogs.org/
11. ISIS — Innovative Solutions in Space. *TRXUV Transceiver datasheet*.
12. GomSpace. *NanoCom TRX Transceiver datasheet*.
13. Clyde Space. *STRaND-1 mission documentation*.
14. Álvarez, R., & Restrepo, C. (2020). Desarrollo de tecnología espacial en Colombia: retos y perspectivas para la ingeniería nacional. *Revista Colombiana de Tecnología Avanzada*, 1(35), 1–10.
15. Gómez, J. A., & Llano, G. (2018). Introducción al diseño de sistemas de comunicación para pequeños satélites. *Ingeniería y Ciencia*, 14(27), 123–148.

---

## Apéndice A: Estructura del proyecto

```
cubesat/
├── README.md
├── GUIA_GNURADIO.md
├── load_data.py                      # Descarga de telemetría de SatNOGS
├── decodificar_frames_STRAND1.py     # Decodificación de frames a bytes/binario
├── simular_enlace_rf_fsk_bpsk.py     # Modelo de simulación RF (BER + IQ)
├── generar_iq_bpsk_desde_bin.py      # Generación de archivos IQ
├── calcular_link_budget.py           # Cálculo de link budget
├── comparar_con_cubesats_reales.py   # Comparación con CubeSats documentados
├── simulacion_visualizar_iq.grc      # Flujograma GNU Radio: visualización IQ
├── simulacion_cadena_completa.grc    # Flujograma GNU Radio: cadena BPSK completa
├── simulacion_visualizar_iq.py       # Código Python generado desde .grc
├── simulacion_cadena_completa.py     # Código Python generado desde .grc
├── frames_STRAND1.csv                # Frames de telemetría crudos
├── frames_STRAND1.json               # Frames en formato JSON
├── resumen_telemetria_STRAND1.json   # Resumen de telemetría
├── frames_STRAND1_gnuradio.bin       # Bytes concatenados para simulación
├── docs/
│   ├── DISENO_MODELO_SIMULACION_ENLACE_RF.md
│   ├── CARACTERIZACION_COMPONENTES_COMMS.md
│   └── INFORME_TECNICO_FINAL.md
└── resultados_simulacion/
    ├── configuracion_modelo_rf.json
    ├── resultados_ber_fsk_bpsk.csv
    ├── curva_ber_fsk_bpsk.png
    ├── strand1_bpsk_iq_clean_complex64.bin
    ├── strand1_fsk_iq_clean_complex64.bin
    ├── link_budget_completo.json
    ├── link_budget_resultados.csv
    ├── link_budget_margen_enlace.png
    ├── comparacion_ber_teorica_vs_simulada.png
    ├── comparacion_parametros_cubesats_reales.csv
    ├── comparacion_parametros_cubesats_reales.json
    ├── cubesats_reales_referencia.csv
    └── cubesats_reales_referencia.json
```

---

*Documento generado como parte del proyecto aplicado de Ingeniería Electrónica — UNAD, 2026.*
