import streamlit as st

# === CONFIGURACIÓN INICIAL DE LA APP ===
st.set_page_config(page_title="Study bot", page_icon="📖")  # Configura título y favicon
st.image("atentamente_logo.svg")  # Muestra logo del proyecto

import os
import sys
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain.memory import ConversationBufferMemory
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
        'agentState': 'start',        # Estado de la conversación (start → chat → select_micronarrative → summarise)
        'consent': False,             # Controla si el usuario aceptó el consentimiento
        'exp_data': True,             # Controla si se expande la conversación
        'llm_model': "gpt-4o",        # Modelo LLM
        'final_response': None,       # Almacena la narrativa final elegida/editada
        'waiting_for_listo': True,    # Controla el paso previo a iniciar generación
        'micronarrativas': [],        # Guarda las 3 narrativas generadas
        'vista_final': False,         # Determina si ya se muestra la narrativa final
        'usar_sugerida': False,       # Permite usar la narrativa adaptada sugerida
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# === CONFIGURACIÓN DE LLM Y MEMORIA DE CONVERSACIÓN ===
openai_api_key = st.secrets["OPENAI_API_KEY"]
msgs = StreamlitChatMessageHistory(key="langchain_messages")  # Historial de mensajes para LangChain

memory = ConversationBufferMemory(
    memory_key="history", input_key="input", chat_memory=msgs
)

chat = ChatOpenAI(temperature=0.3, model=st.session_state.llm_model, openai_api_key=openai_api_key)
prompt_template_raw = llm_prompts.questions_prompt_template  # Prompt base desde TOML

# === FLUJO: PANTALLA DE CONSENTIMIENTO ===
if not st.session_state['consent']:
    with st.container():
        st.markdown(llm_prompts.intro_and_consent)  # Texto inicial desde TOML
        st.button("He leído, entiendo", key="consent_button", on_click=lambda: st.session_state.update({"consent": True}))
    st.stop()  # Detiene ejecución hasta aceptar

# === FLUJO: PANTALLA FINAL SI YA EXISTE NARRATIVA ===
if st.session_state.vista_final:
    st.markdown("## 🎉 ¡Gracias por participar!")
    st.markdown("Esta es la narrativa final que elegiste o editaste:")
    st.markdown(f"> {st.session_state.final_response}")

    st.markdown("---")
    st.markdown("### Tu experiencia es muy valiosa para nosotros. 🙌")
    st.markdown("Ayúdanos completando esta breve encuesta de retroalimentación para mejorar el chatbot.")
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
    st.stop()

# === FLUJO: MOSTRAR HISTORIAL DE CONVERSACIÓN ===
entry_messages = st.expander("🗣️ Conversación", expanded=st.session_state['exp_data'])
if not msgs.messages:
    msgs.add_ai_message(llm_prompts.questions_intro)  # Primer mensaje del bot

with entry_messages:
    for m in msgs.messages:
        with st.chat_message(m.type):
            st.markdown(f"<span style='color:black'>{m.content}</span>", unsafe_allow_html=True)

# === FLUJO: SELECCIÓN DE MICRONARRATIVAS ===
if st.session_state.agentState == "select_micronarrative":
    st.subheader("✨ Elige la narrativa que más se parece a tu experiencia")

    # Auto scroll al final para mostrar opciones
    # st.components.v1.html("""
    #     <script>
    #         window.addEventListener('load', function() {
    #             setTimeout(function() {
    #                 window.scrollTo(0, document.body.scrollHeight);
    #             }, 300);
    #         });
    #     </script>
    # """, height=0)

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
                st.session_state.final_response = texto
                st.session_state.agentState = "summarise"
                st.success("Narrativa seleccionada.")
                st.rerun()

# === FLUJO: CHAT PRINCIPAL ===
elif not st.session_state.agentState in ("summarise", "select_micronarrative") and not st.session_state.vista_final:
    prompt = st.chat_input()
    if prompt:
        with entry_messages:
            st.chat_message("human").markdown(f"<span style='color:black'>{prompt}</span>", unsafe_allow_html=True)

            # Controla transición tras mensaje "listo"
            if st.session_state['waiting_for_listo']:
                if prompt.strip().lower() == "listo":
                    st.session_state['waiting_for_listo'] = False

            # Cadena principal del chat
            conversation = LLMChain(
                llm=chat,
                prompt=PromptTemplate(
                    input_variables=["history", "input"],
                    template=prompt_template_raw
                ),
                memory=memory,
                verbose=True
            )

            # Genera respuesta del bot
            with st.spinner("💭 Pensando..."):
                response = conversation.invoke({"input": prompt})

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
                full_history = "\n".join([f"{m.type.upper()}: {m.content}" for m in msgs.messages])
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

# === FLUJO: RESUMEN Y EDICIÓN FINAL ===
if st.session_state.agentState == "summarise" and st.session_state.final_response:
    st.subheader("📄 Tu historia en tus propias palabras")
    guardar_final = False

    # Si se usa la sugerida automáticamente, se guarda
    if st.session_state.usar_sugerida:
        new_text = st.session_state.final_response
        st.session_state.usar_sugerida = False
        guardar_final = True
    else:
        # Usuario puede editar la narrativa final
        new_text = st.text_area("✍️ Edita tu micronarrativa si lo deseas", value=st.session_state.final_response, height=250)

    # === OPCIÓN DE MEJORA CON IA ===
    with st.container():
        st.markdown("### ✨ ¿Quieres mejorar tu narrativa con ayuda de la Inteligencia Artificial?")
        with st.expander("🛠️ Haz clic aquí para adaptar tu texto con la Inteligencia Artificial", expanded=False):
            st.chat_message("ai").markdown(
                "Aquí puedes refinar la narrativa que elegiste..."
            )
            adaptation_input = st.chat_input("Escribe cómo quieres mejorarla...")
            if adaptation_input:
                st.chat_message("human").markdown(adaptation_input)

                placeholder = st.empty()
                with placeholder.container():
                    st.chat_message("ai").markdown("💭 Estoy generando una versión mejorada...")

                # Prompt para adaptar narrativa
                adaptation_prompt = PromptTemplate(
                    input_variables=["input", "scenario"],
                    template=llm_prompts.extraction_adaptation_prompt_template
                )
                parser = SimpleJsonOutputParser()
                chain = adaptation_prompt | chat | parser

                with st.spinner('Generando versión mejorada...'):
                    improved = chain.invoke({"scenario": st.session_state.final_response, "input": adaptation_input})

                placeholder.empty()
                st.chat_message("ai").markdown(f"**Versión adaptada sugerida:**\n\n> {improved['new_scenario']}")
                st.chat_message("ai").markdown(
                    "**Si ves bien esta narrativa cómo está, puedes copiarla para ti. Espero que te haya ayudado a tener mayor claridad.**"
                )

    # === BOTÓN DE GUARDADO FINAL (después de la sección de IA) ===
    if not st.session_state.usar_sugerida:
        if st.button("✅ Guardar versión final"):
            guardar_final = True

    # Guarda en Google Sheets y pasa a vista final
    if guardar_final:
        st.session_state.final_response = new_text
        try:
            sheet.append_row([new_text, datetime.now().isoformat()])
        except Exception as e:
            st.error(f"❌ Error al guardar en Google Sheets: {e}")
        st.session_state.vista_final = True
        st.rerun()
