# Caracterización técnica de los componentes del subsistema de comunicaciones de un CubeSat

**Proyecto:** Caracterización del subsistema electrónico de comunicaciones de un CubeSat mediante simulación de señales de radiofrecuencia

**Autora:** Mayelin Stefania Aguilar Vásquez — UNAD, Ingeniería Electrónica

**Línea de investigación:** Ciberseguridad y Telecomunicaciones

**Fecha:** Julio 2026

---

## 1. Introducción

El subsistema de comunicaciones (COMMS) es el encargado de establecer y mantener el enlace de radiofrecuencia entre el CubeSat y la estación terrena. Sus componentes principales son la antena, el transceptor de radiofrecuencia, el modulador/demodulador (módem) y el sistema de telemetría, seguimiento y comando (TT&C).

Este documento describe técnicamente cada uno de estos componentes, sus parámetros eléctricos clave, las implementaciones típicas en CubeSats universitarios y su relación con el modelo de simulación desarrollado en este proyecto, usando como referencia el satélite STRaND-1 (NORAD 39090).

---

## 2. Antena

### 2.1 Función en el subsistema

La antena es el elemento encargado de convertir la señal eléctrica guiada (proveniente del transceptor) en una onda electromagnética radiada hacia el espacio libre, y viceversa en recepción. Es el componente que más directamente influye en el balance de enlace (link budget).

### 2.2 Parámetros eléctricos clave

| Parámetro | Símbolo | Unidad | Descripción |
|-----------|---------|--------|-------------|
| Frecuencia de operación | f | MHz | Rango de frecuencias donde la antena presenta adaptación aceptable |
| Ganancia | G | dBi | Relación entre la intensidad de radiación en una dirección y la de una antena isotrópica |
| Polarización | — | — | Orientación del campo eléctrico radiado (lineal, circular) |
| ROE / VSWR | S | — | Relación de onda estacionaria; mide la adaptación de impedancia |
| Ancho de banda | BW | MHz | Rango de frecuencias con VSWR < 2:1 |
| Patrón de radiación | — | — | Distribución angular de la energía radiada |
| Impedancia | Z | Ω | Usualmente 50 Ω para sistemas de RF |

### 2.3 Tipos de antenas usadas en CubeSats

#### 2.3.1 Monopolo

- **Descripción:** Conductor rectilíneo de longitud λ/4 (aprox. 17 cm para UHF a 437 MHz) que opera con un plano de tierra (la estructura del CubeSat).
- **Ventajas:** Simple, desplegable, bajo costo, ocupa poco volumen.
- **Desventajas:** Ganancia baja (~0-2 dBi), polarización lineal, patrón cuasi-omnidireccional.
- **Uso típico:** El más común en CubeSats 1U. Usado por STRaND-1, ESTCube-1, ITUPSAT 1.

#### 2.3.2 Dipolo

- **Descripción:** Dos conductores de λ/4 cada uno, alimentados en el centro. Usualmente desplegable.
- **Ventajas:** Ganancia moderada (~2 dBi), patrón omnidireccional en el plano H.
- **Desventajas:** Requiere dos elementos desplegables, mayor volumen.
- **Uso típico:** Libertad 1 (Colombia), Delfi-C3.

#### 2.3.3 Antena de microcinta (patch)

- **Descripción:** Parche conductor sobre un sustrato dieléctrico con plano de tierra.
- **Ventajas:** Perfil bajo, no requiere despliegue, polarización circular posible.
- **Desventajas:** Ganancia limitada (~2-4 dBi), ancho de banda angosto (< 5%).
- **Uso típico:** Misiones que requieren polarización circular (bandas S, X).

#### 2.3.4 Helix (hélice)

- **Descripción:** Estructura helicoidal que produce polarización circular.
- **Ventajas:** Ganancia moderada a alta (~5-15 dBi), polarización circular.
- **Desventajas:** Volumen mayor, más compleja de desplegar.
- **Uso típico:** Estaciones terrenas (no embarcada típicamente en 1U).

### 2.4 Antena del STRaND-1

STRaND-1 utiliza una antena tipo **monopolo desplegable** para la banda UHF a 437.568 MHz. Las características típicas son:

