# Rediseño del gemelo digital de STRaND-1

**Fecha:** 13 de octubre de 2026 · **Página:** `/gemelo` de la plataforma `telemetria_strand1/`

Qué se cambió en la página del gemelo digital, qué se conservó y cómo se comprobó. Regla del
trabajo: mejorar la presentación sin tocar los datos ni añadir ninguno que no exista.

> **Estado.** Probado en local contra la base PostgreSQL local. Ver al final si está desplegado.

## 1. Auditoría de lo que había

| Elemento | Estado anterior | Clase de dato |
|---|---|---|
| `GET /api/gemelo/resumen`, `/estado`, `/serie/{campo}`, `/eventos/{campo}` | 21 833 eventos, 588 pases, 38 magnitudes, del 2016-11-30 al 2023-01-29 | Histórico real (balizas de SatNOGS) |
| Antigüedad y frescura de cada lectura | Calculadas por `gemelo_digital/estado.py` | Derivado |
| Mediana móvil, z robusto, etiquetas y eventos | `gemelo_digital/anomalias.py` | Derivado |
| Modelo 3D (`CubeSat3D.tsx`) | Cuerpo 3U, **cuatro** paneles, dos antenas UHF, tres testigos | Conceptual |
| Inclinación del modelo | Tomada de las cuentas del magnetómetro | Presentada como dato; no lo era |
| Giro del modelo | Barrido constante | Sintético (rotulado) |
| Datos simulados | Ninguno | — |
| Enlace en tiempo real | No existe: la última baliza es de enero de 2023 | — |

Problemas detectados: el modelo no correspondía al documento de la misión (número de paneles,
antenas); el cuerpo entero se pintaba de verde «NOMINAL» a partir del diagnóstico de un solo
canal; 9,75 V y 508–528 mA aparecían como valores normales; la gráfica usaba un eje de categorías
que comprimía los huecos de meses y unía los puntos con una curva suavizada; el salto a un evento
aproximaba la posición por proporción; nada indicaba que la página reproduce un archivo.

## 2. Protección de los datos

El rediseño **no escribe en la base de datos ni cambia su esquema**: no hubo migración que
respaldar. Los cuatro endpoints existentes conservan su contrato; solo se añaden campos.

Comprobación antes/después, entre la API en producción (código anterior) y la local (código
nuevo), sobre los mismos datos:

| Comparación | Resultado |
|---|---|
| `resumen`: los 9 campos originales | idénticos |
| `estado` en 8 instantes: 238 lecturas, campo a campo (valor, unidad, fecha, antigüedad, frescura) | idénticas |
| `serie` de 4 magnitudes: 12 408 puntos, estadísticas y totales | idénticos |
| `eventos` de 4 magnitudes: 449 eventos | idénticos |
| **Diferencias** | **0** |

Reversión: el cambio está en un commit propio; `git revert` lo deshace sin efecto sobre los datos.

## 3. Cambios

**API (aditivos)**

- `resumen`: `fuente`, `fuente_calibracion`, `tipo_dato`, `en_vivo` (siempre falso) y `nota_conexion`.
- `estado`: cada lectura lleva `validacion` —`calibrado`, `canal_sin_medida` (vale la ordenada de su
  recta: cuenta ADC = 0), `pendiente_de_validacion` (valor negativo), `sin_calibrar`, `dato_crudo` o
  `decodificado`—. El valor no se modifica.
- `serie`: parámetros opcionales `desde` y `hasta`. Acotan la vista; la clasificación se calcula
  siempre sobre la serie completa.
- `GET /api/gemelo/indice?t=`: evento vigente en una fecha exacta.
- Las lecturas (`GET`) se reintentan una vez ante un fallo de red.

**Modelo 3D** (`components/gemelo/Modelo3D.tsx`, sustituye a `CubeSat3D.tsx`)

- Configuración según el documento de la misión: chasis 3U con rieles, dos paneles de 30 × 10 cm
  abisagrados en las aristas largas, dos paneles menores en el cuerpo, monopolo UHF (≈ 17 cm) y VHF
  (≈ 51 cm) saliendo por el costado.
- Pila interior esquemática con 10 conjuntos: radio, OBC, EPS y batería, CubeSense, ruedas y
  magnetopares, GPS, computador Digi-Wi9C, smartphone, PPT y resistojet.
