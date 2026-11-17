"""LIRA AI — Language Intelligence for Real-time Aerospace Operations.

Copiloto de la plataforma STRaND-1. Consulta telemetria, la explica y maneja la
interfaz de la plataforma; nunca envia nada al satelite (no existe ese canal) y
nunca ejecuta codigo.

Capas, de abajo arriba:

    acciones      lista blanca de acciones de interfaz, con limites y confirmacion
    herramientas  consultas de solo lectura sobre el archivo sellado, con procedencia
    interprete    ordenes en español resueltas sin IA (gratis, siempre disponible)
    verificador   comprueba que cada cifra de una respuesta sale de una herramienta
    seguridad     contraseña de la IA, fichas firmadas, limite de peticiones
    registro      auditoria (solo en local; en Vercel el disco es de solo lectura)
    motor         un turno: interprete → (si hace falta y hay acceso) Claude + herramientas

Ninguna capa importa la interfaz: el frontend recibe acciones ya validadas y
las ejecuta con su propio codigo.
"""

VERSION = "1.0.0"
MODELO = "claude-sonnet-5-5"
