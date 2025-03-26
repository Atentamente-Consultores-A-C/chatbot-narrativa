import tomllib

class LLMConfig:

    def __init__(self, filename):

        with open(filename, "rb") as f:
            config = tomllib.load(f)

        self.intro_and_consent = config["consent"]["intro_and_consent"].strip()

        self.questions_intro = config["collection"]["intro"].strip() 
        self.questions_prompt_template = self.generate_questions_prompt_template(config["collection"])
        self.questions_outro = "Gracias por compartir tu situación conmigo. Creo que tengo toda la información que necesito para apoyarte, pero déjame verificarlo."

        self.extraction_task = "Crea un escenario basado en estas respuestas."
        self.extraction_prompt_template = self.generate_extraction_prompt_template(config["summaries"])
        self.summary_keys = list(config["summaries"]["questions"].keys())
        self.extraction_adaptation_prompt_template = self.generate_adaptation_prompt_template()

        self.personas = [persona.strip() for persona in list(config["summaries"]["personas"].values())]
        self.one_shot = self.generate_one_shot(config["example"])

        self.main_prompt_template = self.generate_main_prompt_template(config["summaries"]["questions"])


    def generate_questions_prompt_template(self, data_collection):

        questions_prompt = f"{data_collection['persona']}\n\nTu objetivo es recopilar respuestas estructuradas para las siguientes preguntas:\n\n"

        for count, question in enumerate(data_collection["questions"]):
            questions_prompt += f"{count+1}. {question}\n"

        questions_prompt += (
            f"\nHaz cada pregunta de una en una. {data_collection['language_type']} "
            "Asegúrate de obtener al menos una respuesta básica para cada pregunta antes de pasar a la siguiente. "
            "Nunca respondas por la persona. "
            "Si no estás seguro de lo que la persona quiso decir, vuelve a preguntar. "
            f"{data_collection['topic_restriction']}"
        )

        n_questions = len(data_collection["questions"])
        if n_questions == 1:
            questions_prompt += "\n\nUna vez que hayas recopilado la respuesta a la pregunta"
        else:
            questions_prompt += f"\n\nUna vez que hayas recopilado las respuestas a las {n_questions} preguntas"

        questions_prompt += (
            ', detén la conversación y escribe una sola palabra "FINISHED".\n\n'
            "Conversación actual:\n{history}\nHuman: {input}\nAI:"
        )

        return questions_prompt


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
            "Si no conoces el valor de un atributo que se te pide extraer, devuelve null para el valor de ese atributo.\n\n"
            f"Vas a producir un JSON con las siguientes claves: {keys_string}.\n\n"
            f"Estas corresponden a la(s) siguiente(s) pregunta(s):\n"
        )

        for count, question in enumerate(summaries["questions"].values()):
            extraction_prompt += f"{count+1}: {question}\n"

        extraction_prompt += (
            "\nMensaje hasta la fecha: {conversation_history}\n\n"
            "Recuerda, solo extrae texto que esté en los mensajes de arriba y no lo cambies. "
        )

        return extraction_prompt


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


    def generate_one_shot(self, example):

        one_shot = f"Ejemplo:\n{example['conversation']}"
        one_shot += f"\nEl escenario basado en estas respuestas: \"{example['scenario'].strip()}\""

        return one_shot


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
