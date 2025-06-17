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
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree
from streamlit_feedback import streamlit_feedback
import streamlit.components.v1 as components
from functools import partial
from llm_config_espanol import LLMConfig

# === Load environment variables from Streamlit secrets ===
os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_PROJECT"] = st.secrets["LANGCHAIN_PROJECT"]
os.environ["LANGCHAIN_TRACING_V2"] = st.secrets["LANGCHAIN_TRACING_V2"]
os.environ["LANGSMITH_ENDPOINT"] = st.secrets["LANGCHAIN_ENDPOINT"]

# === Load Custom CSS ===
def load_custom_css(path="style.css"):
    with open(path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_custom_css()

# === Parse config file path ===
input_args = sys.argv[1:]
config_file = input_args[0] if input_args else st.secrets.get("CONFIG_FILE", "config_natalia_v0.1_teachers.toml")
print(f"Configuring app using {config_file}...\n")

# === Load prompt config from TOML ===
llm_prompts = LLMConfig(config_file)

# === Debug switch ===
DEBUG = False

# === LangSmith Client ===
smith_client = Client()

# === Initialize session state variables ===
if 'run_id' not in st.session_state: 
    st.session_state['run_id'] = None
if 'agentState' not in st.session_state: 
    st.session_state['agentState'] = "start"
if 'consent' not in st.session_state: 
    st.session_state['consent'] = False
if 'exp_data' not in st.session_state: 
    st.session_state['exp_data'] = True
if 'llm_model' not in st.session_state:
    st.session_state.llm_model = "gpt-4o"
if 'final_response' not in st.session_state:
    st.session_state.final_response = None
if 'waiting_for_listo' not in st.session_state:
    st.session_state['waiting_for_listo'] = True
if 'micronarrativas' not in st.session_state:
    st.session_state['micronarrativas'] = []

# === Load OpenAI API key ===
openai_api_key = st.secrets.get("OPENAI_API_KEY")
if not openai_api_key:
    openai_api_key = st.sidebar.text_input("🔑 Ingresa tu OpenAI API Key", type="password")

if not openai_api_key:
    st.info("Por favor ingresa una OpenAI API Key para continuar.")
    st.stop()

# === Setup LangChain Memory ===
msgs = StreamlitChatMessageHistory(key="langchain_messages")
memory = ConversationBufferMemory(memory_key="history", chat_memory=msgs)

# === Adjust prompt for gpt-4o ===
if st.session_state.llm_model == "gpt-4o":
    prompt_datacollection = llm_prompts.questions_prompt_template

# === Set up LLM instance ===
chat = ChatOpenAI(temperature=0.3, model=st.session_state.llm_model, openai_api_key=openai_api_key)

# === ConversationChain setup ===
prompt_updated = PromptTemplate(input_variables=["history", "input"], template=prompt_datacollection)
conversation = ConversationChain(prompt=prompt_updated, llm=chat, verbose=True, memory=memory)

# === Helper function to extract user responses into structured format ===
def extractChoices():
    extraction_llm = ChatOpenAI(temperature=0.1, model=st.session_state.llm_model, openai_api_key=openai_api_key)
    extraction_template = PromptTemplate(input_variables=["conversation_history"], template=llm_prompts.extraction_prompt_template)
    json_parser = SimpleJsonOutputParser()
    extraction_chain = extraction_template | extraction_llm | json_parser
    return extraction_chain.invoke({"conversation_history": msgs})

# === UI and Conversation flow ===
if st.session_state['consent']:
    entry_messages = st.expander("Collecting your story", expanded=st.session_state['exp_data'])

    if not msgs.messages:
        msgs.add_ai_message(llm_prompts.questions_intro)

    with entry_messages:
        for m in msgs.messages:
            with st.chat_message(m.type):
                st.write(m.content)

    if st.session_state.agentState == "select_micronarrative":
        st.subheader("Elige la narrativa que más se parece a tu experiencia")
        st.markdown("Selecciona una de las siguientes opciones para continuar:")

        for idx, texto in enumerate(st.session_state.micronarrativas):
            with st.container():
                st.text_area(
                    label=f"✍️ Opción {idx + 1}",
                    value=texto,
                    height=180,
                    key=f"narrativa_{idx}",
                    disabled=True,
                    label_visibility="collapsed"
                )
                if st.button("✅ Elegir versión", key=f"elegir_{idx}"):
                    st.session_state.final_response = texto
                    st.session_state.agentState = "summarise"
                    st.success("Narrativa seleccionada.")
                    st.rerun()

    if st.session_state.agentState == "summarise" and st.session_state.final_response:
        st.subheader("Tu historia en tus propias palabras")
        st.markdown("Aquí tienes la versión final de tu narrativa. Si quieres mejorarla o adaptarla, puedes hacerlo a continuación:")

        new_text = st.text_area("✍️ Edita tu micronarrativa si lo deseas", value=st.session_state.final_response, height=250, label_visibility="visible")

        if st.button("✅ Guardar versión final"):
            st.success("Tu narrativa ha sido actualizada.")
            st.session_state.final_response = new_text

        with st.container():
            st.markdown("### ✨ ¿Quieres mejorar tu narrativa con ayuda de la IA?")
            with st.expander("🔧 Haz clic aquí para adaptar tu texto con la IA", expanded=True):
                st.chat_message("ai").write("¿Qué podríamos mejorar o cambiar en tu narrativa?")
                adaptation_input = st.chat_input("Escribe cómo quieres mejorarla...")
                if adaptation_input:
                    st.chat_message("human").write(adaptation_input)
                    adaptation_prompt = PromptTemplate(input_variables=["input", "scenario"], template=llm_prompts.extraction_adaptation_prompt_template)
                    json_parser = SimpleJsonOutputParser()
                    chain = adaptation_prompt | chat | json_parser
                    with st.spinner('Generando versión mejorada...'):
                        improved = chain.invoke({"scenario": st.session_state.final_response, "input": adaptation_input})
                    st.markdown(f"Versión adaptada sugerida: \n {improved['new_scenario']}")
                    if st.button("✅ Usar versión sugerida"):
                        st.session_state.final_response = improved['new_scenario']
                        st.success("Narrativa actualizada con la sugerencia de IA.")

            st.markdown("---")
            st.markdown("### 📝 Por favor, ¿nos ayudas a responder esta encuesta para poder mejorar el chatbot?")
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

    # === Input always at bottom ===
    prompt = st.chat_input("Escribe tu mensaje aquí")

    if prompt:
        st.chat_message("human").write(prompt)

        if st.session_state['waiting_for_listo']:
            if prompt.strip().lower() == "listo":
                st.session_state['waiting_for_listo'] = False
                response = conversation.invoke(input=prompt)
                st.chat_message("ai").write(response['response'])
            else:
                st.warning("🔒 Para comenzar, por favor escribe la palabra **\"listo\"**.")
        else:
            response = conversation.invoke(input=prompt)
            if "FINISHED" in response['response']:
                cleaned_response = response['response'].replace(
                    "FINISHED", '<span style="color:#c9c9c9;">FINISHED</span>'
                )
                st.chat_message("ai").write(cleaned_response, unsafe_allow_html=True)

                extracted = extractChoices()
                template = PromptTemplate.from_template(llm_prompts.main_prompt_template)
                parser = SimpleJsonOutputParser()
                chain = template | chat | parser

                micronarrativas = []
                for persona in llm_prompts.personas:
                    narrativa = chain.invoke({
                        "persona": persona,
                        "one_shot": llm_prompts.one_shot,
                        "end_prompt": llm_prompts.extraction_task,
                        **extracted
                    })["output_scenario"]
                    micronarrativas.append(narrativa)

                st.session_state.agentState = "select_micronarrative"
                st.session_state.micronarrativas = micronarrativas
                st.rerun()
            else:
                st.chat_message("ai").write(response['response'])

else:
    consent_message = st.container()
    with consent_message:
        st.markdown(llm_prompts.intro_and_consent)
        st.button("He leído, entiendo", key="consent_button", on_click=lambda: st.session_state.update({"consent": True}))
