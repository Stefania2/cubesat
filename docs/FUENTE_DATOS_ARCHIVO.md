# La web pública sin base de datos externa (modo archivo)

Desde el 2026-11-17 la plataforma en Vercel **no lee PostgreSQL (Neon)**. Ese día Neon bloqueó el
proyecto por superar la cuota del plan gratuito («Your account or project has exceeded the quota») y
todas las páginas que leían la base devolvían 500. Producción es de solo lectura y nunca ingiere datos
nuevos, así que depender de un servicio externo no aportaba nada.

## Cómo funciona

```
validacion_cientifica/archivo/   (en el repositorio y en el despliegue, 3,2 MB)
   ├── 5 ficheros del sello de reconstrucción (tramas, observaciones, campos, clasificación, TLE)
   └── 4 ficheros del complemento de plataforma (análisis de tramas, ids, reglas, protocolo)
            │  verificación SHA-256 de los 9 frente a sello.json
            ▼
app/archivo_sqlite.py → /tmp/strand1_archivo_<huella>.db   (SQLite, 72 MB, ~4,5 s en frío)
            │  abierta en modo solo lectura (mode=ro)
            ▼
toda la API: ORM (frames, observaciones, telemetría, anomalías, exportar)
             y pandas (gemelo, salud) por DATOS_DSN
```

| Variable | Valor | Efecto |
| --- | --- | --- |
| `FUENTE_DATOS` | `archivo` (por omisión en Vercel) | SQLite desde el archivo sellado |
| | `postgres` (por omisión fuera de Vercel) | la base local o la de `DATABASE_URL` |

* **Sin caída silenciosa.** En modo archivo, si el archivo no supera la verificación SHA-256 la API no
  arranca. La vieja caída a una SQLite *vacía* queda solo para desarrollo local en modo postgres.
* **Procedencia visible.** `/api/status` devuelve `database: "archivo"` y `fuente_datos` con el sello,
  su fecha y la huella del conjunto.
* El complemento de plataforma se sella aparte (`archivar.py --solo-plataforma`) y **no entra en la
  huella de las reconstrucciones**: los manifests ya emitidos siguen reproduciéndose.

## Diferencias de SQL resueltas

| Diferencia | Solución |
| --- | --- |
| SQLite no guarda la zona horaria | tipo `FechaUTC` en `models.py`: siempre devuelve UTC; en PostgreSQL no cambia nada |
| `percentile_cont` (Telemetría → campos) no existe en SQLite | percentiles en Python con la misma interpolación lineal |
| `greatest`, `log` | registradas como funciones de SQLite |
| pandas recibe las fechas como texto | `gemelo_digital.datos._leer` las convierte a datetime UTC |

## Lo que destapó la comparación

`tests/test_fuente_archivo.py` levanta dos backends reales (PostgreSQL local y archivo) y compara la
respuesta JSON de 36 rutas de lectura. Encontró **ocho consultas cuyo orden dependía de la base**, todas
por empates de marca de tiempo (dos balizas en el mismo segundo) o grupos sin orden explícito. Una no era
cosmética: **la pérdida de paquetes del HMTA (página Salud) daba 42,8 % o 41,07 % según cómo la base
deshiciera los empates.** Todas desempatan ahora por identificador, también en PostgreSQL, lo que además
resuelve el riesgo de los 552 instantes ambiguos del gemelo documentado en `VALIDACION_CIENTIFICA.md`.

Resultado: 39 de 39 comprobaciones idénticas.

```bash
../strand_api/bin/python -m pytest tests/test_fuente_archivo.py   # necesita PostgreSQL local
```

## Actualizar los datos de la web

1. Ingerir en la base local como siempre.
2. `../strand_api/bin/python -m validacion_cientifica.archivar --forzar` (sello completo) o
   `--solo-plataforma` si solo cambian reglas o análisis.
3. Pasar las pruebas y desplegar (`vercel deploy --prod` desde `cubesat/`).

Renovar el sello completo cambia la huella de las reconstrucciones: los manifests anteriores dejarán de
reproducirse contra el nuevo archivo, como corresponde.

## Limitaciones

* La web muestra la foto del archivo (datos hasta 2026-07-13, sellados el 2026-11-17).
* Cada instancia nueva de Vercel paga unos 4,5 s extra en su primera petición para construir la base.
* Neon ya no es necesario para la web; sigue siéndolo solo si se quiere una copia remota de la base.
