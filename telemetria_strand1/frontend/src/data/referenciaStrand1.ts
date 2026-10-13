/**
 * Datos de REFERENCIA del gemelo digital: lo que dicen los documentos, no lo
 * que midió el satélite.
 *
 * Nada de este archivo es telemetría. Cada valor lleva la fuente de la que se
 * transcribió y, cuando procede, su limitación. La telemetría real llega solo
 * por la API (`/api/gemelo/*`) y nunca se mezcla con estos valores.
 *
 * Dos documentos, dos satélites distintos:
 *   - MISION: STRaND-1, un CubeSat de **3U** (Kenyon, Bridges et al., 2011).
 *   - ESTRUCTURA_1U: una estructura CubeSat de **1U** estudiada por separado
 *     (Cruz-Martínez et al., 2022). No es STRaND-1 y sus resultados no se le
 *     aplican.
 */

export const FUENTE_MISION = {
  clave: 'IAC-11',
  cita:
    'Kenyon, S., Bridges, C. P., et al. (2011). STRaND-1: Use of a $500 smartphone as the central ' +
    'avionics of a nanosatellite. 62nd International Astronautical Congress, IAC-11-B4.6B.8.',
  aviso:
    'Documento de diseño de 2011, anterior al lanzamiento (2013): describe lo previsto, no lo ' +
    'ocurrido en órbita.',
} as const

export const FUENTE_ESTRUCTURA_1U = {
  clave: 'ICTI-2022',
  cita:
    'Cruz-Martínez, E. F., Martínez-Calzada, V., & Saldaña-Heredia, A. (2022). Diseño estructural ' +
    'de un nanosatélite tipo CubeSat. Rev. INGENIERÍA: Ciencia, Tecnología e Innovación, 9(1), ' +
    '45-56. https://doi.org/10.26495/icti.v9i1.2165',
} as const

export const FUENTE_TELEMETRIA =
  'Balizas recibidas por la red SatNOGS, decodificadas con la especificación de AMSAT-UK'

/* ── Clases de dato ───────────────────────────────────────────────────────── */

export type ClaseDato = 'historico' | 'referencia' | 'derivado' | 'conceptual' | 'no_disponible'

export const CLASE: Record<ClaseDato, { etiqueta: string; descripcion: string }> = {
  historico: {
    etiqueta: 'Histórico real',
    descripcion: 'Baliza recibida y almacenada, con su marca de tiempo original.',
  },
  referencia: {
    etiqueta: 'Referencia documental',
    descripcion: 'Valor transcrito de un documento técnico; no es una medida en órbita.',
  },
  derivado: {
    etiqueta: 'Derivado',
    descripcion: 'Calculado en este proyecto a partir de las balizas (edad, diagnóstico).',
  },
  conceptual: {
    etiqueta: 'Conceptual',
    descripcion: 'Representación visual sin dato que la respalde.',
  },
  no_disponible: {
    etiqueta: 'No disponible',
    descripcion: 'La fuente no entrega este dato.',
  },
}

/* ── Presupuestos del documento de la misión ──────────────────────────────── */

/** Tabla II: masa por subsistema, kg, con 10 % de margen. */
export const MASA_KG = [
  { subsistema: 'AOCS', masa: 0.4 },
  { subsistema: 'Potencia', masa: 0.2 },
  { subsistema: 'Comunicaciones', masa: 0.3 },
  { subsistema: 'Propulsión', masa: 0.5 },
  { subsistema: 'OBDH', masa: 0.1 },
  { subsistema: 'Ambiente', masa: 0.0 },
  { subsistema: 'Estructura', masa: 1.0 },
  { subsistema: 'Cableado', masa: 0.2 },
  { subsistema: 'Carga útil', masa: 0.4 },
] as const

export const MASA_TOTALES = {
  subsistemas: 3.2,
  margen: 0.3,
  seca: 3.5,
  propelente: 0.4,
  lanzamiento: 3.9,
} as const

/** Tabla III: demanda de potencia de pico por componente, W. */
export const POTENCIA_PICO_W = [
  { componente: 'Propulsor de plasma pulsado', potencia: 4.9 },
  { componente: 'Controlador AOCS', potencia: 0.1 },
  { componente: 'Sensor de Sol y nadir', potencia: 0.5 },
  { componente: 'Receptor GPS', potencia: 1.0 },
  { componente: 'Transmisor RF', potencia: 3.3 },
  { componente: 'Receptor RF', potencia: 1.6 },
  { componente: 'Resistojet de butano', potencia: 7.0 },
  { componente: 'Smartphone', potencia: 1.2 },
  { componente: 'Computador de altas prestaciones', potencia: 2.0 },
] as const

