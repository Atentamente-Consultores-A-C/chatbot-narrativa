import streamlit as st

# MUST BE FIRST
st.set_page_config(page_title="Study bot", page_icon="📖")
st.image("atentamente_logo.svg")

import os
import sys
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain.chains import ConversationChain
from langchain_openai import ChatOpenAI
from langchain.output_parsers.json import SimpleJsonOutputParser
from langsmith import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from llm_config_espanol import LLMConfig

# === Load environment variables from Streamlit secrets ===
os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_PROJECT"] = st.secrets["LANGCHAIN_PROJECT"]
os.environ["LANGCHAIN_TRACING_V2"] = st.secrets["LANGCHAIN_TRACING_V2"]
os.environ["LANGSMITH_ENDPOINT"] = st.secrets["LANGCHAIN_ENDPOINT"]

# === Google Sheets ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"], scope
)
gs_client = gspread.authorize(credentials)

try:
    sheet = gs_client.open("micronarrativas_atentamenteBot").sheet1
except Exception as e:
    st.error(f"❌ No se pudo abrir la hoja de cálculo: {e}")
    st.stop()

def load_custom_css(path="style.css"):
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_custom_css()

input_args = sys.argv[1:]
config_file = input_args[0] if input_args else st.secrets.get("CONFIG_FILE", "config_natalia_v0.1_teachers.toml")
llm_prompts = LLMConfig(config_file)

smith_client = Client()

