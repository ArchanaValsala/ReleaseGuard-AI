import streamlit as st
import requests
import uuid
API_BASE_URL = "http://127.0.0.1:8000"

# -------------------------------------------------------------------
# PAGE STYLING
# -------------------------------------------------------------------

# Streamlit applies fairly generous spacing by default.
# This small CSS block makes the page more compact and easier to scan.
#
# unsafe_allow_html=True is required because we are injecting custom CSS.
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    h1, h2, h3 {
        margin-bottom: 0.5rem;
    }

    div[data-testid="stMetric"] {
        margin-bottom: -0.5rem;
    }

    div[data-testid="stAlert"] {
        margin-top: 0.25rem;
        margin-bottom: 0.75rem;
    }

    p {
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------------------------------------------------
# PAGE HEADER
# -------------------------------------------------------------------

st.title("ReleaseGuard AI")
st.write("AI-assisted release risk assessment")


# -------------------------------------------------------------------
# ASSESSMENT / THREAD ID
# -------------------------------------------------------------------

# Each release assessment needs a unique LangGraph thread_id.
#
# The thread_id is used by LangGraph checkpointing to keep the state
# and history of different release assessments separate.
#
# We generate the ID only once per Streamlit session and save it in
# session_state so normal Streamlit reruns keep using the same assessment.
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = str(uuid.uuid4())

thread_id = st.session_state["thread_id"]

# Display the generated assessment ID for traceability/debugging.
st.caption(f"Assessment ID: {thread_id}")


# ===================================================================
# RUN RELEASE ASSESSMENT
# ===================================================================

if st.button("Assess Release"):
    try:
        # st.empty() creates a placeholder that can be updated repeatedly.
        # We use it to show live progress messages as LangGraph nodes finish.
        progress_box = st.empty()

        # Call the FastAPI streaming endpoint.
        #
        # stream=True tells requests not to wait for the entire HTTP response.
        # Instead, Streamlit can process progress messages as they arrive.
        response = requests.get(
            f"{API_BASE_URL}/stream-assessment/{thread_id}",
            stream=True,
            timeout=60,
        )

        # Raise an exception for HTTP errors such as 404 or 500.
        # The exception is caught by the except block below.
        response.raise_for_status()

        # Keep all progress messages so the UI can display the complete
        # sequence rather than replacing the previous message each time.
        progress_lines = []

        # FastAPI sends one progress message per line.
        #
        # Example:
        # Fetching GitHub evidence...
        # Evaluating release risk...
        # Generating AI explanation...
        for line in response.iter_lines(decode_unicode=True):
            if line:
                progress_lines.append(line)

                # Update the same Streamlit placeholder with the growing
                # list of workflow progress messages.
                progress_box.text(
                    "\n".join(progress_lines)
                )

        # ---------------------------------------------------------------
        # LOAD THE FINAL CHECKPOINT AFTER STREAMING FINISHES
        # ---------------------------------------------------------------

        # The streaming endpoint is used only for progress messages.
        # Once the workflow finishes, retrieve the final structured state
        # from the checkpoint API.
        final_response = requests.get(
            f"{API_BASE_URL}/release-state/{thread_id}",
            timeout=30,
        )

        final_response.raise_for_status()

        data = final_response.json()

        # Save the assessment result in Streamlit session_state.
        #
        # This is important because Streamlit reruns the entire script when
        # another button or radio option is used. Without session_state,
        # the assessment result would disappear after the next interaction.
        st.session_state["assessment_data"] = data

    except requests.exceptions.RequestException:
        # Show a user-friendly message instead of exposing a raw Python
        # or requests exception in the UI.
        st.error("Unable to run the release assessment.")


# ===================================================================
# DISPLAY SAVED ASSESSMENT RESULT
# ===================================================================

# Display logic is intentionally separate from the Assess Release button.
#
# This means the result remains visible even after Streamlit reruns the
# script because of later interactions such as human review.
if "assessment_data" in st.session_state:
    data = st.session_state["assessment_data"]

    st.subheader("Assessment Result")

    decision = data["decision"]

    # ---------------------------------------------------------------
    # RELEASE DECISION
    # ---------------------------------------------------------------

    # Make the release decision visually prominent.
    if decision == "GO":
        st.success(f"Decision: {decision}")

    elif decision == "GO WITH CONDITIONS":
        st.warning(f"Decision: {decision}")

    else:
        st.error(f"Decision: {decision}")

    # Operational action selected by the LangGraph branch.
    st.write("Action Type:", data["action_type"])

    # ---------------------------------------------------------------
    # RISK LEVEL
    # ---------------------------------------------------------------

    risk_level = data["explanation"]["risk_level"]

    # st.metric makes the risk level easy to scan.
    st.metric(
        label="Risk Level",
        value=risk_level,
    )

    # ---------------------------------------------------------------
    # AI EXPLANATION
    # ---------------------------------------------------------------

    st.markdown("### Summary")
    st.write(data["explanation"]["summary"])

    st.markdown("### Recommended Action")
    st.info(data["explanation"]["recommended_action"])

    # ---------------------------------------------------------------
    # REVIEW STATUS
    # ---------------------------------------------------------------

    st.markdown("### Review")
    st.write("Review Status:", data["review_status"])

    # ---------------------------------------------------------------
    # HUMAN-IN-THE-LOOP
    # ---------------------------------------------------------------

    # Human review controls appear only when LangGraph has exhausted the
    # allowed automatic revisions and explicitly asks for human input.
    if data["human_review_required"]:
        st.warning("Human review is required before proceeding.")

        # Give the reviewer only the choices supported by the backend API.
        human_decision = st.radio(
            "Human Decision",
            [
                "Approve",
                "Reject",
                "Request Changes",
            ],
        )

        if st.button("Submit Human Decision"):
            try:
                # Send the human decision back to FastAPI.
                #
                # FastAPI will:
                # 1. find the existing LangGraph thread
                # 2. save human_decision into the checkpoint
                # 3. apply the corresponding human decision rules
                review_response = requests.post(
                    f"{API_BASE_URL}/human-review",
                    json={
                        "thread_id": thread_id,
                        "decision": human_decision,
                    },
                    timeout=30,
                )

                review_response.raise_for_status()

                review_data = review_response.json()

                # -------------------------------------------------------
                # REFRESH THE SAVED ASSESSMENT AFTER HUMAN REVIEW
                # -------------------------------------------------------

                # The backend state has now changed, but Streamlit still has
                # the old assessment_data stored in session_state.
                #
                # Retrieve the latest checkpoint immediately so the UI
                # reflects the human decision without requiring the user
                # to manually load the state again.
                updated_response = requests.get(
                    f"{API_BASE_URL}/release-state/{thread_id}",
                    timeout=30,
                )

                updated_response.raise_for_status()

                updated_data = updated_response.json()

                # Replace the old frontend copy with the latest backend state.
                st.session_state["assessment_data"] = updated_data

                # Confirm that the backend accepted and saved the decision.
                st.success(
                    f"Human decision submitted: {review_data['decision']}"
                )

                # Force an immediate rerun so the displayed Review Status,
                # Human Review section, and Action Type use the refreshed state.
                st.rerun()

            except requests.exceptions.RequestException:
                st.error(
                    "Unable to submit the human review decision."
                )

    else:
        # Most normal assessments will finish automatically and therefore
        # do not need human intervention.
        st.success("No human review required.")


# ===================================================================
# LOAD RAW SAVED LANGGRAPH STATE
# ===================================================================

# This button is mainly useful for debugging and demonstration.
#
# It lets us prove that the assessment is checkpointed and that the
# latest LangGraph state can be retrieved later using the same thread_id.
if st.button("Load Saved State"):
    try:
        with st.spinner("Loading saved state..."):
            response = requests.get(
                f"{API_BASE_URL}/release-state/{thread_id}",
                timeout=30,
            )

        response.raise_for_status()

        saved_state = response.json()

        st.subheader("Saved Release State")

        # Display the complete LangGraph state as JSON.
        #
        # This is intentionally a technical/debug view rather than the
        # normal user-facing result presentation above.
        st.json(saved_state)

    except requests.exceptions.RequestException:
        st.error("Unable to load the saved release state.")