export const POTENCIA_TOTALES = { subsistemas: 21.6, margen: 2.2, pico: 23.8 } as const

/* ── Componentes del modelo ───────────────────────────────────────────────── */

export type IdSubsistema =
  | 'estructura'
  | 'potencia'
  | 'obc'
  | 'smartphone'
  | 'comunicaciones'
  | 'adcs'
  | 'propulsion'
  | 'sensores'

export interface Componente {
  id: string
  nombre: string
  subsistema: IdSubsistema
  funcion: string
  /** Lo que el documento dice de su forma o ubicación. */
  geometria: 'documentada' | 'aproximada'
  notaGeometria: string
  /** Campos de telemetría que este componente tiene asociados, si los hay. */
  campos: string[]
  /** Por qué no hay telemetría, cuando `campos` está vacío. */
  sinTelemetria?: string
}

export const COMPONENTES: Componente[] = [
  {
    id: 'chasis',
    nombre: 'Chasis Pumpkin 3U (Rev D)',
    subsistema: 'estructura',
    funcion:
      'Estructura de paredes sólidas de tres unidades CubeSat que aloja la pila de tarjetas PC104.',
    geometria: 'documentada',
    notaGeometria: 'Envolvente 3U (≈10 × 10 × 30 cm). El detalle de las paredes es esquemático.',
    campos: [],
    sinTelemetria: 'La estructura no tiene sensores en la baliza.',
  },
  {
    id: 'panel_ala_a',
    nombre: 'Panel solar desplegable A',
    subsistema: 'potencia',
    funcion:
      'Panel de 30 × 10 cm con 6 celdas de triple unión; abisagrado a lo largo de una arista larga. ' +
      'El documento prevé 6,9 V a 0,86 A por panel.',
    geometria: 'documentada',
    notaGeometria:
      'Tamaño y bisagra documentados. No se sabe qué canal de corriente de la baliza corresponde ' +
      'a cada panel, así que no se le asigna ninguno.',
    campos: [],
    sinTelemetria: 'La correspondencia entre canales de corriente y paneles no está documentada.',
  },
  {
    id: 'panel_ala_b',
    nombre: 'Panel solar desplegable B',
    subsistema: 'potencia',
    funcion: 'Segundo panel de 30 × 10 cm, abisagrado en la arista larga opuesta.',
    geometria: 'documentada',
    notaGeometria: 'Igual que el panel A.',
    campos: [],
    sinTelemetria: 'La correspondencia entre canales de corriente y paneles no está documentada.',
  },
  {
    id: 'eps',
    nombre: 'EPS y batería ClydeSpace (20 Wh)',
    subsistema: 'potencia',
    funcion:
      'Regula el flujo de potencia entre paneles, batería y cargas. EPS y batería son nodos I2C ' +
      'que informan corrientes y tensiones.',
    geometria: 'aproximada',
    notaGeometria: 'Tarjetas PC104; su posición en la pila es esquemática.',
    campos: [
      'battery_0_voltage',
      'battery_1_voltage',
      'adc1_py_array_current',
      'adc4_my_array_current',
      'adc7_mx_array_current',
      'adc13_px_array_current',
      'adc10_pz_array_current',
      'adc31_mz_array_current',
    ],
  },
  {
    id: 'obc',
    nombre: 'OBC GomSpace NanoMind A712',
    subsistema: 'obc',
    funcion:
      'Computador de a bordo (ARM7 a 40 MHz, FreeRTOS). Maestro principal del bus I2C; ejecuta el ' +
      'control de actitud e integra un magnetómetro de tres ejes.',
    geometria: 'aproximada',
    notaGeometria: 'Tarjeta PC104; posición en la pila esquemática.',
    campos: ['obc_uptime', 'magnetometer_x', 'magnetometer_y', 'magnetometer_z'],
  },
  {
    id: 'hpc',
    nombre: 'Computador de altas prestaciones (Digi-Wi9C)',
    subsistema: 'smartphone',
    funcion:
      'Puente entre el smartphone y el bus del satélite: interfaz I2C, control por USB y WiFi, ' +
      'carga de software y gestión de telemetría del teléfono.',
    geometria: 'aproximada',
    notaGeometria: 'Tarjeta junto al teléfono; forma esquemática.',
    campos: ['switch_5_digi_wi9c_corriente', 'switch_5_digi_wi9c_tension'],
  },
  {
    id: 'telefono',
    nombre: 'Smartphone Google Nexus One',
    subsistema: 'smartphone',
    funcion:
      'Carga útil experimental: cámara de imagen y ensayo de un teléfono comercial como computador ' +
      'de a bordo. Una cámara VGA vigila su pantalla.',
    geometria: 'aproximada',
    notaGeometria: 'Alojado en una bandeja de carga útil; orientación esquemática.',
    campos: ['switch_2_phone_5v_webcam_corriente', 'switch_2_phone_5v_webcam_tension'],
  },
  {
    id: 'radio',
    nombre: 'Transceptor RF (sección digital, PIC24)',
    subsistema: 'comunicaciones',
    funcion:
      'Codifica y decodifica AX.25, emite la baliza, despliega las antenas y puede reconfigurar el ' +
      'OBC. Amplificador de 1 W nominal (0,25 W en modo baliza/CW).',
    geometria: 'aproximada',
    notaGeometria: 'Tarjeta PC104; posición en la pila esquemática.',
    campos: [],
    sinTelemetria: 'La baliza no incluye magnitudes del transceptor (ni RSSI ni potencia).',
  },
  {
    id: 'antenas',
    nombre: 'Antenas monopolo VHF y UHF',
    subsistema: 'comunicaciones',
    funcion:
      'Dos monopolos de cinta métrica en cajas modulares: banda de 2 m para el enlace ascendente y ' +
      'de 70 cm para el descendente. Se despliegan por el costado al fundirse un hilo de nailon.',
    geometria: 'documentada',
    notaGeometria:
      'Despliegue lateral documentado. La longitud dibujada es proporcional a λ/4 de cada banda; ' +
      'la posición exacta a lo largo del cuerpo es esquemática.',
    campos: [],
    sinTelemetria: 'El estado de despliegue de las antenas no aparece en la baliza.',
  },
  {
    id: 'cubesense',
    nombre: 'CubeSense (sensor de Sol y nadir)',
    subsistema: 'adcs',
    funcion:
      'Dos cámaras CMOS de gran angular, de la Universidad de Stellenbosch: una mide el vector ' +
      'solar y la otra el horizonte.',
    geometria: 'aproximada',
    notaGeometria: 'Tarjeta PC104; posición esquemática.',
    campos: [],
    sinTelemetria: 'La baliza no transmite los vectores de Sol ni de nadir.',
  },
  {
    id: 'ruedas',
    nombre: 'Ruedas de reacción (3) y magnetopares (3)',
    subsistema: 'adcs',
    funcion:
      'Tres ruedas ortogonales para control en tres ejes (90° en 60 s a 5000 rpm) y tres varillas ' +
      'magnéticas para amortiguar y desaturar.',
    geometria: 'aproximada',
    notaGeometria: 'Conjunto esquemático.',
    campos: ['switch_7_reaction_wheels_corriente', 'switch_7_reaction_wheels_tension'],
  },
  {
    id: 'gps',
    nombre: 'Receptor GPS SSTL SGR-05',
    subsistema: 'sensores',
    funcion: 'Receptor GPS comercial de SSTL para determinar la posición orbital.',
    geometria: 'aproximada',
    notaGeometria: 'Tarjeta esquemática.',
    campos: ['switch_6_sgr05_corriente', 'switch_6_sgr05_tension'],
  },
  {
    id: 'ppt',
    nombre: 'Propulsores de plasma pulsado (PPT)',
    subsistema: 'propulsion',
    funcion:
      'Tres tarjetas PC104: dos con cuatro propulsores cada una y una unidad de potencia que eleva ' +
      '5 V a 800 V. Ensayo en tierra: 0,9 µN con 1,5 W.',
    geometria: 'aproximada',
    notaGeometria: 'Tres tarjetas documentadas; su posición en la pila es esquemática.',
    campos: [
      'switch_0_ppt_power_supply_corriente',
      'switch_0_ppt_power_supply_tension',
      'switch_1_ppt_1_2_corriente',
      'switch_1_ppt_1_2_tension',
    ],
  },
  {
    id: 'resistojet',
    nombre: 'Resistojet de butano y depósito',
    subsistema: 'propulsion',
    funcion:
      'Propulsión de gas caliente con depósito soldado de aluminio, válvula solenoide y ' +
      'calefactor; diseñada para 2 m/s de Δv en un volumen menor de 75 × 75 × 21 mm.',
    geometria: 'aproximada',
    notaGeometria: 'Volumen máximo documentado; forma esquemática.',
    campos: [
      'switch_3_warp_valve_corriente',
      'switch_3_warp_valve_tension',
      'switch_4_warp_heater_corriente',
      'switch_4_warp_heater_tension',
    ],
  },
]