def init_session():
    defaults = {
        'run_id': None,
        'agentState': 'start',
        'consent': False,
        'exp_data': True,
        'llm_model': "gpt-4o",
        'final_response': None,
        'waiting_for_listo': True,
        'micronarrativas': [],
        'vista_final': False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

openai_api_key = st.secrets["OPENAI_API_KEY"]
msgs = StreamlitChatMessageHistory(key="langchain_messages")
memory = ConversationBufferMemory(memory_key="history", chat_memory=msgs)

if st.session_state.llm_model == "gpt-4o":
    prompt_datacollection = llm_prompts.questions_prompt_template

chat = ChatOpenAI(temperature=0.3, model=st.session_state.llm_model, openai_api_key=openai_api_key)
prompt_updated = PromptTemplate(input_variables=["history", "input"], template=prompt_datacollection)
conversation = ConversationChain(prompt=prompt_updated, llm=chat, verbose=True, memory=memory)

if not st.session_state['consent']:
    with st.container():
        st.markdown(llm_prompts.intro_and_consent)
        st.button("He leído, entiendo", key="consent_button", on_click=lambda: st.session_state.update({"consent": True}))
    st.stop()

if st.session_state.vista_final:
    st.markdown("## 🎉 ¡Gracias por participar!")
    st.markdown("Esta es la narrativa final que elegiste o editaste:")
    st.markdown(f"> {st.session_state.final_response}")

    st.markdown("---")
    st.markdown("### 📝 ¿Nos ayudas con tu opinión?")
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

entry_messages = st.expander("🗣️ Conversación", expanded=st.session_state['exp_data'])

if not msgs.messages:
    msgs.add_ai_message(llm_prompts.questions_intro)

with entry_messages:
    for m in msgs.messages:
        with st.chat_message(m.type):
            st.markdown(f"<span style='color:black'>{m.content}</span>", unsafe_allow_html=True)

if st.session_state.agentState == "select_micronarrative":
    st.subheader("✨ Elige la narrativa que más se parece a tu experiencia")
    st.markdown("A continuación te voy a presentar 3 narrativas que pienso que describen tu situación, elige la narrativa que mejor describa tu experiencia. Ya que la hayas elegido, la podemos refinar.")

    st.components.v1.html("""
        <script>
            window.addEventListener('load', function() {
                setTimeout(function() {
                    window.scrollTo(0, document.body.scrollHeight);
                }, 300);
            });
        </script>
    """, height=0)

    cols = st.columns(len(st.session_state.micronarrativas))

    for idx, (col, texto) in enumerate(zip(cols, st.session_state.micronarrativas)):
        with col:
            st.markdown(f"**Opción {idx + 1}**")
            st.text_area(
                label="",
                value=texto,
                height=200,
                key=f"narrativa_col_{idx}",
                disabled=True,
                label_visibility="collapsed"
            )
            if st.button("✅ Elegir versión", key=f"elegir_col_{idx}"):
                st.session_state.final_response = texto
                st.session_state.agentState = "summarise"
                st.success("Narrativa seleccionada.")
                st.rerun()

else:
    if st.session_state.agentState != "summarise" or not st.session_state.final_response:
        prompt = st.chat_input()
        if prompt:
            with entry_messages:
                st.chat_message("human").markdown(f"<span style='color:black'>{prompt}</span>", unsafe_allow_html=True)

                if st.session_state['waiting_for_listo']:
                    if prompt.strip().lower() == "listo":
                        st.session_state['waiting_for_listo'] = False
                        with st.spinner("💭 Pensando..."):
                            response = conversation.invoke(input=prompt)
                        st.chat_message("ai").markdown(f"<span style='color:black'>{response['response']}</span>", unsafe_allow_html=True)
                    else:
                        st.warning("🔒 Para comenzar, por favor escribe la palabra **\"listo\"**.")
                else:
                    with st.spinner("💭 Pensando..."):
                        response = conversation.invoke(input=prompt)
                    if "Gracias!" in response['response']:
                        summary_prompt = PromptTemplate.from_template(llm_prompts.main_prompt_template)
                        parser = SimpleJsonOutputParser()
                        chain = summary_prompt | chat | parser
                        full_history = "\n".join([f"{m.type.upper()}: {m.content}" for m in msgs.messages])
                        summary_input = {key: full_history for key in llm_prompts.summary_keys}
                        micronarrativas = []
                        for persona in llm_prompts.personas:
                            with st.spinner(f"💭 Generando narrativas"):
                                result = chain.invoke({
                                    "persona": persona,
                                    "one_shot": llm_prompts.one_shot,
                                    "end_prompt": llm_prompts.extraction_task,
                                    **summary_input
                                })
                            micronarrativas.append(result['output_scenario'])
                        st.session_state.micronarrativas = micronarrativas
                        st.session_state.agentState = "select_micronarrative"
                        st.rerun()
                    else:
                        st.chat_message("ai").markdown(f"<span style='color:black'>{response['response']}</span>", unsafe_allow_html=True)

    if st.session_state.agentState == "summarise" and st.session_state.final_response:
        st.subheader("📄 Tu historia en tus propias palabras")
        st.markdown("Gracias por compartir esto, nos ayuda a entender las problemáticas que enfrentan los educadores. Si quieres, puedes copiar esta narrativa para ti mismo o mejorarla con la IA.")
        new_text = st.text_area("✍️ Edita tu micronarrativa si lo deseas", value=st.session_state.final_response, height=250)

        if st.button("✅ Guardar versión final"):
            st.session_state.final_response = new_text
            try:
                sheet.append_row([new_text, datetime.now().isoformat()])
            except Exception as e:
                st.error(f"❌ Error al guardar en Google Sheets: {e}")
            st.session_state.vista_final = True
            st.rerun()

        with st.container():
            st.markdown("### ✨ ¿Quieres mejorar tu narrativa con ayuda de la IA?")
            with st.expander("🛠️ Haz clic aquí para adaptar tu texto con la IA", expanded=True):
                st.chat_message("ai").markdown("¿Qué podríamos mejorar o cambiar en tu narrativa?")
                adaptation_input = st.chat_input("Escribe cómo quieres mejorarla...")
                if adaptation_input:
                    st.chat_message("human").markdown(adaptation_input)

                    placeholder = st.empty()
                    with placeholder.container():
                        st.chat_message("ai").markdown("💭 Estoy generando una versión mejorada...")

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

                    if st.button("✅ Usar versión sugerida"):
                        st.session_state.final_response = improved['new_scenario']
                        st.success("Narrativa actualizada con la sugerencia de IA.")
