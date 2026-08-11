from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


# -------------------------------------------------------------------
# FASTAPI TEST CLIENT
# -------------------------------------------------------------------

# TestClient lets pytest call FastAPI endpoints directly without starting
# a real Uvicorn server.
#
# This makes API tests:
# - fast
# - isolated
# - easy to run in CI
client = TestClient(app)


# ===================================================================
# HEALTH CHECK TEST
# ===================================================================

def test_health_check():
    """
    Verify that the API health endpoint is available and returns
    the expected response.

    This is the simplest API smoke test and confirms that the FastAPI
    application can be loaded successfully.
    """

    response = client.get("/health")

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok"
    }


# ===================================================================
# RELEASE ASSESSMENT ENDPOINT TEST
# ===================================================================

@patch("api.graph.invoke")
def test_assess_release(mock_graph_invoke):
    """
    Verify POST /assess-release without running the real LangGraph workflow.

    graph.invoke() is mocked so this test does NOT call:
    - GitHub
    - OpenAI
    - the full release workflow

    The goal here is only to confirm that FastAPI:
    1. accepts the request
    2. calls the graph
    3. returns the expected fields to the client
    """

    # Simulate the final state that LangGraph would normally return.
    mock_graph_invoke.return_value = {
        "decision": "GO",
        "action_type": "release",
        "explanation": {
            "summary": "Test summary",
            "risk_level": "Low",
            "recommended_action": "Proceed with release",
        },
        "review_status": "approved",
        "human_review_required": False,
    }

    response = client.post(
        "/assess-release",
        json={
            "thread_id": "test-api-thread"
        },
    )

    assert response.status_code == 200

    data = response.json()

    # Verify the important parts of the API response.
    assert data["decision"] == "GO"
    assert data["action_type"] == "release"
    assert data["explanation"]["risk_level"] == "Low"
    assert data["review_status"] == "approved"
    assert data["human_review_required"] is False


# ===================================================================
# SAVED STATE ENDPOINT TESTS
# ===================================================================

@patch("api.graph.get_state")
def test_get_release_state_existing_thread(mock_get_state):
    """
    Verify that GET /release-state/{thread_id} returns the saved
    LangGraph checkpoint when the thread exists.
    """

    # graph.get_state() normally returns a StateSnapshot object.
    # We only need its .values attribute for this API test.
    mock_get_state.return_value.values = {
        "decision": "GO",
        "action_type": "release",
        "review_status": "approved",
    }

    response = client.get(
        "/release-state/test-thread"
    )

    assert response.status_code == 200

    assert response.json() == {
        "decision": "GO",
        "action_type": "release",
        "review_status": "approved",
    }


@patch("api.graph.get_state")
def test_get_release_state_unknown_thread(mock_get_state):
    """
    Verify that an unknown checkpoint thread returns HTTP 404.

    This protects the API from silently returning an empty state when
    the requested LangGraph thread does not exist.
    """

    # Empty snapshot values simulate a thread that has never been created
    # in the current checkpointer.
    mock_get_state.return_value.values = {}

    response = client.get(
        "/release-state/unknown-thread"
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Release thread not found"
    }


# ===================================================================
# HUMAN REVIEW VALIDATION TEST
# ===================================================================

def test_human_review_rejects_invalid_decision():
    """
    Verify that FastAPI/Pydantic rejects unsupported human decisions.

    HumanReviewRequest uses Literal, so only these values are accepted:
    - Approve
    - Reject
    - Request Changes

    "Maybe" should therefore fail validation before the endpoint
    business logic is executed.
    """

    response = client.post(
        "/human-review",
        json={
            "thread_id": "release-001",
            "decision": "Maybe",
        },
    )

    # 422 is FastAPI/Pydantic's validation error response.
    assert response.status_code == 422


# ===================================================================
# HUMAN REVIEW — APPROVE
# ===================================================================

