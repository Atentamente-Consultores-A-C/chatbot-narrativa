import streamlit as st

# === CONFIGURACIÓN INICIAL DE LA APP ===
st.set_page_config(page_title="Study bot", page_icon="📖")  # Configura título y favicon
st.image("atentamente_logo.svg")  # Muestra logo del proyecto

import os
import sys
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain.memory.buffer import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_openai import ChatOpenAI
from langchain.output_parsers.json import SimpleJsonOutputParser
from langsmith import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from llm_config_espanol import LLMConfig  # Maneja configuración de prompts desde TOML

# === CARGA DE VARIABLES DE ENTORNO DESDE STREAMLIT SECRETS ===
os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_PROJECT"] = st.secrets["LANGCHAIN_PROJECT"]
os.environ["LANGCHAIN_TRACING_V2"] = st.secrets["LANGCHAIN_TRACING_V2"]
os.environ["LANGSMITH_ENDPOINT"] = st.secrets["LANGCHAIN_ENDPOINT"]

# === CONEXIÓN CON GOOGLE SHEETS COMO MOCK DE BASE DE DATOS ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"], scope
)
gs_client = gspread.authorize(credentials)

# Verifica si la hoja existe, si falla detiene la app
try:
    sheet = gs_client.open("micronarrativas_atentamenteBot").sheet1
except Exception as e:
    st.error(f"❌ No se pudo abrir la hoja de cálculo: {e}")
    st.stop()

# === CARGA DE ESTILOS CSS PERSONALIZADOS ===
def load_custom_css(path="style.css"):
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_custom_css()

# === CONFIGURACIÓN DEL ARCHIVO TOML Y LLM ===
input_args = sys.argv[1:]
config_file = input_args[0] if input_args else st.secrets.get("CONFIG_FILE", "config_natalia_v0.1_teachers.toml")
llm_prompts = LLMConfig(config_file)  # Carga prompts, plantillas y personalidades desde TOML

smith_client = Client()  # Cliente para LangSmith (trazabilidad y debugging)

