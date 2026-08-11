#!/usr/bin/env bash
# Restaura la base de datos de telemetria de STRaND-1 desde el volcado.
#
# El volcado se genero con --no-owner --no-privileges, de modo que no arrastra
# roles ni contrasenas del equipo de origen: la propiedad de los objetos la
# toma quien ejecute la restauracion. No contiene CREATE DATABASE ni \connect,
# asi que vale igual para una base recien creada que para una que ya existe.
#
# Uso:
#   ./restaurar.sh                    # crea la base y restaura (local)
#   ./restaurar.sh --base-existente   # restaura dentro de una base ya creada
#
# El segundo modo es el que necesitan los proveedores gestionados --- Supabase,
# Neon, el PostgreSQL de Render ---, donde la base viene dada y el usuario no
# tiene permiso para crear otras.
#
# La conexion se toma de las variables de entorno de PostgreSQL:
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
#
# En Supabase hay que usar la conexion **directa** (puerto 5432), no el pooler
# de transacciones (6543): este ultimo no admite todas las sentencias de un
# volcado y la restauracion falla a medias.

set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLCADO="$AQUI/strand1.sql.gz"

BASE="${PGDATABASE:-strand1}"
USUARIO="${PGUSER:-strand}"
SERVIDOR="${PGHOST:-localhost}"
PUERTO="${PGPORT:-5432}"

EXISTENTE=0
[[ "${1:-}" == "--base-existente" ]] && EXISTENTE=1

if [[ ! -f "$VOLCADO" ]]; then
  echo "No encuentro el volcado en $VOLCADO" >&2
  exit 1
fi

psql_() { psql -h "$SERVIDOR" -p "$PUERTO" -U "$USUARIO" -d "$BASE" "$@"; }

echo "Restaurando en '$BASE' de $SERVIDOR:$PUERTO como '$USUARIO'"

if [[ $EXISTENTE -eq 1 ]]; then
  # Restaurar sobre tablas que ya tienen datos deja una mezcla silenciosa de dos
  # conjuntos, que es peor que un error: nada falla y los recuentos mienten.
  YA=$(psql_ -tAc "select count(*) from information_schema.tables
                   where table_schema='public'
                     and table_name in ('frames','decoded_fields','observations')" 2>/dev/null || echo 0)
  if [[ "$YA" != "0" ]]; then
    echo "En '$BASE' ya hay $YA de las tablas de telemetria. Vacia el esquema antes:" >&2
    echo "  psql ... -c 'drop table if exists decoded_fields, frames, observations," >&2
    echo "               protocol_definitions, anomaly_rules cascade'" >&2
    exit 1
  fi
else
  if psql -h "$SERVIDOR" -p "$PUERTO" -U "$USUARIO" -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$BASE"; then
    echo "La base '$BASE' ya existe. Usa --base-existente, o borrala:" >&2
    echo "  dropdb -h $SERVIDOR -U $USUARIO $BASE" >&2
    exit 1
  fi
  createdb -h "$SERVIDOR" -p "$PUERTO" -U "$USUARIO" "$BASE"
fi

gunzip -c "$VOLCADO" | psql_ -q -v ON_ERROR_STOP=1

echo
echo "Contenido restaurado:"
psql_ -c "
select 'frames' as tabla, count(*) as filas from frames
union all select 'decoded_fields', count(*) from decoded_fields
union all select 'observations', count(*) from observations
union all select 'protocol_definitions', count(*) from protocol_definitions
union all select 'anomaly_rules', count(*) from anomaly_rules;"

echo "Listo. Apunta DATABASE_URL del backend a esta base."