- **Longitud:** λ/4 ≈ 17.1 cm a 437.568 MHz
- **Ganancia estimada:** 0-2 dBi
- **Polarización:** Lineal
- **VSWR típico:** < 2:1 en el rango 435-438 MHz
- **Impedancia:** 50 Ω
- **Despliegue:** Mediante mecanismo de resorte o memoria de forma

---

## 3. Transceptor de radiofrecuencia

### 3.1 Función en el subsistema

El transceptor (TRX) integra las funciones de transmisión y recepción de la señal RF. En transmisión, toma la señal modulada en banda base, la convierte a la frecuencia de portadora UHF, la amplifica y la entrega a la antena. En recepción, amplifica la señal débil proveniente de la antena, la filtra y la convierte a banda base para su demodulación.

### 3.2 Arquitectura típica

```text
TRANSMISOR:
  BB (I/Q) → [Filtro BB] → [Mezclador] → [Filtro RF] → [PA] → [Duplexor/Switch] → Antena
                  ↑
            [PLL/Sintetizador]

RECEPTOR:
  Antena → [Duplexor/Switch] → [LNA] → [Filtro RF] → [Mezclador] → [Filtro BB] → BB (I/Q)
                  ↑
            [PLL/Sintetizador]
```

### 3.3 Parámetros eléctricos clave

| Parámetro | Símbolo | Unidad | Descripción |
|-----------|---------|--------|-------------|
| Frecuencia de transmisión | f_tx | MHz | Frecuencia de la portadora transmitida |
| Frecuencia de recepción | f_rx | MHz | Frecuencia de la portadora recibida |
| Potencia de salida | P_tx | dBm | Potencia RF entregada a la antena |
| Sensibilidad del receptor | S_rx | dBm | Potencia mínima detectable para una BER dada |
| Figura de ruido | NF | dB | Degradación de la SNR por el receptor |
| Ganancia del LNA | G_LNA | dB | Ganancia del amplificador de bajo ruido |
| Potencia máxima de PA | P_sat | dBm | Potencia de saturación del amplificador de potencia |
| Estabilidad de frecuencia | Δf/f | ppm | Precisión del sintetizador de frecuencia |
| Selectividad de canal | — | dB | Rechazo de canales adyacentes |

### 3.4 Transceptores comerciales típicos para CubeSat

| Modelo | Fabricante | Banda | P_tx | Sensibilidad | Interfaz |
|--------|------------|-------|------|-------------|----------|
| TRXUV | ISIS (Innovative Solutions in Space) | UHF/VHF | 30 dBm | -124 dBm | I2C, UART |
| AstroDev UHF | AstroDev | UHF | 27-30 dBm | -120 dBm | UART |
| NanoCom TRX | GomSpace | UHF | 30 dBm | -125 dBm | I2C, UART |
| STX-1 | EnduroSat | UHF/S | 27 dBm | — | UART |

### 3.5 Parámetros del transceptor del STRaND-1

Basado en datos de la misión y transceptores típicos de Clyde Space (fabricante de STRaND-1):

| Parámetro | Valor |
|-----------|-------|
| Frecuencia de transmisión | 437.568 MHz |
| Potencia de transmisión | 1 W (30 dBm) |
| Tipo de modulación compatible | BPSK / GMSK |
| Estabilidad de frecuencia | ±2 ppm |
| Impedancia de antena | 50 Ω |
| Consumo en transmisión | ~3-5 W |
| Consumo en recepción | ~0.5-1 W |

### 3.6 Modelo en la simulación

En el modelo de simulación desarrollado (ver `simular_enlace_rf_fsk_bpsk.py`), el transceptor se modela de forma equivalente en banda base:

- **Modulación:** Se implementa mediante mapeo de bits a símbolos BPSK (NRZ: 0 → -1, 1 → +1) y FSK (dos tonos complejos a ±2400 Hz).
- **Canal:** AWGN (ruido blanco gaussiano aditivo) que modela el ruido térmico del receptor y el frente atmosférico.
- **Demodulación:** Coherente ideal para BPSK (promedio de muestras por símbolo con decisión por umbral) y por correlación de energía para FSK.
- **No se modelan:** No linealidades del PA, fase noise del PLL, ni desvanecimiento por multitrayecto.