/* ── Subsistemas ──────────────────────────────────────────────────────────── */

export interface Subsistema {
  id: IdSubsistema
  titulo: string
  descripcion: string
  /** Hechos del documento de la misión, cada uno con su unidad. */
  referencia: { magnitud: string; valor: string }[]
  /** Qué hay y qué no hay en la telemetría para este subsistema. */
  telemetria: string
}

export const SUBSISTEMAS: Subsistema[] = [
  {
    id: 'estructura',
    titulo: 'Estructura mecánica',
    descripcion:
      'Chasis comercial Pumpkin 3U de paredes sólidas con dos paneles solares desplegables ' +
      'construidos en Surrey, abisagrados a lo largo de las aristas largas.',
    referencia: [
      { magnitud: 'Formato', valor: 'CubeSat 3U' },
      { magnitud: 'Masa de estructura', valor: '1,0 kg (30 % del total)' },
      { magnitud: 'Masa de lanzamiento', valor: '3,9 kg' },
    ],
    telemetria: 'Sin sensores estructurales en la baliza.',
  },
  {
    id: 'potencia',
    titulo: 'Sistema de potencia eléctrica',
    descripcion:
      'EPS y batería ClydeSpace. Generación: dos paneles de 30 × 10 cm, un panel dorsal menor y ' +
      'otro menor hacia la Tierra. Almacenamiento: 20 Wh. Consumo: cargas conmutadas por la ' +
      'tarjeta de interruptores.',
    referencia: [
      { magnitud: 'Generación de pico por órbita', valor: '10 W' },
      { magnitud: 'Potencia media orbital', valor: '3 W (5,8 W apuntando al Sol)' },
      { magnitud: 'Batería', valor: '20 Wh' },
      { magnitud: 'Demanda de pico máxima', valor: '≈ 24 W (nominal < 10 W)' },
    ],
    telemetria:
      'Tensión de dos baterías y corriente de seis canales de panel (±X, ±Y, ±Z). No se emiten ' +
      'temperaturas, ni corriente de batería, ni nivel de carga: la potencia generada o consumida ' +
      'no puede calcularse.',
  },
  {
    id: 'obc',
    titulo: 'Computador de a bordo y procesamiento',
    descripcion:
      'El OBC GomSpace NanoMind es el maestro principal del bus I2C y controla la operación ' +
      'normal. El documento prevé conmutar el bus para que el smartphone actúe como OBC solo ' +
      'después de caracterizar su comportamiento en órbita: no es su papel permanente.',
    referencia: [
      { magnitud: 'Procesador', valor: 'ARM7, 40 MHz' },
      { magnitud: 'Memoria', valor: '2 MB RAM, 8 MB Flash' },
      { magnitud: 'Sistema', valor: 'FreeRTOS' },
    ],
    telemetria:
      'Tiempo de funcionamiento del OBC (segundos desde el último arranque). No consta en la ' +
      'baliza qué computador gobernaba el bus en cada momento.',
  },
  {
    id: 'smartphone',
    titulo: 'Carga útil del smartphone Android',
    descripcion:
      'Un Google Nexus One conectado al satélite a través del computador de altas prestaciones ' +
      'Digi-Wi9C, por USB como enlace principal y WiFi como secundario.',
    referencia: [
      { magnitud: 'Teléfono', valor: 'Google Nexus One' },
      { magnitud: 'Imagen máxima', valor: '2592 × 1944 px' },
      { magnitud: 'Ensayo térmico en tierra', valor: 'opera entre −5 °C y +65 °C' },
    ],
    telemetria:
      'Corriente y tensión de las líneas conmutadas del teléfono y del computador Digi. No hay ' +
      'datos del propio teléfono en la baliza.',
  },
  {
    id: 'comunicaciones',
    titulo: 'Comunicaciones y antenas',
    descripcion:
      'Cadena de radio desarrollada en Surrey: dos transceptores UHF de un solo chip (uno para ' +
      'transmitir y otro para recibir), microcontrolador PIC24 con AX.25 y dos monopolos ' +
      'desplegables.',
    referencia: [
      { magnitud: 'Descendente previsto', valor: '437,575 MHz (banda de 70 cm)' },
      { magnitud: 'Ascendente previsto', valor: '145,860 MHz (banda de 2 m)' },
      { magnitud: 'Potencia de RF', valor: '1 W nominal · 0,25 W en baliza/CW' },
      { magnitud: 'Protocolo', valor: 'AX.25' },
    ],
    telemetria:
      'Lo único observable es la propia recepción: cada baliza almacenada es una transmisión ' +
      'recibida en tierra. No hay RSSI, SNR ni potencia: SatNOGS no los publica por trama.',
  },
  {
    id: 'adcs',
    titulo: 'Determinación y control de actitud',
    descripcion:
      'Magnetómetro del OBC, sensor de Sol y nadir CubeSense, tres ruedas de reacción y tres ' +
      'magnetopares. Modos previstos: amortiguación B-dot, búsqueda del Sol, momento en Y y ' +
      'control en tres ejes.',
    referencia: [
      { magnitud: 'Ruedas de reacción', valor: '3, ortogonales, 5000 rpm máx.' },
      { magnitud: 'Magnetopares', valor: '3, entre ±0,4 y ±0,8 A·m²' },
      { magnitud: 'Ejes cuerpo', valor: '+X vuelo · +Y normal a la órbita · +Z nadir' },
    ],
    telemetria:
      'Magnetómetro en tres ejes, en cuentas sin calibrar. No se transmite actitud: no hay ' +
      'orientación medida ni estimada. Cualquier giro del modelo es de presentación.',
  },
  {
    id: 'propulsion',
    titulo: 'Propulsión',
    descripcion:
      'Dos sistemas experimentales: un resistojet de butano de SSTL y ocho propulsores de plasma ' +
      'pulsado del Surrey Space Centre.',
    referencia: [
      { magnitud: 'Resistojet, Δv de diseño', valor: '2 m/s' },
      { magnitud: 'Presión máxima de operación', valor: '4 bar' },
      { magnitud: 'PPT, empuje medido en tierra', valor: '0,9 µN con 1,5 W' },
      { magnitud: 'PPT, tensión de carga', valor: '800 V' },
    ],
    telemetria:
      'Corriente y tensión de las líneas conmutadas de la válvula, el calefactor y la alimentación ' +
      'de los PPT. La baliza no registra encendidos ni maniobras: aquí no se simula ninguna.',
  },
  {
    id: 'sensores',
    titulo: 'Sensores y telemetría',
    descripcion:
      'El OBC da acceso desde tierra a los puntos de telemetría del bus I2C. La baliza transporta ' +
      'de uno a tres campos por paquete, nunca el estado completo.',
    referencia: [
      { magnitud: 'GPS', valor: 'SSTL SGR-05' },
      { magnitud: 'Bus', valor: 'I2C, nodos esclavos' },
    ],
    telemetria:
      'Cada lectura tiene su propia antigüedad. Posición, velocidad y altitud no están en la ' +
      'baliza: la órbita solo puede obtenerse de elementos TLE externos.',
  },
]

