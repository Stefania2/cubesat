"""HMTA --- Health Monitoring & Telemetry Analysis de STRaND-1.

Modulo de **supervision**, exclusivamente. Lee telemetria, la valida, la
compara y la explica; no envia ordenes al satelite ni actua sobre ningun
subsistema. Tampoco podria: STRaND-1 esta inactivo y lo que se supervisa es el
archivo historico de SatNOGS.

Capas, de abajo arriba:

    catalogo                inventario de variables: que mide cada una, en que
                            unidad, y si el satelite la emite o no
    telemetry_acquisition   normaliza cualquier fuente a una tabla larga con la
                            procedencia de cada fila (REAL, SIMULADO, ...)
    telemetry_validation    marca lecturas ausentes, duplicadas, saturadas o
                            que no son medidas (cuenta ADC = 0)
    anomaly_detection       limites documentados, tendencias, z robusto y
                            comparacion contra un modelo dinamico
    *_monitor               un modulo por subsistema (EPS, termico, enlace,
                            OBC, ADCS) sobre `subsystem_monitor`
    pid_reference           modelos G1/G2 con P, PI y PID de Ziegler-Nichols
    alerts                  la alerta y su registro persistente (SQLite)
    health_assessment       compone el informe de salud completo

Reutiliza lo que ya existia en el repositorio en lugar de duplicarlo:
`gemelo_digital.datos` (acceso a PostgreSQL), `gemelo_digital.anomalias`
(z robusto y canal enrielado), `strand_amsat.calibraciones()` (rectas de
AMSAT-UK), `parametros_enlace.py` y el analisis de recepcion versionado en
`resultados_simulacion/analisis_recepcion_telemetria.json`.
"""
