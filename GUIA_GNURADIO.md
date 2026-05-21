# Guia rapida para GNU Radio en este proyecto

## 1. Abrir GNU Radio en Windows

Usa este archivo del proyecto:

- `C:\CubeSat\abrir_gnuradio.bat`

Ese lanzador abre GNU Radio con las variables de entorno correctas y usa el
runtime GTK reparado del entorno:

- `C:\Users\mstef\anaconda3\envs\gtkfix`

## 2. Entender el archivo `.bin`

El archivo:

- `C:\CubeSat\frames_STRAND1_gnuradio.bin`

contiene bytes de telemetria concatenados. No contiene muestras IQ reales de
una captura SDR. Por eso no se puede conectar directamente a una cadena de
demodulacion RF como si fuera una grabacion compleja de radio.

## 3. Archivos utiles para GNU Radio

Ejecuta:

```powershell
python C:\CubeSat\generar_iq_bpsk_desde_bin.py
```

Eso produce:

- `C:\CubeSat\frames_STRAND1_bits.bin`
- `C:\CubeSat\frames_STRAND1_bpsk_iq_complex64.bin`

Para el modelo completo FSK/BPSK de la Fase 2, ejecuta:

```powershell
python C:\CubeSat\simular_enlace_rf_fsk_bpsk.py
```

Eso produce:

- `C:\CubeSat\resultados_simulacion\strand1_bpsk_iq_clean_complex64.bin`
- `C:\CubeSat\resultados_simulacion\strand1_fsk_iq_clean_complex64.bin`
- `C:\CubeSat\resultados_simulacion\resultados_ber_fsk_bpsk.csv`
- `C:\CubeSat\resultados_simulacion\curva_ber_fsk_bpsk.png`

## 4. Como cargarlos

### Opcion A: revisar telemetria en bruto

En `File Source`:

- File: `C:\CubeSat\frames_STRAND1_gnuradio.bin`
- Output Type: `Byte`
- Repeat: `No`

### Opcion B: revisar el flujo de bits

En `File Source`:

- File: `C:\CubeSat\frames_STRAND1_bits.bin`
- Output Type: `Byte`
- Repeat: `No`

### Opcion C: hacer simulacion BPSK

En `File Source`:

- File: `C:\CubeSat\frames_STRAND1_bpsk_iq_complex64.bin`
- Output Type: `Complex`
- Repeat: `No`

### Opcion D: inspeccionar el modelo FSK/BPSK de Fase 2

En `File Source`:

- File BPSK: `C:\CubeSat\resultados_simulacion\strand1_bpsk_iq_clean_complex64.bin`
- File FSK: `C:\CubeSat\resultados_simulacion\strand1_fsk_iq_clean_complex64.bin`
- Output Type: `Complex`
- Repeat: `No`

Parametros sugeridos:

- Sample Rate: `76800`
- Symbol Rate: `9600`
- Samples/Symbol: `8`

## 5. Idea de flujo simple para prueba

Para la opcion C puedes armar un flujo como este:

`File Source (Complex)` -> `Throttle` -> `QT GUI Time Sink`

o

`File Source (Complex)` -> `Throttle` -> `Constellation Decoder` / `Binary Slicer`

## 6. Si GNU Radio no abre

Prueba siempre desde:

- `C:\CubeSat\abrir_gnuradio.bat`

No lo abras con el acceso directo original ni con un `python` normal del
sistema. En este equipo, la instalacion de `C:\GNURadio-3.10` quedo con GTK
incompleto y por eso el lanzador reparado usa `gtkfix`.
