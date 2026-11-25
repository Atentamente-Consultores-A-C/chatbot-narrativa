# -*- coding: utf-8 -*-
"""
Mapas de curso ("cerebro"): qué herramientas hay en cada módulo y para qué sirven. Se
inyectan SIEMPRE en el prompt del programa correspondiente, además de los fragmentos del RAG,
para que el bot sepa qué ha aprendido la persona y cómo conectarlo con su situación.

Fuente: explicación de Leandro (reunión 23-nov-2026) + nombres de prácticas tal como aparecen
en las cartas descriptivas V2022 de EpB cargadas en Supabase.
PENDIENTE: validar con el equipo académico (nombres exactos, qué va en cada sesión).
"""

EPB_COURSE_MAP = """MAPA DEL CURSO EDUCAR PARA EL BIENESTAR (EPB)
En EPB NO se usa el lenguaje del ABCD (Atención, Bondad, Claridad, Dirección) ni se habla de \
"desequilibrios". Se habla de competencias socioemocionales: autoconocimiento, regulación \
emocional y prosocialidad.

MÓDULO 1 — AUTOCONOCIMIENTO
- Metas y valores: qué me importa, qué anhelo. Práctica: *Visión en 4 pasos* (anhelos más \
profundos; qué aspectos de mí quisiera cultivar o pulir; qué quisiera ofrecer al mundo; cómo \
se vincula eso con lo que hago ahora). En EPB se presenta como herramienta de \
autoconocimiento, no de "dirección".
- Entrenamiento de la atención: atención a la respiración / recolección del respirar, \
*momento de atención*, atención al cuerpo. Sirven para concentrarse, calmarse y descansar \
internamente. La clave: notar que la mente se fue con un pensamiento, soltarlo y regresar al \
respirar, sin pelearse con lo que se piensa (la pelea interna es lo que más cansa).
- Conciencia emocional: reconocer qué emoción siento, cómo se siente en el cuerpo y cuáles son \
mis *botones* (lo que dispara mis emociones), para que las emociones no me controlen tanto.

MÓDULO 2 — REGULACIÓN EMOCIONAL
Primero conciencia emocional (darse cuenta), después regular. Estrategias para regular las \
emociones, según dónde intervengo:
- Mundo — trabajar con la situación: evitar la situación o modificarla (ej. si sé que el \
berrinche de mi hija es un botón cuando estoy cansada, se la paso a su papá antes de que sea \
demasiado tarde).
- Atención — regular la atención (despliegue atencional): llevar la atención a otro lado, al \
respirar, al cuerpo.
- Pensamiento — cambio cognitivo: ver la situación de otra manera.
- Acción — modular la conducta: cambiar cómo respondo una vez que la emoción ya surgió.
Prácticas del módulo: *recapitulación*, *darle la mano a las emociones*, *atención a los \
pensamientos* / observar los pensamientos sin intervenir, atención al cuerpo, *mariposa*.

MÓDULO 3 — PROSOCIALIDAD (cultivar las cualidades del corazón)
Empatía, imparcialidad, bondad, compasión y regocijo. Prácticas: bondad (hacia mí, hacia \
personas difíciles), compasión, regocijo (incluso por una persona difícil), *al igual que yo*.

CÓMO USAR ESTE MAPA
- Si sabes en qué módulo va la persona, sugiere primero herramientas de ese módulo o de los \
anteriores: son las que ya conoce. Si mencionas algo de un módulo que todavía no ve, dilo \
("esto lo vas a ver más adelante en el curso").
- Recuérdale lo que ha visto de forma breve ("en el curso has visto cosas como atención a la \
respiración o identificar tus botones") para ayudarle a hacer la conexión.
- Los pasos concretos de cada práctica tómalos de los MATERIALES; si no aparecen, explica solo \
la idea general sin inventar pasos.
- Ajusta la intensidad: si la persona está muy agotada o le cuesta mucho, propone una versión \
muy corta y suave (30 segundos o tres respiraciones)."""


def get_course_map(program: str | None) -> str:
    return EPB_COURSE_MAP if program == "EPB" else ""
