# Manual de usuario — Supervisión de salud de STRaND-1

Este manual explica, sin dar nada por sabido, cómo usar la sección **Salud y supervisión del
satélite** de la plataforma STRaND-1 Telemetría. Si buscas los detalles técnicos, están en
[`HMTA_MODULO_SALUD.md`](HMTA_MODULO_SALUD.md).

---

## 1. ¿Qué es esto?

STRaND-1 es un satélite pequeño (un *CubeSat* del tamaño de una caja de zapatos) lanzado en
2013. Mientras funcionaba, enviaba por radio pequeños mensajes con información sobre sí mismo:
el voltaje de sus baterías, la corriente de sus paneles solares y otros datos. A esos mensajes
se les llama **telemetría**.

Estaciones de radioaficionados de todo el mundo (la red **SatNOGS**) recibieron y guardaron esos
mensajes. Esta página los lee y responde a una pregunta: **¿cómo estaba el satélite?**

Dos cosas importantes desde el principio:

1. **Solo observa.** La página no puede enviar órdenes al satélite ni cambiar nada en él.
2. **STRaND-1 ya no transmite.** Lo que se ve es un archivo histórico. La telemetría más
   reciente es de enero de 2023, así que la página nunca dice cómo está el satélite *hoy*: eso
   es desconocido.

## 2. Cómo abrirla

Está en la página de **Inicio**, debajo del satélite en 3D (el gemelo digital). Puedes bajar
hasta ella o pulsar el botón «Salud del satélite» al principio de la página. Si la plataforma
está en tu ordenador, la dirección es `http://localhost:5173/#salud`; la antigua
`/salud` te lleva al mismo sitio.

En la pestaña **Observaciones** de la barra superior puedes ver, en un globo terrestre en 3D,
cómo pasaba STRaND-1 sobre las antenas de SatNOGS que lo escucharon.

La primera vez puede tardar unos minutos: tiene que descargar todo el archivo. Después va
rápido.

## 3. Los controles de arriba

| Control | Para qué sirve |
| --- | --- |
| **Fuente** | Elige entre el **archivo real** (lo que mandó el satélite) y un **escenario simulado** (datos inventados para probar que la página detecta problemas). |
| **Periodo** | Qué trozo del archivo real quieres mirar: el último mes con datos, la época en que todo funcionaba, el momento en que falló un sensor, o todo. |
| **Básico / Técnico** | *Básico* explica qué se mide y qué significa. *Técnico* añade números de referencia, estadísticas y detalles de validación. |

Cuando eliges un escenario simulado aparece una **franja amarilla** arriba que dice
«ESCENARIO SIMULADO — estos datos no son de STRaND-1». Mientras la veas, nada de lo que hay
en pantalla describe al satélite real.

## 4. Cómo leer cada dato

Cada valor lleva dos etiquetas de colores:

**¿De dónde sale el dato?** (procedencia)

| Etiqueta | Significa |
| --- | --- |
| REAL | Lo midió el satélite y lo recibió una estación. |
| SIMULADO | Lo generó una simulación por ordenador. |
| ESTIMADO | Se calculó con un modelo matemático o a partir de otros datos. |
| DOCUMENTADO | Viene de un documento técnico de la misión. |
| NO DISPONIBLE | No existe en esta fuente. |

**¿Cómo está?** (estado)

| Etiqueta | Significa |
| --- | --- |
| Normal | Se comporta como de costumbre. |
| Advertencia | Algo se sale de lo habitual y conviene mirarlo. **No significa que esté roto.** |
| Crítico | Supera un límite oficial documentado. Para STRaND-1 no se publicó ninguno, así que con datos reales nunca aparece. |
| Desconocido | No hay información suficiente para saberlo. **No significa que esté roto.** |

Debajo de cada valor hay dos enlaces desplegables: **¿Qué significa?** y **¿Por qué es
importante?** Púlsalos cuando una palabra no te suene.

## 5. Las secciones

### Inicio
Un resumen: el estado general, la fecha de la última telemetría, el periodo que estás mirando,
una tarjeta por cada parte del satélite (púlsala para ir a ella), de dónde salen los datos y
las alertas más recientes.

Fíjate en el recuadro **Vigencia**: recuerda cuántos días tienen los datos.

### Sistema energético
El satélite funciona con electricidad. Los **paneles solares** la recogen del Sol y las
**baterías** la guardan.

- **Voltaje** (en voltios, V): cuánta «fuerza» eléctrica tiene la batería. Una batería que
  pierde voltaje de forma sostenida se está vaciando.
- **Corriente** (en miliamperios, mA): cuánta electricidad fluye. La de cada panel sube al sol
  y cae casi a cero en la sombra de la Tierra; eso es normal.

En las gráficas, la línea azul son medidas válidas. Las **cruces rojas** son lecturas que *no*
son medidas: el sensor había dejado de funcionar y enviaba siempre el mismo número. Un ejemplo
real: desde febrero de 2021 la batería «marca» 9,75 V todo el rato. No es que la batería
estuviera perfecta: es el número que sale cuando el sensor lee cero. La página lo detecta y lo
dice.

No hay **potencia** ni **nivel de carga** porque el satélite no envía los datos necesarios
para calcularlos.