---

## 4. Modulador / Demodulador (Módem)

### 4.1 Función en el subsistema

El módem convierte los datos digitales (bits) en señales analógicas moduladas para su transmisión (modulación), y recupera los bits a partir de la señal recibida (demodulación). En CubeSats modernos, esta función suele estar integrada en el transceptor o implementada en un FPGA/microcontrolador.

### 4.2 Esquemas de modulación usados en CubeSats

#### 4.2.1 BPSK (Binary Phase Shift Keying)

- **Principio:** La fase de la portadora cambia 180° entre dos estados (bit 0 y bit 1).
- **Expresión matemática:** s(t) = A · cos(2πf_c t + φ), φ ∈ {0, π}
- **Eficiencia espectral:** 1 bps/Hz
- **Probabilidad de error (AWGN):** BER = ½ · erfc(√(Eb/N0))
- **Requiere:** Recuperación de portadora (Costas loop o similar)
- **Uso en CubeSats:** STRaND-1, FACSAT-1, ESTCube-1, Delfi-C3

#### 4.2.2 FSK (Frequency Shift Keying)

- **Principio:** La frecuencia instantánea de la portadora cambia entre dos valores.
- **Expresión matemática:** s(t) = A · cos(2π(f_c ± f_d)t)
- **Eficiencia espectral:** < 1 bps/Hz (depende de la desviación)
- **Probabilidad de error (no coherente):** BER = ½ · exp(-Eb/(2N0))
- **Ventaja:** No requiere recuperación de portadora coherente
- **Uso en CubeSats:** Misiones de baja tasa, balizas de telemetría

#### 4.2.3 AFSK (Audio Frequency Shift Keying)

- **Principio:** Variante de FSK donde se modula un tono de audio que luego modula la portadora FM.
- **Estándar:** Bell 202 (1200/2200 Hz para 0/1 a 1200 bps)
- **Uso en CubeSats:** Libertad 1, AAUSAT-II. Muy usado en radioaficionados (APRS/AX.25).

#### 4.2.4 GMSK (Gaussian Minimum Shift Keying)

- **Principio:** FSK con filtrado gaussiano para reducir el ancho de banda. MSK tiene índice de modulación 0.5.
- **Eficiencia espectral:** Alta (~1.5 bps/Hz con BT=0.5)
- **Uso en CubeSats:** FACSAT-1, misiones más modernas

### 4.3 Parámetros del módem en este proyecto

| Parámetro | BPSK | FSK |
|-----------|------|-----|
| Tasa de símbolos | 9600 bps | 9600 bps |
| Samples por símbolo | 8 | 8 |
| Frecuencia de muestreo | 76800 sps | 76800 sps |
| Desviación FSK | N/A | ±2400 Hz |
| Ancho de banda (-20 dB) | ~27.0 kHz | ~11.8 kHz |
| BER a SNR=0 dB (simulado) | 5.3 × 10⁻⁵ | 5.3 × 10⁻² |
| SNR para BER=0 (18776 bits) | 2 dB | 8 dB |
| Tipo de demodulación | Coherente ideal (integración y decisión) | No coherente (correlación de energía) |

### 4.4 Comparación de desempeño BPSK vs FSK

La simulación confirma lo esperado teóricamente:

- **BPSK** requiere aproximadamente 3 dB menos de SNR que FSK no coherente para la misma BER, debido a la distancia euclidiana entre símbolos (2√E vs. √2E).
- **FSK** ofrece un ancho de banda menor (~12 kHz vs. ~27 kHz) debido a que la energía se concentra en dos tonos discretos, pero su demodulación no coherente es menos eficiente energéticamente.
- Para el enlace CubeSat típico con restricciones de potencia, **BPSK es la opción preferida**, lo que coincide con el ~45% de las misiones CubeSat universitarias que usan BPSK (Bouwmeester & Guo, 2010).

---

## 5. Sistema de telemetría, seguimiento y comando (TT&C)

### 5.1 Función en el subsistema