/* ── Parámetros que el panel declara no disponibles ───────────────────────── */

export const NO_DISPONIBLES = [
  { magnitud: 'Temperaturas', estado: 'No emitido', motivo: 'Ninguna baliza recibida incluye canales de temperatura.' },
  { magnitud: 'Corriente y nivel de carga de batería', estado: 'No emitido', motivo: 'Solo se recibe la tensión de las dos baterías.' },
  { magnitud: 'Potencia generada y consumida', estado: 'No calculable', motivo: 'Faltan las tensiones de panel y las corrientes de bus.' },
  { magnitud: 'RSSI y SNR', estado: 'No disponible', motivo: 'SatNOGS no publica nivel de señal por trama.' },
  { magnitud: 'Posición, velocidad y altitud', estado: 'No en telemetría', motivo: 'La baliza no lleva datos de GPS; la órbita se obtiene de un TLE externo.' },
  { magnitud: 'Orientación y velocidad angular', estado: 'No transmitida', motivo: 'Solo hay magnetómetro sin calibrar: no fija la actitud.' },
  { magnitud: 'Estado de despliegue de paneles y antenas', estado: 'No instrumentado', motivo: 'No hay indicador de despliegue en la baliza.' },
] as const

/* ── Modelo estructural de referencia CubeSat 1U ──────────────────────────── */

