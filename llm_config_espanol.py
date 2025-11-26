# Librería estándar de Python para leer archivos TOML en binario
try:
    import tomllib  # stdlib, Python >= 3.11
except ModuleNotFoundError:
    import tomli as tomllib  # backport para Python < 3.11

# Clase que carga la configuración de LLM desde un archivo TOML
# y genera todas las plantillas de prompts necesarias para el chatbot.
class LLMConfig:

    # Inicializa la configuración leyendo el archivo TOML
    # y preparando los prompts y valores que usará el chatbot.
    def __init__(self, filename):
        with open(filename, "rb") as f:
            config = tomllib.load(f)  # Carga el archivo TOML como diccionario

        # Texto inicial y consentimiento del usuario
        self.intro_and_consent = config["consent"]["intro_and_consent"].strip()

        # Prompt de inicio y plantilla para preguntas de recolección de datos
        self.questions_intro = config["collection"]["intro"].strip()
        self.questions_prompt_template = self.generate_questions_prompt_template(config["collection"])
        self.questions_outro = (
            "Gracias por compartir tu situación conmigo. "
            "Creo que tengo toda la información que necesito para apoyarte, "
            "pero déjame verificarlo."
        )

        # Prompt para extracción de información y resumen en JSON
        self.extraction_task = "Crea un escenario basado en estas respuestas."
        self.extraction_prompt_template = self.generate_extraction_prompt_template(config["summaries"])
        self.summary_keys = list(config["summaries"]["questions"].keys())  # Claves JSON para extracción
        self.extraction_adaptation_prompt_template = self.generate_adaptation_prompt_template()

        # Lista de personalidades para generar micronarrativas (ej. Psicólogo, Amigo, Periodista)
        self.personas = [persona.strip() for persona in list(config["summaries"]["personas"].values())]

        # Ejemplo one-shot para guiar al modelo LLM
        self.one_shot = self.generate_one_shot(config["example"])

        # Plantilla principal para generar la narrativa final
        self.main_prompt_template = self.generate_main_prompt_template(config["summaries"]["questions"])

        # Plantilla principal para generar la narrativa final
        self.second_why_prompt = self.generate_2nd_why_prompt_template(config["summaries"]["questions"])

        # Prompt de inicio y plantilla para reflexión e inicio de etapa ABCD
        self.reflect_intro = config["reflect"]["intro"].strip()
        self.reflect_prompt_template = self.generate_reflect_prompt_template(config["reflect"])

        # Prompt de followup y plantilla para preguntas de desequilibrios en el ABCD
        self.a_intro = config["abcd"]["atencion"]["intro"].strip()
        self.b_intro = config["abcd"]["bondad"]["intro"].strip()
        self.c_intro = config["abcd"]["claridad"]["intro"].strip()
        self.d_intro = config["abcd"]["direccion"]["intro"].strip()
        self.a_prompt_template = self.generate_abcd_prompt_template(config["abcd"], "atencion")
        self.b_prompt_template = self.generate_abcd_prompt_template(config["abcd"], "bondad")
        self.c_prompt_template = self.generate_abcd_prompt_template(config["abcd"], "claridad")
        self.d_prompt_template = self.generate_abcd_prompt_template(config["abcd"], "direccion")
        self.abcd_outro = (
            " Gracias por tu apertura. "
            "Espero que esta indagación interna te ayude en situaciones futuras."
        )
        self.abcd_ui = config["abcd"].get("ui", {})
        self.abcd_dims = {
            "atencion": config["abcd"]["atencion"],
            "bondad": config["abcd"]["bondad"],
            "claridad": config["abcd"]["claridad"],
            "direccion": config["abcd"]["direccion"],
        }


    # Genera la plantilla de prompt para hacer preguntas empáticas y secuenciales
    def generate_questions_prompt_template(self, data_collection):
        questions_prompt = (
            f"{data_collection['persona']}\n\n"
            "Tu objetivo es recopilar respuestas estructuradas para las siguientes preguntas, "
            "formulando cada una siempre con un preámbulo cálido y empático según las respuestas anteriores:\n\n"
        )

        for count, question in enumerate(data_collection["questions"]):
            questions_prompt += f"{count+1}. {question}\n"

        questions_prompt += (
            "\nHaz cada pregunta de una en una. "
            "Nunca pongas texto después del preámbulo y las preguntas. "
            "Nunca respondas por la persona. "
            "Recibe al menos una respuesta básica para cada pregunta antes de continuar. "
            "Si no estás seguro de lo que la persona quiso decir, vuelve a preguntar. "
            "Nunca repitas preguntas que ya hiciste si no es la pregunta anterior. "
            "Nunca reformules preguntas que ya hiciste si no es la pregunta anterior. "
            "No pongas los números de pregunta. "
            "Siempre pon el texto de las preguntas en letra negrita. "
            "Manten los pronombres de la persona consistente con el género que te diga. "
            f"{data_collection['language_type']} "
            f"{data_collection['topic_restriction']}"
        )

        n_questions = len(data_collection["questions"])
        if n_questions == 1:
            questions_prompt += "\n\nUna vez que hayas recopilado la respuesta a la pregunta"
        else:
            questions_prompt += f"\n\nUna vez que hayas recopilado las respuestas a las {n_questions} preguntas"

        questions_prompt += (
            ', nunca vuelvas a iniciar a preguntar desde el principio y termina inmediatamente la conversación escribiendo exactamente "Gracias! A continuación te voy a presentar 3 narrativas que pienso que describen tu situación, elige la narrativa que mejor describa tu experiencia. Ya que la hayas elegido, la podemos refinar.".\n\n'
            "Conversación actual:\n{history}\nHuman: {input}\nAI:"
        )

        return questions_prompt

    # Genera el prompt para extraer respuestas relevantes en JSON sin inventar información
    def generate_extraction_prompt_template(self, summaries):
        keys = list(summaries['questions'].keys())

        keys_string = f"`{keys[0]}`"
        for key in keys[1:-1]:
            keys_string += f", `{key}`"
        if len(keys_string):
            keys_string += f", y `{keys[-1]}`"

        extraction_prompt = (
            "Eres un algoritmo experto de extracción de información. "
            "Extrae únicamente la información relevante de las respuestas del humano en el texto. "
            "Usa solamente las palabras y frases que contiene el texto. "
            "Si no conoces el valor de un atributo que se te pide extraer, devuelve null.\n\n"
            f"Vas a producir un JSON con las siguientes claves: {keys_string}.\n\n"
            "Estas corresponden a la(s) siguiente(s) pregunta(s):\n"
        )

        for count, question in enumerate(summaries["questions"].values()):
            extraction_prompt += f"{count+1}: {question}\n"

        extraction_prompt += (
            "\nMensaje hasta la fecha: {conversation_history}\n\n"
            "Recuerda, solo extrae texto que esté en los mensajes de arriba y no lo cambies. "
        )

        return extraction_prompt


    # Genera el prompt para adaptar una narrativa según la petición del usuario (JSON con 'new_scenario')
    def generate_adaptation_prompt_template(self):
        prompt_adaptation = (
            "Eres un asistente servicial, ayudando a estudiantes a adaptar un escenario a su gusto. "
            "El escenario original con el que vino este estudiante:\n\n"
            "Escenario: {scenario}.\n\n"
            "Su petición actual es {input}.\n\n"
            "Sugiere una versión alternativa del escenario. Mantén el lenguaje y el contenido tan similares como sea posible, "
            "cumpliendo con la petición del estudiante.\n\n"
            "Devuelve tu respuesta como un archivo JSON con una sola entrada llamada 'new_scenario'."
        )
        return prompt_adaptation


    # Crea un ejemplo one-shot para guiar al LLM mostrando conversación de ejemplo y resultado esperado
    def generate_one_shot(self, example):
        one_shot = f"Ejemplo:\n{example['conversation']}"
        one_shot += f"\nEl escenario basado en estas respuestas: \"{example['scenario'].strip()}\""
        return one_shot


    # Genera la plantilla principal para crear la narrativa final en JSON con 'output_scenario'
    def generate_main_prompt_template(self, questions):
        main_prompt_template = "{persona}\n\n"
        main_prompt_template += "{one_shot}\n\n"
        main_prompt_template += "Tu tarea:\nCrea un escenario basado en las siguientes respuestas:\n\n"

        for key, question in questions.items():
            main_prompt_template += f"Pregunta: {question}\n"
            main_prompt_template += f"Respuesta: {{{key}}}\n"

        main_prompt_template += (
            "\n{end_prompt}\n\n"
            "Tu respuesta debe ser un archivo JSON con una sola entrada llamada 'output_scenario'."
        )
        return main_prompt_template
    
    # Genera la plantilla principal para crear la narrativa final en JSON con 'output_scenario'
    def generate_2nd_why_prompt_template(self, questions):
        main_prompt_template = "{persona}\n\n"
        main_prompt_template += "{one_shot}\n\n"
        main_prompt_template += "Tu tarea:\nCrea un escenario basado en las siguientes respuestas:\n\n"

        for key, question in questions.items():
            main_prompt_template += f"Pregunta: {question}\n"
            main_prompt_template += f"Respuesta: {{{key}}}\n"

        main_prompt_template += "Crea un escenario basado en estas respuestas.\n\n"

        main_prompt_template += "Un poco de contexto sobre la situación de esta persona:\n\n"
        main_prompt_template += "< {context} >\n\nSé consistente con sus pronombres.\n\n"
        main_prompt_template += (
            "Tu respuesta debe ser un archivo JSON con una sola entrada llamada 'output_scenario'."
        )
        return main_prompt_template


    # Genera la plantilla de prompt para hacer preguntas empáticas y secuenciales
    def generate_abcd_prompt_template(self, followups, dim):
        abcd_prompt = (
            f"{followups['persona']}\n\n"
            "Tu objetivo es recopilar respuestas estructuradas para las siguientes preguntas, "
            "formulando cada una siempre con un preámbulo cálido y empático según las respuestas anteriores:\n\n"
        )

        for count, question in enumerate(followups[dim]["followups"]):
            abcd_prompt += f"{count+1}. {question}\n"

        abcd_prompt += (
            "\nHaz cada pregunta de una en una. "
            "No pongas los números de pregunta. "
            "Siempre pon el texto de las preguntas en letra negrita. "
            "Nunca pongas texto después del preámbulo y las preguntas. "
            f"{followups['language_type']} "
            "Recibe al menos una respuesta básica para cada pregunta antes de continuar. "
            "Nunca repitas ni reformules preguntas anteriores. "
            "Nunca respondas por la persona. "
            "Si no estás seguro de lo que la persona quiso decir, vuelve a preguntar. "
            f"{followups['topic_restriction']}"
        )

        n_questions = len(followups[dim]["followups"])
        if n_questions == 1:
            abcd_prompt += "\n\nUna vez que hayas recopilado la respuesta a la pregunta"
        else:
            abcd_prompt += f"\n\nUna vez que hayas recopilado las respuestas a las {n_questions} preguntas"

        abcd_prompt += (
            ', termina inmediatamente la conversación escribiendo únicamente la palabra "Gracias!".\n\n'
            "Conversación actual:\n{history}\nHuman: {input}\nAI:"
        )

        return abcd_prompt
    
    # Genera la plantilla de prompt para hacer preguntas empáticas y secuenciales
    def generate_reflect_prompt_template(self, data_collection):
        reflect_prompt = (
            f"{data_collection['persona']}\n\n"
            "Tu objetivo es escuchar empáticamente a la persona abrir la indagación interna acerca de esa situación, y darle la siguiente instrucción, "
            "formulandola siempre con un preámbulo cálido y empático según la respuesta anterior:\n\n"
        )

        reflect_prompt += f"< {data_collection['instruction']} >\n"

        reflect_prompt += (
            "\nNunca pongas texto después del preámbulo y la instrucción. "
            f"{data_collection['language_type']} "
            "Recibe al menos una respuesta básica antes de dar la instrucción. "
            "Nunca respondas por la persona. "
            f"{data_collection['topic_restriction']}"
        )

        reflect_prompt += "\n\nUna vez que hayas dado la instrucción y la persona haya escrito <Listo> "

        reflect_prompt += (
            ', termina inmediatamente la conversación escribiendo exactamente "Gracias! Gracias por compartir tu situación conmigo. Esta reflexión es un regalo para tu práctica. 🌱".\n\n'
            "Conversación actual:\n{history}\nHuman: {input}\nAI:"
        )

        return reflect_prompt