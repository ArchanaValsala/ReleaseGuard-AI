from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from typing import Literal

from release_graph import graph, apply_human_decision


# -------------------------------------------------------------------
# FASTAPI APPLICATION
# -------------------------------------------------------------------

# This FastAPI app is the backend interface for ReleaseGuard.
#
# Its job is to:
# - accept requests from clients such as Streamlit
# - trigger LangGraph workflows
# - retrieve saved LangGraph state
# - accept human review decisions
# - expose workflow progress through streaming
#
# It deliberately does NOT contain the core release decision logic.
app = FastAPI()


# -------------------------------------------------------------------
# REQUEST MODELS
# -------------------------------------------------------------------

class ReleaseRequest(BaseModel):
    """
    Request body used to start a release assessment.

    thread_id identifies one LangGraph assessment/checkpoint history.

    The same thread_id is later used to:
    - retrieve saved state
    - submit human review
    - keep assessment history isolated
    """

    thread_id: str


class HumanReviewRequest(BaseModel):
    """
    Request body used when a human reviewer submits a decision.

    Literal restricts decision to the three supported values.
    Any other value is rejected automatically by FastAPI/Pydantic
    with HTTP 422 before this request reaches the endpoint logic.
    """

    thread_id: str

    decision: Literal[
        "Approve",
        "Reject",
        "Request Changes",
    ]


# -------------------------------------------------------------------
# INITIAL LANGGRAPH STATE
# -------------------------------------------------------------------

def create_initial_state():
    """
    Return a fresh initial state for a new ReleaseGuard assessment.

    Keeping the initial LangGraph state in one helper avoids duplicating
    the same dictionary across multiple API endpoints.

    If the state structure changes later, it only needs to be updated
    in this one place.
    """

    return {
        "release_evidence": {},
        "decision": "",
        "explanation": {},
        "action_type": "",
        "review": {},
        "revision_count": 0,
        "review_status": "",
        "human_review_required": False,
        "human_decision": "",
    }


# -------------------------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------------------------

@app.get("/health")
def health_check():
    """
    Simple health endpoint used to confirm that the API is running.

    It does not call GitHub, OpenAI, or LangGraph.
    """

    return {
        "status": "ok"
    }


# -------------------------------------------------------------------
# STANDARD RELEASE ASSESSMENT ENDPOINT
# -------------------------------------------------------------------

@app.post("/assess-release")
def assess_release(request: ReleaseRequest):
    """
    Run the complete ReleaseGuard LangGraph workflow and return
    the final assessment result.

    This endpoint uses graph.invoke(), which waits until the entire
    workflow finishes before returning a response.

    The Streamlit UI currently uses the streaming endpoint instead,
    but this endpoint remains useful for:
    - API clients that only need the final result
    - testing
    - debugging
    - future integrations
    """

    thread_id = request.thread_id

    # create_initial_state() provides a fresh starting state.
    #
    # Each LangGraph node then updates only the fields it is responsible for.
    result = graph.invoke(
        create_initial_state(),
        config={
            "configurable": {
                "thread_id": thread_id
            }
        },
    )

    # Return only the fields useful to a normal API client.
    #
    # The complete checkpoint can be retrieved separately through:
    # GET /release-state/{thread_id}
    return {
        "decision": result["decision"],
        "action_type": result["action_type"],
        "explanation": result["explanation"],
        "review_status": result["review_status"],
        "human_review_required": result["human_review_required"],
    }


# -------------------------------------------------------------------
# RETRIEVE SAVED LANGGRAPH STATE
# -------------------------------------------------------------------

@app.get("/release-state/{thread_id}")
def get_release_state(thread_id: str):
    """
    Retrieve the latest checkpoint for a release assessment.

    This allows another client action to continue using the same
    assessment after the original graph execution has finished.

    Examples:
    - Streamlit loads the final result after streaming completes.
    - A human reviewer can inspect the latest saved state.
    """

    # LangGraph uses this configuration to identify the checkpoint thread.
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    # Retrieve the latest state saved for this assessment.
    snapshot = graph.get_state(config)

    # If no checkpoint exists for this thread, return HTTP 404.
    if not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail="Release thread not found",
        )

    # snapshot.values contains the complete latest LangGraph state.
    return snapshot.values


# -------------------------------------------------------------------
# HUMAN-IN-THE-LOOP ENDPOINT
# -------------------------------------------------------------------