export const ESTRUCTURA_1U = {
  titulo: 'Modelo estructural de referencia CubeSat 1U',
  aviso:
    'Estructura de 1U (10 × 10 × 10 cm) diseñada y simulada por otros autores. NO es STRaND-1, ' +
    'que es un 3U con chasis comercial Pumpkin. Estos resultados no se aplican a STRaND-1 ni se ' +
    'han usado para dimensionar su modelo 3D.',
  valores: [
    { magnitud: 'Material', valor: 'Aluminio 6061-T6', unidad: '' },
    { magnitud: 'Masa estructural', valor: '142,70', unidad: 'g' },
    { magnitud: 'Aceleración longitudinal usada', valor: '6', unidad: 'g' },
    { magnitud: 'Fuerza en cada una de las cuatro puntas superiores de los rieles', valor: '≈ 106', unidad: 'N' },
    { magnitud: 'Deformación máxima calculada', valor: '0,0015123', unidad: 'mm' },
    { magnitud: 'Esfuerzo máximo calculado (von Mises)', valor: '3,4001', unidad: 'MPa' },
    { magnitud: 'Factor de seguridad reportado', valor: '79,409', unidad: '' },
  ],
  limitaciones: [
    'Análisis estático: una única carga longitudinal de lanzamiento.',
    'No incluye vibración aleatoria, modos propios, choque ni cargas térmicas.',
    'Resultado publicado por sus autores; no se ha repetido la simulación en este proyecto.',
  ],
  pendienteStrand1: [
    'Masa y geometría del chasis Pumpkin 3U con su pila de tarjetas',
    'Interfaces y bisagras de despliegue de los paneles',
    'Rigidez y modos propios',
    'Cargas estáticas y dinámicas del lanzador',
    'Vibración aleatoria',
    'Condiciones térmicas en órbita',
  ],
} as const