El sistema TT&C (Telemetry, Tracking & Command) es el responsable de tres funciones vitales:

1. **Telemetría (downlink):** Transmite a tierra datos del estado interno del satélite: temperatura, voltaje de baterías, corriente de paneles solares, estado de los subsistemas, etc.
2. **Seguimiento (tracking):** Permite determinar la posición y velocidad del satélite mediante el análisis de la señal de beacon (efecto Doppler, tiempo de arribo).
3. **Comando (uplink):** Recibe y ejecuta comandos desde la estación terrena: cambio de modo de operación, actualización de software, activación de experimentos.

### 5.2 Parámetros de telemetría típicos en CubeSats

| Parámetro | Rango típico | Resolución |
|-----------|-------------|-----------|
| Temperatura interna | -20 a +60 °C | 0.1-1 °C |
| Voltaje de bus | 3.3-8.4 V | 0.01-0.1 V |
| Corriente de paneles solares | 0-2 A | 1-10 mA |
| Corriente de batería | -1 a +1 A | 1-10 mA |
| Estado de carga (SoC) | 0-100 % | 1 % |
| Velocidad de rueda de reacción | ±5000 RPM | 1 RPM |
| Magnetómetro | ±Gauss | 1-10 mG |

### 5.3 Protocolos de comunicaciones

#### 5.3.1 AX.25 (Amateur X.25)

- **Origen:** Derivado del protocolo X.25 para redes de radioaficionados.
- **Estructura:** Trama con flag (0x7E), dirección, control, PID, información, FCS.
- **Tasa típica:** 1200 bps (AFSK Bell 202) o 9600 bps (BPSK/GMSK).
- **Uso en CubeSats:** Protocolo más extendido en CubeSats universitarios. Usado por STRaND-1 para telemetría, Libertad 1, AAUSAT-II, entre otros.

#### 5.3.2 CCSDS (Consultative Committee for Space Data Systems)

- **Estándar:** Estándar internacional para comunicaciones espaciales (CCSDS 131.0-B).
- **Ventajas:** Mayor eficiencia, soporte para corrección de errores (turbo códigos, LDPC), estructuras de trama más flexibles.
- **Uso en CubeSats:** Misiones más avanzadas (FACSAT-1 usa capa física CCSDS).

#### 5.3.3 CubeSat Space Protocol (CSP)

- **Origen:** Desarrollado por Aalborg University para CubeSats.
- **Características:** Capa de red liviana sobre enlaces serie, soporta routing, addressing.
- **Uso:** Gobierna la red interna entre subsistemas en muchos CubeSats (GomSpace, ISIS).

### 5.4 Telemetría del STRaND-1 — Análisis de datos reales

Se procesaron 100 frames de telemetría real del STRaND-1 descargados de SatNOGS:

| Parámetro | Valor |
|-----------|-------|
| Total de frames | 100 |
| Rango de fechas | 2025-04-24 a 2026-05-06 |
| Estaciones observadoras | 24 estaciones globales |
| Longitud promedio de frame | 23.5 bytes (188 bits) |
| Longitud mínima | 1 byte |
| Longitud máxima | 64 bytes |
| Entropía promedio del payload | 4.049 bits/byte |
| Tiempo de transmisión por frame | ~19.6 ms a 9600 bps |

La entropía promedio de 4.049 bits/byte (sobre 8 bits/byte máximo) indica que los frames contienen una mezcla de datos estructurados (campos de cabecera y checksum con baja entropía) y datos variables (telemetría numérica con entropía moderada).

### 5.5 Estructura de trama típica (AX.25)

```text
┌──────┬───────┬───────────┬──────┬──────┬──────┐
│ Flag │ Dir. │ Control   │ PID  │ Info │ FCS  │
│ 0x7E │ 14 B  │ 1 B      │ 1 B  │ N B  │ 2 B  │
└──────┴───────┴───────────┴──────┴──────┴──────┘
         ↑              ↑
      Callsign      Telemetria
      del sat.      del satelite
```