@app.post("/human-review")
def submit_human_review(request: HumanReviewRequest):
    """
    Apply a human review decision to an existing assessment.

    Human review happens after the automated graph run has finished.

    The decision is written back into the checkpointed LangGraph state
    using graph.update_state().

    Current flow:

        find saved thread
            ↓
        save raw human decision
            ↓
        read updated checkpoint
            ↓
        apply human-decision rules
            ↓
        save resulting state updates
            ↓
        return updated review status

    Note:
    This is checkpoint-based human intervention rather than a true
    LangGraph interrupt/resume workflow.
    """

    config = {
        "configurable": {
            "thread_id": request.thread_id
        }
    }

    # Confirm that the assessment exists before modifying its state.
    snapshot = graph.get_state(config)

    if not snapshot.values:
        raise HTTPException(
            status_code=404,
            detail="Release thread not found",
        )

    # ----------------------------------------------------------------
    # STEP 1: SAVE THE RAW HUMAN CHOICE
    # ----------------------------------------------------------------

    # Human input occurs outside the original automated graph execution.
    #
    # update_state() lets us add this external input to the existing
    # LangGraph checkpoint without rerunning the complete assessment.
    graph.update_state(
        config,
        {
            "human_decision": request.decision
        },
    )

    # ----------------------------------------------------------------
    # STEP 2: READ THE UPDATED STATE
    # ----------------------------------------------------------------

    # Retrieve the checkpoint again so it now includes human_decision.
    updated_snapshot = graph.get_state(config)

    # ----------------------------------------------------------------
    # STEP 3: APPLY HUMAN-DECISION RULES
    # ----------------------------------------------------------------

    # Reuse the decision-mapping logic from release_graph.py.
    #
    # This avoids duplicating the meaning of:
    # - Approve
    # - Reject
    # - Request Changes
    # inside the API layer.
    state_updates = apply_human_decision(
        updated_snapshot.values
    )

    # ----------------------------------------------------------------
    # STEP 4: SAVE THE RESULTING STATE CHANGES
    # ----------------------------------------------------------------

    graph.update_state(
        config,
        state_updates,
    )

    # Retrieve the state one final time after the decision has been applied.
    final_snapshot = graph.get_state(config)

    return {
        "thread_id": request.thread_id,
        "decision": request.decision,
        "review_status": final_snapshot.values["review_status"],
        "human_review_required": final_snapshot.values[
            "human_review_required"
        ],
        "status": "saved",
    }


# -------------------------------------------------------------------
# STREAMING RELEASE ASSESSMENT
# -------------------------------------------------------------------

@app.get("/stream-assessment/{thread_id}")
def stream_assessment(thread_id: str):
    """
    Run the ReleaseGuard workflow while streaming progress messages.

    Unlike graph.invoke(), graph.stream() produces events as individual
    LangGraph nodes complete.

    FastAPI wraps these events in StreamingResponse so the Streamlit
    frontend can display live progress instead of waiting silently
    for the entire workflow to finish.
    """

    def event_generator():
        """
        Convert LangGraph stream events into readable progress messages.

        Each yield sends another line to the HTTP client while the
        workflow is still running.
        """

        # Translate internal LangGraph node names into messages suitable
        # for the user interface.
        progress_messages = {
            "fetch_release_evidence": "Fetching GitHub evidence...",
            "evaluate_release": "Evaluating release risk...",
            "handle_go": "Release path selected: GO",
            "handle_go_with_conditions":
                "Release path selected: GO WITH CONDITIONS",
            "handle_no_go": "Release path selected: NO-GO",
            "generate_explanation": "Generating AI explanation...",
            "review_explanation": "Reviewing AI explanation...",
            "revise_explanation": "Revising AI explanation...",
            "finalize_review_status": "Finalizing assessment...",
        }

        # graph.stream() runs the same workflow as graph.invoke(),
        # but emits events after nodes complete.
        for event in graph.stream(
            create_initial_state(),
            config={
                "configurable": {
                    "thread_id": thread_id
                }
            },
        ):

            # Example LangGraph stream event:
            #
            # {
            #     "evaluate_release": {
            #         "decision": "GO"
            #     }
            # }
            #
            # The first dictionary key tells us which node just completed.
            node_name = next(iter(event))

            # Use a friendly message when the node is known.
            #
            # The fallback means newly added nodes will still produce
            # visible progress even if the mapping has not been updated.
            message = progress_messages.get(
                node_name,
                f"Completed: {node_name}"
            )

            # StreamingResponse sends each yielded line immediately
            # instead of waiting for the generator to finish.
            yield message + "\n"

    # Send the generator output as a streaming HTTP response.
    #
    # Streamlit receives this using:
    #
    # requests.get(..., stream=True)
    #
    # and reads each message using:
    #
    # response.iter_lines()
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
    )