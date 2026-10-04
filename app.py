import subprocess
import sys
import streamlit as st


st.set_page_config(
    page_title="JSSH Knowledge Assistant",
    page_icon="🔎",
    layout="wide"
)


st.title("JSSH Knowledge Assistant")

st.write(
    "Ask a question about Jobseeker Support using the Work and Income knowledge base."
)


question = st.text_area(
    "Question",
    placeholder="e.g. What rate of Jobseeker Support does a client receive while their partner is in prison if they have dependent children?",
    height=100
)


if st.button("Ask", type="primary"):

    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    with st.spinner("Searching the knowledge base..."):

        try:

            result = subprocess.run(
                [sys.executable, "ask_jssh_v2.py"],
                input=question + "\n",
                text=True,
                capture_output=True,
                check=True
            )

            output = result.stdout

        except subprocess.CalledProcessError as e:

            st.error("The RAG system returned an error.")

            if e.stderr:
                st.code(e.stderr)

            st.stop()

    # Find the ANSWER section
    if "ANSWER" in output:

        answer_start = output.find("ANSWER")
        sources_start = output.find("SOURCES")

        if sources_start != -1:

            answer = output[
                answer_start + len("ANSWER"):sources_start
            ].strip()

            sources = output[
                sources_start + len("SOURCES"):
            ].strip()

        else:

            answer = output[
                answer_start + len("ANSWER"):
            ].strip()

            sources = ""

    else:

        answer = output
        sources = ""


    st.subheader("Answer")

    st.markdown(answer)


    if sources:

        with st.expander("Sources", expanded=True):

            st.markdown(sources)