/* ── Discrepancias detectadas ─────────────────────────────────────────────── */

export const DISCREPANCIAS = [
  {
    asunto: 'Frecuencia del enlace descendente',
    aplicacion: '437,568 MHz (AMSAT-UK y SatNOGS DB, valor de vuelo)',
    documento: '437,575 MHz (recomendación IARU citada en el documento de 2011)',
    tratamiento:
      'Se conservan ambos. La aplicación usa el valor de vuelo; el del documento es anterior al lanzamiento.',
  },
  {
    asunto: 'Fecha y órbita',
    aplicacion: 'Lanzado en febrero de 2013; ≈ 775 km según el TLE de 2026',
    documento: 'Lanzamiento previsto para el primer trimestre de 2012; órbita sin fijar',
    tratamiento: 'El documento es un diseño previo; prevalecen los datos posteriores de la aplicación.',
  },
  {
    asunto: 'Paneles solares del modelo 3D',
    aplicacion: 'El modelo anterior dibujaba cuatro paneles desplegados, uno por cara lateral',
    documento: 'Dos paneles desplegables de 30 × 10 cm, más un panel dorsal y otro hacia la Tierra, menores',
    tratamiento:
      'El modelo se ha rehecho según el documento. Los seis canales de corriente de la baliza se ' +
      'muestran por eje cuerpo, sin asignarlos a un panel concreto.',
  },
  {
    asunto: 'Antenas del modelo 3D',
    aplicacion: 'El modelo anterior dibujaba dos latiguillos UHF en un extremo',
    documento: 'Un monopolo VHF (ascendente) y otro UHF (descendente), desplegados por el costado',
    tratamiento: 'Corregido en el modelo.',
  },
  {
    asunto: 'Modulación y tasa del enlace',
    aplicacion: 'FSK a 9600 bit/s con NRZI (AMSAT-UK y SatNOGS DB)',
    documento: 'Solo indica AX.25; no especifica modulación ni tasa',
    tratamiento: 'No hay contradicción: el documento no lo recoge.',
  },
  {
    asunto: 'Inclinación del modelo según el magnetómetro',
    aplicacion: 'El modelo anterior inclinaba el satélite con las cuentas del magnetómetro',
    documento: 'El magnetómetro mide el campo en ejes cuerpo; por sí solo no determina la actitud',
    tratamiento:
      'Se ha retirado esa inclinación. El modelo no adopta ninguna orientación derivada de datos; ' +
      'el giro opcional es de presentación.',
  },
] as const