### Estado térmico
Mostraría la temperatura de las piezas. Con datos reales está vacía: STRaND-1 tenía sensores de
temperatura, pero **nunca envió sus lecturas** en los mensajes que se conservan. La página lo
explica en lugar de inventar valores.

### Comunicaciones
Cómo llegaban los mensajes a la Tierra.

- **Tramas recibidas**: cuántos mensajes llegaron. Una *trama* o *paquete* es un mensaje
  digital con un número de orden.
- **Paquetes perdidos**: si llegan los mensajes 10, 11 y 13, falta el 12. Contando huecos así
  se estima cuántos se perdieron por el camino.
- **Pases observados**: cuántas veces una estación apuntó su antena al satélite.
- **Estado del enlace**: *Activo* (llegan mensajes), *Degradado* (se pierden más que antes),
  *Interrumpido* (se intentó escuchar y no llegó nada) o *Sin información suficiente*.

Más abajo hay dos gráficas que **no son datos reales**: la BER (proporción de bits erróneos)
de una simulación, y el margen del enlace calculado con un modelo. Sirven para entender el
enlace, no prueban que hubiera comunicación.

### Computador de a bordo
El ordenador del satélite. El único dato que envía es un número que la documentación llama
«reloj». La página comprueba si avanza como un reloj y, en el archivo real, **no lo hace**: casi
siempre vale 2. Por eso no se pueden contar reinicios ni saber si el ordenador iba bien. Uso
del procesador, memoria y errores: no disponibles.

### Orientación
Hacia dónde apunta el satélite. STRaND-1 enviaba lecturas de sus **magnetómetros** (sensores
del campo magnético de la Tierra) y el estado de sus **ruedas de reacción** (que lo hacen
girar), pero no la orientación. Los magnetómetros llegan como números sin calibrar, así que no
se pueden convertir en una dirección. La página muestra: «Información ADCS no disponible en
esta fuente de datos».

### Anomalías
Una **anomalía** es algo que se aleja de lo normal. La página busca de cinco maneras:

1. **Límites**: ¿se sale de un rango oficial? (Para STRaND-1 no hay ninguno publicado.)
2. **Tendencias**: ¿sube o baja poco a poco y de forma clara?
3. **Desviaciones**: ¿un valor es muy distinto de los anteriores?
4. **Modelo**: ¿una respuesta medida se parece a la que predice un modelo matemático?
5. **Validación**: ¿la lectura es de verdad una medida?

Cada alerta, al pulsarla, responde a siete preguntas: qué ocurrió, en qué parte, qué variable,
qué valor se registró, con qué se comparó, por qué puede importar y qué haría falta para
investigarlo.

### Modelos PID
Dos modelos matemáticos del curso de Teoría de Control, con controladores **P, PI y PID**
ajustados con un método clásico (Ziegler–Nichols). Un controlador PID es la receta que usan
muchas máquinas para llegar a un valor deseado sin pasarse demasiado: un termostato, el
control de velocidad de un coche.

La gráfica muestra cómo responde cada uno cuando se le pide pasar de 0 a 1. La tabla dice
cuánto se pasa (*sobrepaso*), cuánto tarda en subir y en estabilizarse, y si es estable. Puedes
cambiar el **periodo de muestreo**: con valores grandes algún controlador se vuelve inestable.

Estos modelos **no son partes de STRaND-1** y no controlan nada: son una herramienta de
estudio y de comparación.

### Historial
Mes a mes, cuántas lecturas del voltaje de la batería llegaron y qué parte eran medidas de
verdad. Se ve con claridad cuándo falló el sensor de energía: sano hasta octubre de 2020,
fallos esporádicos hasta enero de 2021 y, desde febrero de 2021, ninguna medida válida.
Debajo, la lista de alertas que se han registrado.

## 6. Probar con escenarios simulados

En **Fuente** elige uno de los escenarios para ver cómo reacciona la página ante problemas
conocidos:

| Escenario | Qué deberías ver |
| --- | --- |
| nominal | Todo normal, sin alertas. |
| caida voltaje | Advertencia en la batería 0. |
| aumento temperatura | Crítico en la temperatura (con un límite de prueba). |
| perdida paquetes | Enlace degradado. |
| errores comunicacion | Más tramas con error. |
| reinicios obc | Tres posibles reinicios del computador. |
| datos inconsistentes | Lecturas que no son medidas detectadas. |
| sin telemetria | Todo desconocido, sin alertas: falta de datos no es un fallo. |
| respuesta dinamica anormal | La respuesta medida se aparta del modelo PID. |

Los escenarios tienen fechas de 2030 a propósito, para que nunca se confundan con el archivo
real.

## 7. Preguntas frecuentes

**¿Por qué casi todo dice «Desconocido»?** Porque el satélite envió pocos tipos de datos y,
desde 2021, el sensor de energía dejó de medir. La página prefiere decir «no lo sé» antes que
adivinar.

**¿«Advertencia» quiere decir que el satélite estaba averiado?** No. Quiere decir que algo se
salió de lo habitual y merece una mirada. En el archivo real, la mayoría de las advertencias
señalan precisamente que un sensor dejó de medir.

**¿Puedo enviarle algo al satélite desde aquí?** No. La página solo lee datos.

**Sale un error «No se pudo leer la base de telemetría».** Es un problema de conexión con la
base de datos, no del satélite. Espera un momento y pulsa *Reintentar*.