Donde:
- **Flag (1 byte):** Delimitador de trama (0x7E)
- **Dirección (14 bytes):** Callsign del satélite y de la estación terrena
- **Control (1 byte):** Tipo de trama (información, supervisión, no numerada)
- **PID (1 byte):** Identificador de protocolo
- **Información (N bytes):** Payload de telemetría
- **FCS (2 bytes):** Frame Check Sequence (CRC-16)

Los frames de STRaND-1 analizados en este proyecto contienen los payloads en hexadecimal sin la estructura completa de capa física (los flags, direcciones y FCS son añadidos por la estación terrena al recibir). Los 2347 bytes totales de telemetría representan aproximadamente 2 segundos de transmisión continua a 9600 bps.

---

## 6. Integración de los componentes en el modelo de simulación

El siguiente diagrama muestra cómo se relacionan los componentes caracterizados con el modelo de simulación implementado:

```text
DATOS REALES (STRaND-1)
       ↓
[Telemetría en frames hex]
       ↓
[Decodificación a bytes/binario]
       ↓
┌─────────────────────────────────────────────────────┐
│              MODELO DE SIMULACIÓN                   │
│                                                     │
│  Bits → [Modulador] → [Canal AWGN] → [Demodulador] │
│             ↑                        ↑              │
│        BPSK/FSK                  Coherente/         │
│        (módem)                   Correlación         │
│                                                     │
│         ↓ Salidas: BER, SNR, espectro               │
└─────────────────────────────────────────────────────┘
       ↓
[Comparación con teoría y CubeSats reales]
       ↓
[DOCUMENTO TÉCNICO DE REFERENCIA]
```

### Correspondencia con componentes físicos

| Componente físico | Modelo en simulación |
|-------------------|---------------------|
| Antena TX (monopolo 0 dBi) | No modelada explícitamente; se considera en el link budget (G_tx = 0 dBi) |
| Transmisor (PA + PLL) | Mapeo de bits → símbolos + sobremuestreo a 76800 sps |
| Canal RF (espacio libre, atmósfera) | Canal AWGN + pérdidas en link budget |
| Receptor (LNA + downconverter) | Figura de ruido 2 dB en link budget |
| Demodulador | Integración + binary slicer (BPSK); correlación (FSK) |
| Decodificador de trama | Separación de bytes desde bits; no se implementa AX.25 completo |

---

## 7. Referencias

1. Bouwmeester, J., & Guo, J. (2010). Survey of worldwide pico- and nanosatellite missions, distributions and subsystem technology. *Acta Astronautica*, 67(7–8), 854–862.
2. Cal Poly SLO. (2022). *CubeSat Design Specification (CDS) Rev. 14*. California Polytechnic State University.
3. Fortescue, P., Swinerd, G., & Stark, J. (2011). *Spacecraft systems engineering* (4th ed.). John Wiley & Sons.
4. Larson, W. J., & Wertz, J. R. (Eds.). (1999). *Space mission analysis and design* (3rd ed.). Microcosm Press.
5. Maral, G., Bousquet, M., & Sun, Z. (2020). *Satellite communications systems: Systems, techniques and technology* (6th ed.). John Wiley & Sons.
6. Pratt, T., Bostian, C., & Allnutt, J. (2003). *Satellite communications* (2nd ed.). John Wiley & Sons.
7. GNU Radio Project. (2024). *GNU Radio documentation*. https://www.gnuradio.org/doc/
8. SatNOGS. (2026). *SatNOGS DB — STRaND-1 telemetry*. https://db.satnogs.org/
9. ISIS — Innovative Solutions in Space. *TRXUV Transceiver datasheet*.
10. GomSpace. *NanoCom TRX Transceiver datasheet*.
11. Álvarez, R., & Restrepo, C. (2020). Desarrollo de tecnología espacial en Colombia: retos y perspectivas para la ingeniería nacional. *Revista Colombiana de Tecnología Avanzada*, 1(35), 1–10.
12. Gómez, J. A., & Llano, G. (2018). Introducción al diseño de sistemas de comunicación para pequeños satélites. *Ingeniería y Ciencia*, 14(27), 123–148.

---

*Documento generado como parte del proyecto aplicado de Ingeniería Electrónica — UNAD, 2026.*