# === INICIALIZACIÓN DEL ESTADO DE SESIÓN ===
def init_session():
    defaults = {
        'run_id': None,
        'agentState': 'start',        # Estado de la conversación (start → chat → select_micronarrative → summarise1 → reflect → sliders → abcd → summarise2 → end)
        'consent': False,             # Controla si el usuario aceptó el consentimiento
        'summarise1': False,
        'reflect': False,
        'sliders': False,
        'abcd': False,
        'summarise2': False,
        'exp_data': True,             # Controla si se expande la conversación
        'llm_model': "gpt-4.1-mini",  # Modelo LLM
        'primer_porque': None,       # Almacena la primera narrativa final elegida/editada
        'segundo_porque': None,       # Almacena la segunda narrativa final elegida/editada
        'waiting_for_listo': True,    # Controla el paso previo a iniciar generación
        'micronarrativas': [],        # Guarda las 3 narrativas generadas
        'persona_elegida_idx': 4,
        'vista_final': False,         # Determina si ya se muestra la narrativa final
        'ai_used': False,             # Permite mostrar o no el chat input del recuadro de mejora con IA
        'ai_used2': False,             # Permite mostrar o no el chat input del recuadro de mejora con IA
        'abcd_tie_options': [],
        'await_pick_top': False,
        'abcd_top': "atencion",
        'abcd_ratings': { "atencion": 3, "bondad": 3, "claridad": 3, "direccion": 3},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# === CONFIGURACIÓN DE LLM Y MEMORIA DE CONVERSACIÓN ===
openai_api_key = st.secrets["OPENAI_API_KEY"]

msgs_questions = StreamlitChatMessageHistory(key="langchain_messages")  # Historial de mensajes para LangChain
memory_questions = ConversationBufferMemory(
    memory_key="history", input_key="input", chat_memory=msgs_questions
)

msgs_reflect = StreamlitChatMessageHistory(key="reflect_messages")
memory_reflect = ConversationBufferMemory(
    memory_key="history", input_key="input", chat_memory=msgs_reflect
)

msgs_abcd = StreamlitChatMessageHistory(key="abcd_messages")
memory_abcd = ConversationBufferMemory(
    memory_key="history", input_key="input", chat_memory=msgs_abcd
)

chat = ChatOpenAI(temperature=0.3, model=st.session_state.llm_model, openai_api_key=openai_api_key)

# === FLUJO: PANTALLA DE CONSENTIMIENTO ===
if not st.session_state.consent:
    with st.container():
        st.markdown(llm_prompts.intro_and_consent)  # Texto inicial desde TOML
        st.button("He leído, entiendo", key="consent_button", on_click=lambda: st.session_state.update({"consent": True}))
    st.stop()  # Detiene ejecución hasta aceptar

# === FLUJO: PANTALLA FINAL ===
if st.session_state.vista_final:
    st.markdown("#### Has llegado al final de la creación de tu narrativa con nuestro chatbot para maestros y maestras")
    st.markdown("**Tu narrativa se guardó correctamente**. Esperamos que este ejercicio te haya ayudado a ver tu situación con más claridad. Si deseas guardarla para ti, copia el texto antes de salir, porque aquí se borrará. Recuerda que tu información es confidencial y no será compartida con nadie.  \n")
    st.markdown("Esta es la narrativa final de la situación:")
    st.markdown(f"> {st.session_state.primer_porque}")

    st.markdown("Pero esa no es la historia completa.\nEsto es lo que estaba pasando en tu mente realmente:")
    st.markdown(f"> {st.session_state.segundo_porque}")

    st.markdown("##### 🎉 ¡Gracias por participar! ")


    st.markdown("---")
    st.markdown("#### Tu experiencia es muy valiosa para nosotros 🙌")
    st.markdown("Antes de terminar, nos encantaría que nos ayudes a completar esta breve encuesta de retroalimentación para mejorar el chatbot.")
    st.markdown(
        """
        <a href="https://forms.gle/pxBtvu8WPRAort7b7" target="_blank">
            <button style="background-color:#ec6041; color:white; padding:0.75rem 1.5rem; border:none; border-radius:12px; font-size:16px; cursor:pointer;">
                Ir a encuesta de retroalimentación
            </button>
        </a>
        """,
        unsafe_allow_html=True
    )

    st.markdown("\n")
    st.markdown("**Cuando termines de responder la encuesta y/o desees terminar la sesión, da clic en el botón \"Listo\".**")
    if st.button("Listo", key="reset_button"):
        # Reiniciar estado para volver a pantalla de consentimiento
        st.session_state.clear()
        st.rerun()
    st.stop()


# === FLUJO: CHAT PRINCIPAL ===
elif not st.session_state.vista_final:

    if st.session_state.abcd_top == "atencion":
        abcd_prompt_template = llm_prompts.a_prompt_template
        lp_intro = llm_prompts.a_intro
    elif st.session_state.abcd_top == "bondad":
        abcd_prompt_template = llm_prompts.b_prompt_template
        lp_intro = llm_prompts.b_intro
    elif st.session_state.abcd_top == "claridad":
        abcd_prompt_template = llm_prompts.c_prompt_template
        lp_intro = llm_prompts.c_intro
    else:
        abcd_prompt_template = llm_prompts.d_prompt_template
        lp_intro = llm_prompts.d_intro

    # === FLUJO: MOSTRAR HISTORIAL DE CONVERSACIÓN ===
    entry_messages_questions = st.expander("🗣️ Tus experiencias", expanded=st.session_state['exp_data'])
    if not msgs_questions.messages:
            msgs_questions.add_ai_message(llm_prompts.questions_intro)  # Primer mensaje del bot
    with entry_messages_questions:
        for m in msgs_questions.messages:
            with st.chat_message(m.type):
                st.markdown(f"<span style='color:black'>{m.content}</span>", unsafe_allow_html=True)

    if not st.session_state.agentState in ("select_micronarrative", "summarise1", "reflect", "sliders", "abcd", "summarise2"):
        prompt_questions = st.chat_input("Escribe aquí")
        if prompt_questions:
            with entry_messages_questions:
                st.chat_message("human").markdown(f"<span style='color:black'>{prompt_questions}</span>", unsafe_allow_html=True)

                # Cadena principal del chat
                conversation_questions = LLMChain(
                    llm=chat,
                    prompt=PromptTemplate(
                        input_variables=["history", "input"],
                        template=llm_prompts.questions_prompt_template
                    ),
                    memory=memory_questions,
                    verbose=True
                )

                # Genera respuesta del bot
                with st.spinner("💭 Pensando..."):
                    response = conversation_questions.invoke({"input": prompt_questions})

                final_message = response['text']
                # Si llega el trigger "Gracias!" pasa a generación de micronarrativas
                if "Gracias!" in final_message:
                    final_message += " A continuación te voy a presentar 3 narrativas que pienso que describen tu situación, elige la narrativa que mejor describa tu experiencia. Ya que la hayas elegido, la podemos refinar."

                st.chat_message("ai").markdown(f"<span style='color:black'>{final_message}</span>", unsafe_allow_html=True)

                # === GENERACIÓN DE MICRONARRATIVAS ===
                if "Gracias!" in response['text']:
                    summary_prompt = PromptTemplate.from_template(llm_prompts.main_prompt_template)
                    parser = SimpleJsonOutputParser()
                    chain = summary_prompt | chat | parser
                    full_history = "\n".join([f"{m.type.upper()}: {m.content}" for m in msgs_questions.messages])
                    summary_input = {key: full_history for key in llm_prompts.summary_keys}
                    micronarrativas = []

                    # Genera una narrativa por cada personalidad definida en TOML
                    for persona in llm_prompts.personas:
                        with st.spinner(f"💭 Generando narrativas"):
                            result = chain.invoke({
                                "persona": persona,
                                "one_shot": llm_prompts.one_shot,
                                "end_prompt": llm_prompts.extraction_task,
                                **summary_input
                            })
                        micronarrativas.append(result['output_scenario'])

                    # Guarda narrativas y cambia de estado
                    st.session_state.micronarrativas = micronarrativas
                    st.session_state.agentState = "select_micronarrative"

                    st.rerun()


    # === FLUJO: SELECCIÓN DE MICRONARRATIVAS ===
    if st.session_state.agentState == "select_micronarrative":
        st.subheader("✨ Elige la narrativa que mejor describe tu experiencia")

        # Mostrar cada narrativa en una columna
        cols = st.columns(len(st.session_state.micronarrativas))
        for idx, (col, texto) in enumerate(zip(cols, st.session_state.micronarrativas)):
            with col:
                st.markdown(f"**Opción {idx + 1}**")
                st.markdown(
                    f"""
                    <textarea readonly tabindex="-1"
                            style="
                                width:100%; 
                                height:800px; 
                                font-weight:normal; 
                                color:#333; 
                                background-color:white; 
                                border:1px solid #ccc; 
                                border-radius:12px; 
                                padding:12px; 
                                resize:none;
                                box-sizing:border-box;
                                outline: none;
                                user-select: none;">
                    {texto}
                    </textarea>
                    """,
                    unsafe_allow_html=True
                )
                # Botón para seleccionar narrativa
                if st.button("Elegir versión", key=f"elegir_col_{idx}"):
                    st.session_state.persona_elegida_idx = idx
                    st.session_state.primer_porque = texto
                    st.session_state.summarise1 = True
                    st.session_state.agentState = "summarise1"
                    st.success("Narrativa seleccionada.")
                    st.rerun()

    # === FLUJO: RESUMEN Y EDICIÓN 1 ===
    if st.session_state.summarise1 and st.session_state.primer_porque:
        st.subheader("📄 Tu historia en tus propias palabras")
        st.markdown("Ha llegado la hora de personalizar aún más tu narrativa.")
        guardar_final = False

        # === OPCIÓN DE MEJORA CON IA ===
        st.markdown("##### ✨ ¿Quieres mejorar tu narrativa con ayuda de la Inteligencia Artificial?")
        st.markdown("Si lo deseas, aquí le puedes pedir a la Inteligencia Artificial que te ayude a cambiar el texto.  \n"
                    "**Por ejemplo:** puedes pedirle que te ayude a agregar lo que falte, quitar lo que no quieras o cambiar el tono.")
        with st.expander("🛠️ Haz clic aquí para adaptar tu texto con la Inteligencia Artificial", expanded=False):
            first_ai_message = (f"Aquí puedes refinar la narrativa que elegiste:\n\n> {st.session_state.primer_porque}\n\n")
            st.markdown(first_ai_message)
            st.markdown("Los cambios que hagas se guardarán en la caja de texto de abajo, donde podrás editar manualmente en el momento que quieras.")

            # Inicializa variables de sesión para este subchat
            if "adapted_response" not in st.session_state:
                st.session_state.adapted_response = st.session_state.primer_porque
            if "adaptation_messages" not in st.session_state:
                st.session_state.adaptation_messages = []

            # Mostrar historial de mejoras
            for m in st.session_state.adaptation_messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            adaptation_input = st.chat_input("Escribe cómo quieres mejorar tu narrativa...")
            if adaptation_input:
                st.session_state.adaptation_messages.append({"role": "human", "content": adaptation_input})
                with st.chat_message("human"):
                    st.markdown(adaptation_input)

                st.session_state.ai_used = True
                # Prompt para adaptar narrativa sobre la última versión
                adaptation_prompt = PromptTemplate(
                    input_variables=["input", "scenario"],
                    template=llm_prompts.extraction_adaptation_prompt_template
                )
                parser = SimpleJsonOutputParser()
                chain = adaptation_prompt | chat | parser

                with st.spinner("💭 Generando versión mejorada..."):
                    improved = chain.invoke({
                        "scenario": st.session_state.adapted_response,
                        "input": adaptation_input
                    })

                # Actualiza narrativa adaptada
                st.session_state.adapted_response = improved["new_scenario"]

                ai_message = (f"**Versión sugerida:**\n\n> {st.session_state.adapted_response}\n\n"
                                "Si ya ves bien esta versión, **guárdala con el botón de abajo**.\n\n"
                                "Si no, puedes seguir editando con IA o manualmente con el cuadro de texto de abajo.")
                st.session_state.adaptation_messages.append({"role": "ai", "content": ai_message})
                with st.chat_message("ai"):
                    st.markdown(ai_message)
                st.rerun()
        
        st.markdown("\n\n\n\n")
        # Usuario puede editar la narrativa final
        new_text = st.text_area("✍️ Aquí puedes editar manualmente lo que quieras, para que quede más claro lo que estás viviendo.\n\nSi quieres hacer más cambios con la Inteligencia Artificial, puedes hacerlo arriba y se irán reflejando aquí.\n\nSi no, puedes guardar la versión final dando clic al botón \"Guardar versión final\".", value=st.session_state.adapted_response, height=250)
        st.session_state.adapted_response = new_text

        # === BOTÓN DE GUARDADO FINAL (después de la sección de IA) ===
        if st.session_state.agentState == "summarise1":
            if st.button("✅ Guardar versión final"):
                    guardar_final = True

        # Guarda en Google Sheets y pasa a vista final
        if guardar_final:
            if st.session_state.ai_used:
                new_text = st.session_state.adapted_response
            st.session_state.primer_porque = new_text

            try:
                sheet.append_row([new_text, datetime.now().isoformat()])
            except Exception as e:
                st.error(f"❌ Error al guardar en Google Sheets: {e}")
            
            st.session_state.reflect = True
            st.session_state.agentState = "reflect"
            st.rerun()
    
    if st.session_state.reflect:

        entry_messages_reflect = st.expander("🗣️ Tu reflexión", expanded=st.session_state['exp_data'])
        if not msgs_reflect.messages:
                msgs_reflect.add_ai_message(llm_prompts.reflect_intro)  # Primer mensaje del bot
        with entry_messages_reflect:
            for m in msgs_reflect.messages:
                with st.chat_message(m.type):
                    st.markdown(f"<span style='color:black'>{m.content}</span>", unsafe_allow_html=True)

        if st.session_state.agentState == "reflect":
            prompt_reflect = st.chat_input("Escribe aquí")
            if prompt_reflect:
                with entry_messages_reflect:
                    st.chat_message("human").markdown(f"<span style='color:black'>{prompt_reflect}</span>", unsafe_allow_html=True)

                    reflect_prompt_complete = (
                        "Esta es la experiencia de una persona:\n\n"
                        f"< {st.session_state.primer_porque} >\n\n"
                        f"{llm_prompts.reflect_prompt_template}\n\n"
                    )

                    # Cadena principal del chat
                    conversation_reflect = LLMChain(
                        llm=chat,
                        prompt=PromptTemplate(
                            input_variables=["history", "input"],
                            template=reflect_prompt_complete
                        ),
                        memory=memory_reflect,
                        verbose=True
                    )

                    # Genera respuesta del bot
                    with st.spinner("💭 Pensando..."):
                        response = conversation_reflect.invoke({"input": prompt_reflect})

                    final_message = response['text']
                    # Si llega el trigger "Gracias!" pasa a generación de micronarrativas
                    if "Gracias!" in final_message:
                        final_message += llm_prompts.reflect_outro
                    st.chat_message("ai").markdown(f"<span style='color:black'>{final_message}</span>", unsafe_allow_html=True)

                    # === GENERACIÓN DE SLIDERS ===
                    if "Gracias!" in response['text']:
                        # Cambia de estado
                        st.session_state.sliders = True
                        st.session_state.agentState = "sliders"

                        st.rerun()
    
    # === FLUJO: SLIDERS DE ABCD ===
    if st.session_state.sliders:
        st.subheader("🧠 Las 4 cualidades del entrenamiento mental")
        st.markdown("Te mostraré una breve descripción de cada desequilibrio, y tú me dirás qué tanto sientes que estuvo presente en tu mente en ese momento.  \n"
                    "👉 Usa una escala del 1 al 5 (1 = para nada, 5 = muy presente).")
        
        def render_dim(dim_key, key_suffix, col):
            d = llm_prompts.abcd_dims[dim_key]
            with col:
                st.markdown(f"##### **{d['title']}**")
                if d["desc"]:
                    st.markdown(d["desc"])
                st.session_state.abcd_ratings[dim_key] = st.slider(
                    llm_prompts.abcd_ui["slider_label"],
                    1, 5,
                    st.session_state.abcd_ratings[dim_key],
                    key=f"rate_{key_suffix}"
                )

        # Fila 1: Atención | Bondad
        c1, c2 = st.columns(2)  # puedes ajustar widths: st.columns([1,1])
        render_dim("atencion", "atencion", c1)
        render_dim("bondad", "bondad", c2)

        # Fila 2: Claridad | Dirección
        c3, c4 = st.columns(2)
        render_dim("claridad", "claridad", c3)
        render_dim("direccion", "direccion", c4)

        st.markdown("\n\n")  # pequeño espacio

        if st.session_state.await_pick_top and st.session_state.abcd_tie_options:
            st.info("Hay más de un desequilibrio con la calificación más alta.\n\nPor favor, elige en cuál quisieras profundizar:")
            opts = st.session_state.abcd_tie_options
            cols = st.columns(len(opts))
            for col, k in zip(cols, opts):
                with col:
                    title = llm_prompts.abcd_dims[k]["title"].replace(" en desequilibrio", "")
                    if st.button(title, key=f"pick_{k}"):
                        st.session_state.abcd_top = k
                        st.session_state.abcd = True
                        st.session_state.agentState = "abcd"
                        st.session_state.await_pick_top = False
                        st.session_state.abcd_tie_options = []
                        st.success(f"Profundizaremos en: {title}")
                        st.rerun()
            st.stop()
        
        if st.session_state.agentState == "sliders":
            if st.button("Guardar y continuar ➡️"):
                r = {
                        "atencion":  int(st.session_state.abcd_ratings["atencion"] or 0),
                        "bondad":    int(st.session_state.abcd_ratings["bondad"] or 0),
                        "claridad":  int(st.session_state.abcd_ratings["claridad"] or 0),
                        "direccion": int(st.session_state.abcd_ratings["direccion"] or 0),
                    }
                
                max_val = max(r.values())
                empate = [k for k, v in r.items() if v == max_val]

                if len(empate) == 1:
                    st.session_state.abcd_top = empate[0]
                    st.session_state.abcd = True
                    st.session_state.agentState = "abcd"
                    st.success("Calificaciones guardadas")
                    st.rerun()
                else:
                    # Caso con empate: guardar opciones y pedir elección
                    st.session_state.abcd_tie_options = empate
                    st.session_state.await_pick_top = True
                    st.rerun()

                # order = llm_prompts.abcd_ui["tie_break_order"]
                # st.session_state.abcd_top = max(order, key=lambda k: (r[k], -order.index(k)))

                # st.session_state.abcd = True
                # st.session_state.agentState = "abcd"
                # st.success("Calificaciones guardadas")
                # st.rerun()
    
    if st.session_state.abcd:

        entry_messages_abcd = st.expander("🗣️ Los desequilibrios en la mente", expanded=st.session_state['exp_data'])
        if not msgs_abcd.messages:
                msgs_abcd.add_ai_message(lp_intro)  # Primer mensaje del bot
        with entry_messages_abcd:
            for m in msgs_abcd.messages:
                with st.chat_message(m.type):
                    st.markdown(f"<span style='color:black'>{m.content}</span>", unsafe_allow_html=True)

        if st.session_state.agentState == "abcd":
            prompt_abcd = st.chat_input("Escribe aquí")
            if prompt_abcd:
                with entry_messages_abcd:
                    st.chat_message("human").markdown(f"<span style='color:black'>{prompt_abcd}</span>", unsafe_allow_html=True)

                    # Cadena principal del chat
                    conversation_abcd = LLMChain(
                        llm=chat,
                        prompt=PromptTemplate(
                            input_variables=["history", "input"],
                            template=abcd_prompt_template
                        ),
                        memory=memory_abcd,
                        verbose=True
                    )

                    # Genera respuesta del bot
                    with st.spinner("💭 Pensando..."):
                        response = conversation_abcd.invoke({"input": prompt_abcd})

                    final_message = response['text']
                    # Si llega el trigger "Gracias!" pasa a generación de micronarrativas
                    if "Gracias!" in final_message:
                        final_message += llm_prompts.abcd_outro
                    st.chat_message("ai").markdown(f"<span style='color:black'>{final_message}</span>", unsafe_allow_html=True)

                    msgs_joined = StreamlitChatMessageHistory(key="joined_messages")
                    for m in msgs_reflect.messages:
                        if m.type == "ai":
                            msgs_joined.add_ai_message(m.content)
                        elif m.type == "human":
                            msgs_joined.add_user_message(m.content)
                    for m in msgs_abcd.messages:
                        if m.type == "ai":
                            msgs_joined.add_ai_message(m.content)
                        elif m.type == "human":
                            msgs_joined.add_user_message(m.content)

                    # === GENERACIÓN DE MICRONARRATIVA ===
                    if "Gracias!" in response['text']:
                        summary_prompt = PromptTemplate.from_template(llm_prompts.second_why_prompt)
                        parser = SimpleJsonOutputParser()
                        chain = summary_prompt | chat | parser
                        full_history = "\n".join([f"{m.type.upper()}: {m.content}" for m in msgs_joined.messages])
                        summary_input = {key: full_history for key in llm_prompts.summary_keys}

                        # Genera una narrativa por la misma personalidad elegida previamente
                        with st.spinner(f"💭 Generando narrativa"):
                            result = chain.invoke({
                                "persona": llm_prompts.personas[st.session_state.persona_elegida_idx],
                                "one_shot": llm_prompts.one_shot,
                                "context": st.session_state.primer_porque,
                                **summary_input
                            })
                        st.session_state.segundo_porque = result['output_scenario']
                        # Cambia de estado
                        #st.session_state.vista_final = True
                        st.session_state.summarise2 = True
                        st.session_state.agentState = "summarise2"

                        st.rerun()
    
    # === FLUJO: RESUMEN Y EDICIÓN 2 ===
    if st.session_state.summarise2 and st.session_state.segundo_porque:
        st.subheader("📄 Tu reflexión en tus propias palabras")
        st.markdown("Ha llegado la hora de personalizar aún más tu experiencia interna.")
        guardar_final2 = False

        # === OPCIÓN DE MEJORA CON IA ===
        st.markdown("##### ✨ ¿Quieres mejorar tu reflexión con ayuda de la Inteligencia Artificial?")
        st.markdown("Si lo deseas, aquí le puedes pedir a la Inteligencia Artificial que te ayude a cambiar el texto.  \n"
                    "**Por ejemplo:** puedes pedirle que te ayude a agregar lo que falte, quitar lo que no quieras o cambiar el tono.")
        with st.expander("🛠️ Haz clic aquí para adaptar tu texto con la Inteligencia Artificial", expanded=False):
            first_ai_message = (f"Aquí puedes refinar la narrativa que elegiste:\n\n> {st.session_state.segundo_porque}\n\n")
            st.markdown(first_ai_message)
            st.markdown("Los cambios que hagas se guardarán en la caja de texto de abajo, donde podrás editar manualmente en el momento que quieras.")

            # Inicializa variables de sesión para este subchat
            if "adapted_response2" not in st.session_state:
                st.session_state.adapted_response2 = st.session_state.segundo_porque
            if "adaptation_messages2" not in st.session_state:
                st.session_state.adaptation_messages2 = []

            # Mostrar historial de mejoras
            for m in st.session_state.adaptation_messages2:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            adaptation_input2 = st.chat_input("Escribe cómo quieres mejorar tu reflexión...")
            if adaptation_input2:
                st.session_state.adaptation_messages2.append({"role": "human", "content": adaptation_input2})
                with st.chat_message("human"):
                    st.markdown(adaptation_input2)

                st.session_state.ai_used2 = True
                # Prompt para adaptar narrativa sobre la última versión
                adaptation_prompt = PromptTemplate(
                    input_variables=["input", "scenario"],
                    template=llm_prompts.extraction_adaptation_prompt_template
                )
                parser = SimpleJsonOutputParser()
                chain = adaptation_prompt | chat | parser

                with st.spinner("💭 Generando versión mejorada..."):
                    improved = chain.invoke({
                        "scenario": st.session_state.adapted_response2,
                        "input": adaptation_input2
                    })

                # Actualiza narrativa adaptada
                st.session_state.adapted_response2 = improved["new_scenario"]

                ai_message = (f"**Versión sugerida:**\n\n> {st.session_state.adapted_response2}\n\n"
                                "Si ya ves bien esta versión, **guárdala con el botón de abajo**.\n\n"
                                "Si no, puedes seguir editando con IA o manualmente con el cuadro de texto de abajo.")
                st.session_state.adaptation_messages2.append({"role": "ai", "content": ai_message})
                with st.chat_message("ai"):
                    st.markdown(ai_message)
                st.rerun()
        
        st.markdown("\n\n\n\n")
        # Usuario puede editar la narrativa final
        new_text = st.text_area("✍️ Aquí puedes editar manualmente lo que quieras, para que quede más claro lo que estás viviendo.\n\nSi quieres hacer más cambios con la Inteligencia Artificial, puedes hacerlo arriba y se irán reflejando aquí.\n\nSi no, puedes guardar la versión final dando clic al botón \"Guardar versión final\".", value=st.session_state.adapted_response2, height=250)
        st.session_state.adapted_response2 = new_text

        # === BOTÓN DE GUARDADO FINAL (después de la sección de IA) ===
        if st.session_state.agentState == "summarise2":
            if st.button("✅ Guardar versión final"):
                    guardar_final2 = True

        # Guarda en Google Sheets y pasa a vista final
        if guardar_final2:
            if st.session_state.ai_used2:
                new_text = st.session_state.adapted_response2
            st.session_state.segundo_porque = new_text

            try:
                sheet.append_row([new_text, datetime.now().isoformat()])
            except Exception as e:
                st.error(f"❌ Error al guardar en Google Sheets: {e}")
            
            st.session_state.vista_final = True
            st.session_state.agentState = "end"
            st.rerun()