- Vistas exterior, interior y explotada; cámaras isométrica, frontal, lateral y superior; órbita,
  zoom y desplazamiento; indicador de ejes; selección de componentes en el modelo o en una lista
  accesible por teclado; etiquetas.
- Animación de despliegue de paneles y antenas, rotulada como conceptual.
- Sin orientación derivada de datos y sin verde por omisión.

**Interfaz** (`pages/GemeloDigital.tsx`, `components/gemelo/`, estilos `.gemelo`)

- Tema oscuro de consola, solo en esta página; el resto de la plataforma no cambia.
- Cabecera con el estado real de la fuente: «Archivo histórico · sin enlace en vivo», fecha y
  antigüedad de la última baliza, y estado de la API. Si la API falla se conserva el último dato
  válido y se muestra desde cuándo.
- Telemetría en tarjetas agrupadas (almacenamiento, generación, OBC, magnetómetro, cargas
  conmutadas) con unidad, antigüedad y validación; tabla completa desplegable; siete parámetros
  declarados **no disponibles** con su motivo.
- Gráfica en eje de tiempo real: los huecos se ven, la línea se interrumpe donde pasan más de 7 días
  sin lecturas, sin interpolar ni suavizar; intervalos por año, por fechas o alrededor del cursor;
  máximo y mínimo localizables; clic para llevar el cursor.
- Lista de eventos con salto exacto y reproducción.
- Pestañas **Subsistemas** (ocho, con los valores de diseño del documento y sus lecturas),
  **Estructura** y **Procedencia y discrepancias**.

## 4. Dos satélites, dos fuentes

| | STRaND-1 | Estudio estructural |
|---|---|---|
| Formato | CubeSat **3U** | CubeSat **1U** |
| Fuente | Kenyon, Bridges *et al.* (2011), IAC-11-B4.6B.8 | Cruz-Martínez *et al.* (2022) |
| Estructura | Chasis comercial Pumpkin 3U; 1,0 kg | Diseño propio en Al 6061-T6; 142,70 g |
| Uso en la página | Modelo 3D y subsistemas | Apartado «Modelo estructural de referencia CubeSat 1U» |

Los valores del estudio 1U (6 g, ≈106 N por riel, 0,0015123 mm, 3,4001 MPa, factor de seguridad
79,409) se muestran con su fuente y sus limitaciones, rotulados como **otro satélite**. No se
asignan a STRaND-1 ni intervienen en el modelo 3D; una prueba lo verifica. El proyecto **no tiene
un análisis estructural propio de STRaND-1**: la página lo declara pendiente.

## 5. Discrepancias encontradas (se conservan ambos valores)

| Asunto | Aplicación | Documento de la misión |
|---|---|---|
| Frecuencia descendente | 437,568 MHz (vuelo) | 437,575 MHz (recomendación IARU, 2011) |
| Lanzamiento | Febrero de 2013 | Previsto para el primer trimestre de 2012 |
| Paneles del modelo | Cuatro (modelo anterior) | Dos desplegables y dos menores → modelo corregido |
| Antenas del modelo | Dos UHF (modelo anterior) | Una VHF y una UHF, laterales → modelo corregido |
| Modulación | FSK 9600 con NRZI | No la especifica (solo AX.25) |

## 6. Limitaciones

- El interior del modelo es esquemático: ni la forma ni el orden de las tarjetas están documentados.
- No se sabe qué canal de corriente corresponde a cada panel; por eso los paneles no cambian con la
  telemetría y las seis corrientes se muestran por eje cuerpo.
- La correspondencia entre los ejes del modelo y los ejes cuerpo del documento no se afirma.
- No hay temperaturas, corriente de batería, potencia, RSSI, posición ni actitud: no están en la
  baliza o la fuente no los publica.
- El documento de la misión es de 2011; describe el diseño previsto, no el comportamiento en órbita.

## 7. Pruebas

```bash
../strand/bin/python -m pytest      # 168 pasan; 15 nuevas en tests/test_gemelo_rediseno.py
cd telemetria_strand1/frontend && npm run build
```

Revisión visual en Chrome sin interfaz (1440 px y 390 px): monitor, vista interior y explotada,
selección de componente, las tres pestañas y el salto del cursor. Sin errores de consola. No se ha
probado con lector de pantalla ni en dispositivos físicos.
