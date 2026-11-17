"""STRaND-1 SCIENTIFIC VALIDATION — validación, trazabilidad y reproducibilidad.

Paquete independiente de la interfaz. Separa las cuatro responsabilidades que
el encargo pide no mezclar:

    adquisicion     archivar.py          sella una copia de la capa ORIGINAL
    procesamiento   (no se duplica)      strand_amsat, gemelo_digital, orbita_sgp4
    validacion      procedencia, orbital, telemetria, sincronizacion, diagnosticos
    reproduccion    reconstruccion.py    reconstruye un instante y emite el manifest
    informes        informe.py           JSON y PDF

Ningun modulo de aqui reimplementa la propagacion, la decodificacion ni el
diagnostico: llama a los que ya usa la plataforma y los contrasta. Validar una
copia del codigo no diria nada del codigo que se despliega.

Dependencias: numpy, pandas y sgp4, las mismas de la funcion de Vercel.
"""

VERSION = "1.0.0"
MISION = "STRaND-1"
NORAD_ID = 39090
