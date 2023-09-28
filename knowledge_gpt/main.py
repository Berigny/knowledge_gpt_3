import streamlit as st

from knowledge_gpt.ui import (
    wrap_doc_in_html,
    is_query_valid,
    is_file_valid,
    is_open_ai_key_valid,
    display_file_read_error,
)

from knowledge_gpt.core.caching import bootstrap_caching

from knowledge_gpt.core.parsing import read_file
from knowledge_gpt.core.chunking import chunk_file
from knowledge_gpt.core.embedding import embed_files
from knowledge_gpt.core.qa import query_folder
from knowledge_gpt.core.utils import get_llm

# Initialize session state if it doesn't exist
if 'processed' not in st.session_state:
    st.session_state['processed'] = False

if 'queried' not in st.session_state:
    st.session_state['queried'] = False

EMBEDDING = "openai"
VECTOR_STORE = "faiss"
MODEL_LIST = ["gpt-3.5-turbo", "gpt-4"]

# Page setup
st.set_page_config(page_title="HCD-Helper", layout="wide")
st.header("HCD-Helper")

# Enable caching for expensive functions
bootstrap_caching()

openai_api_key = st.text_input(
    "Enter your OpenAI API key. You can get a key at "
    "[https://platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)",
    type='password'  # this line masks the API key input
)

def synthesize_answer(text, api_key):
    try:
        # Making an API call to OpenAI's GPT-3 with a prompt to summarize the text
        response = openai.Completion.create(
            engine="text-davinci-003",  # or "text-davinci-003" for GPT-3.5
            prompt=f"Summarize the following document responses:\n\n{text}",
            max_tokens=150,  # You might want to adjust this value
            api_key=api_key
        )
        
        # Assuming the response contains the answer in 'choices' field
        answer = response['choices'][0]['text'].strip()
        return answer
    except Exception as e:
        return str(e)  # Return the error message in case of an exception


uploaded_files = st.file_uploader(
    "Upload pdf, docx, or txt files",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True,
    help="Scanned documents are not supported yet!",
)

model: str = st.selectbox("Model", options=MODEL_LIST)  # type: ignore

with st.expander("Advanced Options"):
    return_all_chunks = st.checkbox("Show all chunks retrieved from vector search")
    show_full_doc = st.checkbox("Show parsed contents of the document")

if not uploaded_files:
    st.stop()

folder_indices = []

processed_files = []  # List to store processed files

if uploaded_files:
    if not openai_api_key:
        st.error("Please enter your OpenAI API key to proceed.")
        st.stop()

    folder_indices = []

    processed_files = []  # List to store processed files

all_documents_text = []  # List to store text of all documents

# Update the query_all_documents function
def query_all_documents(concatenated_documents, query, llm):
    # Load the QA chain
    qa_chain = load_qa_with_sources_chain()
    
    # Query the concatenated documents using the QA chain
    result = qa_chain.query(concatenated_documents, query)

# Update the query_folder function
def query_folder(folder_index, query, return_all, llm):
    # Load the QA chain
    qa_chain = load_qa_with_sources_chain()
    
    # Query the folder index using the QA chain
    result = query_folder_old(folder_index, query, return_all, qa_chain)

# Process uploaded files
for uploaded_file in uploaded_files:
    try:
        file = read_file(uploaded_file)
    except Exception as e:
        display_file_read_error(e, file_name=uploaded_file.name)
        continue  # Skip to the next file on error

    if not is_file_valid(file):
        continue  # Skip to the next file if it's not valid
    all_documents_text.append(file.docs[0].page_content)  # Accessing the text content of the document
    chunked_file = chunk_file(file, chunk_size=300, chunk_overlap=0)
    processed_files.append(chunked_file)  # Store processed files for later access

    with st.spinner("Indexing document... This may take a while⏳"):
        folder_index = embed_files(
            files=[chunked_file],
            embedding=EMBEDDING if model != "debug" else "debug",
            vector_store=VECTOR_STORE if model != "debug" else "debug",
            openai_api_key=openai_api_key,
        )
        folder_indices.append(folder_index)  # Store folder indices for later querying

st.session_state['processed'] = True  # Set processed to True once documents are processed

if show_full_doc:
    with st.expander("Document"):
        # For simplicity, this code assumes you want to display the last processed file.
        # You might want to adjust this to show all/selected documents.
        last_processed_file = processed_files[-1]  # Get the last processed file
        st.markdown(f"<p>{wrap_doc_in_html(last_processed_file.docs)}</p>", unsafe_allow_html=True)

with st.form(key="qa_form1"):
    query = st.text_area("Ask a question about the document")
    submit = st.form_submit_button("Submit")

# Create a list of document options, adding an "All documents" option at the start
document_options = ["All documents"] + [f"Document {i}" for i, _ in enumerate(uploaded_files, start=1)]
selected_document = st.selectbox("Select document", options=document_options)

# Join all document texts into a single string
all_documents_concatenated = ' '.join(all_documents_text)


if submit:
    # ... rest of the code ...
    
    if selected_document == "All documents":
        # Collect all individual answers here
        individual_answers = []
        for folder_index in folder_indices:
            result = query_folder(
                folder_index=folder_index,
                query=query,
                return_all=return_all_chunks,
                llm=llm,
            )
            individual_answers.append({
                'document': f"Document {folder_indices.index(folder_index) + 1}",
                'answer': result.answer,
                'sources': result.sources,
            })
        
        # Format the individual answers into a structured text
        all_answers_text = "\n".join(
            [f"{answer['document']}:\n{answer['answer']}\nSources:\n{answer['sources']}\n" for answer in individual_answers]
        )
        

        
        # Now pass this collected text to OpenAI for a synthesized response
        # Assume synthesize_answer is a function that interacts with OpenAI to get a summarized/synthesized answer
        synthesized_answer = synthesize_answer(all_answers_text, openai_api_key)

        with answer_col:
            st.markdown("#### Synthesized Answer")
            st.markdown(synthesized_answer)
    else:
        answers = {}  # Dictionary to store answers per document

        # Adjusted index due to "All documents" option
        folder_index = folder_indices[document_options.index(selected_document) - 1]

        # Query the selected document
        result = query_folder(
            folder_index=folder_index,
            query=query,
            return_all=return_all_chunks,
            llm=llm,
        )

        with answer_col:
            st.markdown("#### Answer")
            st.markdown(result.answer)  # assuming result.answer is a string containing the answer

        with sources_col:
            st.markdown("#### Sources")
            for answer in individual_answers:
                st.markdown(f"{answer['document']} Sources:")
                for source in answer['sources']:
                    st.markdown(source.page_content)
                    st.markdown(source.metadata["source"])
                    st.markdown("---")  # Separate sources with a line

    # Set queried to True after processing a query
    st.session_state['queried'] = True