@patch("api.apply_human_decision")
@patch("api.graph.update_state")
@patch("api.graph.get_state")
def test_human_review_approve(
    mock_get_state,
    mock_update_state,
    mock_apply_human_decision,
):
    """
    Verify the successful Approve path for POST /human-review.

    The endpoint performs several state operations:

    1. get the existing checkpoint
    2. save the raw human decision
    3. read the updated checkpoint
    4. apply human-decision rules
    5. save those state updates
    6. read the final checkpoint

    All LangGraph state operations are mocked here so the test focuses
    only on the API orchestration.
    """

    # ---------------------------------------------------------------
    # Snapshot 1:
    # state before the human has made a decision
    # ---------------------------------------------------------------

    existing_snapshot = MagicMock()

    existing_snapshot.values = {
        "human_decision": "",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # ---------------------------------------------------------------
    # Snapshot 2:
    # state after "Approve" has been written to human_decision
    # ---------------------------------------------------------------

    updated_snapshot = MagicMock()

    updated_snapshot.values = {
        "human_decision": "Approve",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # ---------------------------------------------------------------
    # Snapshot 3:
    # final state after apply_human_decision() has been applied
    # ---------------------------------------------------------------

    final_snapshot = MagicMock()

    final_snapshot.values = {
        "human_decision": "Approve",
        "review_status": "human_approved",
        "human_review_required": False,
    }

    # graph.get_state() is called three times by the endpoint.
    # side_effect returns a different snapshot for each call.
    mock_get_state.side_effect = [
        existing_snapshot,
        updated_snapshot,
        final_snapshot,
    ]

    # Simulate the decision-mapping logic from release_graph.py.
    mock_apply_human_decision.return_value = {
        "review_status": "human_approved",
        "human_review_required": False,
    }

    response = client.post(
        "/human-review",
        json={
            "thread_id": "test-human-approve",
            "decision": "Approve",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "thread_id": "test-human-approve",
        "decision": "Approve",
        "review_status": "human_approved",
        "human_review_required": False,
        "status": "saved",
    }


# ===================================================================
# HUMAN REVIEW — REJECT
# ===================================================================

@patch("api.apply_human_decision")
@patch("api.graph.update_state")
@patch("api.graph.get_state")
def test_human_review_reject(
    mock_get_state,
    mock_update_state,
    mock_apply_human_decision,
):
    """
    Verify the Reject path for POST /human-review.

    A human rejection should:
    - mark the review as human_rejected
    - remove the need for further human review
    - produce block_release as the action type
    """

    # State before the human decision.
    existing_snapshot = MagicMock()

    existing_snapshot.values = {
        "human_decision": "",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # State after raw human choice has been saved.
    updated_snapshot = MagicMock()

    updated_snapshot.values = {
        "human_decision": "Reject",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # Final checkpoint after decision rules are applied.
    final_snapshot = MagicMock()

    final_snapshot.values = {
        "human_decision": "Reject",
        "review_status": "human_rejected",
        "human_review_required": False,
        "action_type": "block_release",
    }

    mock_get_state.side_effect = [
        existing_snapshot,
        updated_snapshot,
        final_snapshot,
    ]

    mock_apply_human_decision.return_value = {
        "review_status": "human_rejected",
        "human_review_required": False,
        "action_type": "block_release",
    }

    response = client.post(
        "/human-review",
        json={
            "thread_id": "test-human-reject",
            "decision": "Reject",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "thread_id": "test-human-reject",
        "decision": "Reject",
        "review_status": "human_rejected",
        "human_review_required": False,
        "status": "saved",
    }


# ===================================================================
# HUMAN REVIEW — REQUEST CHANGES
# ===================================================================

@patch("api.apply_human_decision")
@patch("api.graph.update_state")
@patch("api.graph.get_state")
def test_human_review_request_changes(
    mock_get_state,
    mock_update_state,
    mock_apply_human_decision,
):
    """
    Verify the Request Changes path for POST /human-review.

    Unlike Approve or Reject, Request Changes leaves the assessment
    requiring human attention.
    """

    # State before human input.
    existing_snapshot = MagicMock()

    existing_snapshot.values = {
        "human_decision": "",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # State after the raw human choice has been stored.
    updated_snapshot = MagicMock()

    updated_snapshot.values = {
        "human_decision": "Request Changes",
        "review_status": "max_revisions_reached",
        "human_review_required": True,
    }

    # Final state after the human-decision rules are applied.
    final_snapshot = MagicMock()

    final_snapshot.values = {
        "human_decision": "Request Changes",
        "review_status": "changes_requested",
        "human_review_required": True,
    }

    mock_get_state.side_effect = [
        existing_snapshot,
        updated_snapshot,
        final_snapshot,
    ]

    mock_apply_human_decision.return_value = {
        "review_status": "changes_requested",
        "human_review_required": True,
    }

    response = client.post(
        "/human-review",
        json={
            "thread_id": "test-human-request-changes",
            "decision": "Request Changes",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "thread_id": "test-human-request-changes",
        "decision": "Request Changes",
        "review_status": "changes_requested",
        "human_review_required": True,
        "status": "saved",
    }


# ===================================================================
# STREAMING ENDPOINT TEST
# ===================================================================

@patch("api.graph.stream")
def test_stream_assessment(mock_stream):
    """
    Verify that the streaming endpoint converts LangGraph node events
    into readable progress messages.

    graph.stream() is mocked so this test does not run:
    - GitHub API calls
    - OpenAI calls
    - the real LangGraph workflow

    Instead, we feed the endpoint a controlled sequence of fake node events.
    """

    # Simulate three LangGraph node events arriving in sequence.
    mock_stream.return_value = iter(
        [
            {
                "fetch_release_evidence": {
                    "release_evidence": {
                        "ci_passed": True
                    }
                }
            },
            {
                "evaluate_release": {
                    "decision": "GO"
                }
            },
            {
                "finalize_review_status": {
                    "review_status": "approved",
                    "human_review_required": False,
                }
            },
        ]
    )

    response = client.get(
        "/stream-assessment/test-stream-thread"
    )

    assert response.status_code == 200

    body = response.text

    # Verify that technical LangGraph node names were translated into
    # the human-friendly progress text expected by the frontend.
    assert "Fetching GitHub evidence..." in body
    assert "Evaluating release risk..." in body
    assert "Finalizing assessment..." in body