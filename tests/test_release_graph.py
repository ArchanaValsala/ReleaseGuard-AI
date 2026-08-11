from unittest.mock import patch

from github_client import (
    simplify_workflow_run,
    simplify_issues,
)

from release_graph import (
    route_release,
    handle_go,
    handle_go_with_conditions,
    handle_no_go,
    evaluate_release,
    fetch_release_evidence,
    graph,
)


# ===================================================================
# GITHUB DATA TRANSFORMATION TESTS
# ===================================================================

def test_simplify_issues_skips_pull_requests():
    """
    Verify that GitHub pull requests are not accidentally treated
    as release issues.

    GitHub's /issues endpoint can return both:
    - real issues
    - pull requests

    A pull request contains the "pull_request" field, and ReleaseGuard
    should ignore it when calculating issue severity counts.
    """

    issues = [
        {
            "number": 1,
            "title": "Real issue",
            "labels": [
                {"name": "high"}
            ],
        },
        {
            "number": 2,
            "title": "Pull request",
            "labels": [
                {"name": "critical"}
            ],
            "pull_request": {
                "url": "https://example.com/pr/2"
            },
        },
    ]

    result = simplify_issues(issues)

    # Only the real GitHub issue should remain.
    # The critical label on the pull request must not affect release risk.
    assert result == [
        {
            "number": 1,
            "title": "Real issue",
            "severity": "high",
        }
    ]


def test_simplify_workflow_run_when_no_runs():
    """
    Verify safe behavior when the repository has no GitHub Actions runs.

    Instead of failing with workflow_runs[0], ReleaseGuard should return
    a conservative result where CI is treated as not passed.
    """

    workflow_data = {
        "workflow_runs": []
    }

    result = simplify_workflow_run(workflow_data)

    assert result == {
        "ci_passed": False,
        "status": "not_found",
        "conclusion": None,
        "branch": None,
    }


# ===================================================================
# RELEASE ROUTER TESTS
# ===================================================================

# These tests isolate route_release() from the rest of LangGraph.
#
# The purpose is to prove that each deterministic release decision
# maps to the correct conditional-edge route.


def test_route_go():
    """
    GO should route to the "go" graph branch.
    """

    state = {
        "decision": "GO"
    }

    result = route_release(state)

    assert result == "go"


def test_route_go_with_conditions():
    """
    GO WITH CONDITIONS should route to the conditional-release branch.
    """

    state = {
        "decision": "GO WITH CONDITIONS"
    }

    result = route_release(state)

    assert result == "go_with_conditions"


def test_route_no_go():
    """
    NO-GO should route to the release-blocking branch.
    """

    state = {
        "decision": "NO-GO"
    }

    result = route_release(state)

    assert result == "no_go"


# ===================================================================
# RELEASE BRANCH HANDLER TESTS
# ===================================================================

# After route_release chooses a branch, these handlers translate the
# business decision into an operational action_type.


def test_handle_go():
    """
    A GO branch should result in the normal release action.
    """

    result = handle_go({})

    assert result["action_type"] == "release"


def test_handle_go_with_conditions():
    """
    GO WITH CONDITIONS should produce a conditional release action.
    """

    result = handle_go_with_conditions({})

    assert result["action_type"] == "conditional_release"


def test_handle_no_go():
    """
    NO-GO should explicitly block the release.
    """

    result = handle_no_go({})

    assert result["action_type"] == "block_release"


# ===================================================================
# DETERMINISTIC EVALUATION NODE TEST
# ===================================================================

def test_evaluate_release():
    """
    Verify that the LangGraph evaluate_release node correctly calls
    the deterministic release rules using evidence from state.

    Here:
    - CI passed
    - no critical issues
    - one high issue

    Therefore the expected result is GO WITH CONDITIONS.
    """

    state = {
        "release_evidence": {
            "ci_passed": True,
            "critical_issues": 0,
            "high_issues": 1,
        }
    }

    result = evaluate_release(state)

    assert result["decision"] == "GO WITH CONDITIONS"


# ===================================================================
# GITHUB EVIDENCE NODE TEST
# ===================================================================

# patch() replaces external dependencies with controlled test doubles.
#
# This allows us to test fetch_release_evidence() without:
# - making real GitHub API requests
# - depending on the current state of the repository
# - needing network access
#
# Important:
# decorators are applied from bottom to top, which is why the mock
# parameters appear in the reverse order of the decorators.


@patch("release_graph.get_open_issues")
@patch("release_graph.simplify_issues")
@patch("release_graph.count_issues_by_severity")
@patch("release_graph.get_latest_workflow_run")
@patch("release_graph.simplify_workflow_run")
def test_fetch_release_evidence(
    mock_simplify_workflow_run,
    mock_get_latest_workflow_run,
    mock_count_issues_by_severity,
    mock_simplify_issues,
    mock_get_open_issues,
):
    """
    Verify that fetch_release_evidence() combines issue severity data
    and CI data into the expected LangGraph release_evidence structure.
    """

    # Pretend GitHub returned no raw issues.
    mock_get_open_issues.return_value = []

    # Pretend issue simplification also produced an empty list.
    mock_simplify_issues.return_value = []

    # Control the severity totals used by the graph node.
    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 1,
        "unknown": 0,
    }

    # The raw workflow response itself does not matter because
    # simplify_workflow_run() is also mocked below.
    mock_get_latest_workflow_run.return_value = {}

    # Simulate a successful latest GitHub Actions run.
    mock_simplify_workflow_run.return_value = {
        "ci_passed": True,
        "status": "completed",
        "conclusion": "success",
        "branch": "main",
    }

    result = fetch_release_evidence({})

    evidence = result["release_evidence"]

    # Check that the node combined CI and issue information correctly.
    assert evidence["ci_passed"] is True
    assert evidence["critical_issues"] == 0
    assert evidence["high_issues"] == 1
    assert evidence["low_issues"] == 1


# ===================================================================
# FULL GRAPH TEST — GO WITH CONDITIONS
# ===================================================================

# This is broader than the previous unit tests.
#
# Instead of testing one function, it executes the compiled LangGraph
# from beginning to end.
#
# GitHub and OpenAI are mocked so the test remains:
# - deterministic
# - fast
# - free from API costs
# - independent of network services


@patch("release_graph.get_review_model")
@patch("release_graph.get_structured_model")
@patch("release_graph.get_open_issues")
@patch("release_graph.simplify_issues")
@patch("release_graph.count_issues_by_severity")
@patch("release_graph.get_latest_workflow_run")
@patch("release_graph.simplify_workflow_run")
def test_full_graph_go_with_conditions(
    mock_simplify_workflow_run,
    mock_get_latest_workflow_run,
    mock_count_issues_by_severity,
    mock_simplify_issues,
    mock_get_open_issues,
    mock_get_structured_model,
    mock_get_review_model,
):
    """
    Execute the full LangGraph workflow for a scenario that should result
    in GO WITH CONDITIONS.

    This verifies several connected pieces at once:
    - evidence collection
    - deterministic decision
    - conditional routing
    - action selection
    - AI explanation
    - AI review
    - final review status
    """

    # -------------------------
    # Mock GitHub issue data
    # -------------------------

    mock_get_open_issues.return_value = []

    mock_simplify_issues.return_value = []

    # One high issue should lead to GO WITH CONDITIONS.
    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 1,
        "unknown": 0,
    }

    # -------------------------
    # Mock GitHub Actions data
    # -------------------------

    mock_get_latest_workflow_run.return_value = {}

    mock_simplify_workflow_run.return_value = {
        "ci_passed": True,
        "status": "completed",
        "conclusion": "success",
        "branch": "main",
    }

    # -------------------------
    # Mock explanation model
    # -------------------------

    # get_structured_model() normally returns a LangChain structured model.
    #
    # Instead of calling OpenAI, we tell the mock exactly what
    # invoke(...).model_dump() should return.
    mock_get_structured_model.return_value.invoke.return_value.model_dump.return_value = {
        "summary": "Test summary",
        "risk_level": "Moderate",
        "recommended_action": "Test action",
    }

    # -------------------------
    # Mock AI reviewer
    # -------------------------

    # The reviewer accepts the first explanation, so no revision loop
    # should be triggered in this test.
    mock_get_review_model.return_value.invoke.return_value.model_dump.return_value = {
        "is_consistent": True,
        "review_comment": "The explanation matches the decision.",
        "needs_revision": False,
    }

    # -------------------------
    # Run the complete graph
    # -------------------------

    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
            "review": {},
            "revision_count": 0,
            "review_status": "",
            "human_review_required": False,
            "human_decision": "",
        },

        # The graph uses checkpointing, so every graph execution needs
        # a thread_id. Tests use their own IDs to isolate saved state.
        config={
            "configurable": {
                "thread_id": "test-go-with-conditions"
            }
        },
    )

    # -------------------------
    # Verify final graph state
    # -------------------------

    assert result["decision"] == "GO WITH CONDITIONS"

    assert result["action_type"] == "conditional_release"

    assert result["explanation"]["risk_level"] == "Moderate"

    assert result["review_status"] == "approved"

    assert result["human_review_required"] is False


# ===================================================================
# FULL GRAPH TEST — ONE REVISION THEN APPROVAL
# ===================================================================


@patch("release_graph.get_review_model")
@patch("release_graph.get_structured_model")
@patch("release_graph.get_open_issues")
@patch("release_graph.simplify_issues")
@patch("release_graph.count_issues_by_severity")
@patch("release_graph.get_latest_workflow_run")
@patch("release_graph.simplify_workflow_run")
def test_full_graph_revision_loop(
    mock_simplify_workflow_run,
    mock_get_latest_workflow_run,
    mock_count_issues_by_severity,
    mock_simplify_issues,
    mock_get_open_issues,
    mock_get_structured_model,
    mock_get_review_model,
):
    """
    Verify the agentic review/revision loop.

    Scenario:

        deterministic decision = GO
                ↓
        initial AI explanation is wrong
                ↓
        reviewer requests revision
                ↓
        explanation is revised
                ↓
        reviewer approves revision
                ↓
        workflow finishes

    Expected revision_count = 1.
    """

    # -------------------------
    # Mock release evidence
    # -------------------------

    mock_get_open_issues.return_value = []

    mock_simplify_issues.return_value = []

    # CI passes and there are no critical/high issues.
    # Therefore the deterministic decision should be GO.
    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 1,
        "unknown": 0,
    }

    mock_get_latest_workflow_run.return_value = {}

    mock_simplify_workflow_run.return_value = {
        "ci_passed": True,
        "status": "completed",
        "conclusion": "success",
        "branch": "main",
    }

    # -------------------------
    # Mock explanation model
    # -------------------------

    explanation_model = mock_get_structured_model.return_value

    # side_effect lets consecutive calls return different results.
    #
    # First call:
    # generate_explanation() produces an intentionally inconsistent result.
    #
    # Second call:
    # revise_explanation() produces a corrected result.
    explanation_model.invoke.return_value.model_dump.side_effect = [
        {
            "summary": "Initial explanation",
            "risk_level": "High",
            "recommended_action": "Block the release",
        },
        {
            "summary": "Revised explanation",
            "risk_level": "Low",
            "recommended_action": "Proceed with the release",
        },
    ]

    # -------------------------
    # Mock reviewer
    # -------------------------

    review_model = mock_get_review_model.return_value

    # First review rejects the initial explanation.
    #
    # Second review accepts the revised explanation.
    review_model.invoke.return_value.model_dump.side_effect = [
        {
            "is_consistent": False,
            "review_comment":
                "The explanation does not match the GO decision.",
            "needs_revision": True,
        },
        {
            "is_consistent": True,
            "review_comment":
                "The revised explanation now matches the GO decision.",
            "needs_revision": False,
        },
    ]

    # -------------------------
    # Run full graph
    # -------------------------

    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
            "review": {},
            "revision_count": 0,
            "review_status": "",
            "human_review_required": False,
            "human_decision": "",
        },
        config={
            "configurable": {
                "thread_id": "test-revision-loop"
            }
        },
    )

    # -------------------------
    # Verify revision behavior
    # -------------------------

    # Deterministic decision should remain unchanged by the AI.
    assert result["decision"] == "GO"

    assert result["action_type"] == "release"

    # The final explanation should be the revised one,
    # not the inconsistent initial explanation.
    assert result["explanation"]["summary"] == "Revised explanation"

    # The final reviewer response should approve the revised result.
    assert result["review"]["needs_revision"] is False

    # Exactly one revision occurred.
    assert result["revision_count"] == 1

    assert result["review_status"] == "approved"

    assert result["human_review_required"] is False


# ===================================================================
# FULL GRAPH TEST — MAXIMUM REVISION SAFETY LIMIT
# ===================================================================


@patch("release_graph.get_review_model")
@patch("release_graph.get_structured_model")
@patch("release_graph.get_open_issues")
@patch("release_graph.simplify_issues")
@patch("release_graph.count_issues_by_severity")
@patch("release_graph.get_latest_workflow_run")
@patch("release_graph.simplify_workflow_run")
def test_revision_stops_after_max_limit(
    mock_simplify_workflow_run,
    mock_get_latest_workflow_run,
    mock_count_issues_by_severity,
    mock_simplify_issues,
    mock_get_open_issues,
    mock_get_structured_model,
    mock_get_review_model,
):
    """
    Verify that the AI review/revision loop cannot continue forever.

    Scenario:

        generate explanation
                ↓
        reviewer requests revision
                ↓
        revision 1
                ↓
        reviewer still requests revision
                ↓
        revision 2
                ↓
        reviewer STILL requests revision
                ↓
        STOP automatic retries
                ↓
        human_review_required = True

    This is an important safety mechanism for agentic workflows.
    """

    # -------------------------
    # Mock release evidence
    # -------------------------

    mock_get_open_issues.return_value = []

    mock_simplify_issues.return_value = []

    # Evidence results in a deterministic GO decision.
    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 1,
        "unknown": 0,
    }

    mock_get_latest_workflow_run.return_value = {}

    mock_simplify_workflow_run.return_value = {
        "ci_passed": True,
        "status": "completed",
        "conclusion": "success",
        "branch": "main",
    }

    # -------------------------
    # Mock explanation/revisions
    # -------------------------

    explanation_model = mock_get_structured_model.return_value

    # Three explanation outputs are expected:
    #
    # 1. initial explanation
    # 2. first revision
    # 3. second/final allowed revision
    explanation_model.invoke.return_value.model_dump.side_effect = [
        {
            "summary": "Initial explanation",
            "risk_level": "High",
            "recommended_action": "Block release",
        },
        {
            "summary": "Revision one",
            "risk_level": "Medium",
            "recommended_action": "Still not correct",
        },
        {
            "summary": "Revision two",
            "risk_level": "Low",
            "recommended_action": "Final revision",
        },
    ]

    # -------------------------
    # Mock reviewer
    # -------------------------

    review_model = mock_get_review_model.return_value

    # The reviewer requests another revision every time.
    #
    # Even after the third review asks for another revision,
    # route_review() must stop because revision_count has reached 2.
    review_model.invoke.return_value.model_dump.side_effect = [
        {
            "is_consistent": False,
            "review_comment": "Needs revision.",
            "needs_revision": True,
        },
        {
            "is_consistent": False,
            "review_comment": "Still needs revision.",
            "needs_revision": True,
        },
        {
            "is_consistent": False,
            "review_comment": "Would still revise.",
            "needs_revision": True,
        },
    ]

    # -------------------------
    # Run full graph
    # -------------------------

    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
            "review": {},
            "revision_count": 0,
            "review_status": "",
            "human_review_required": False,
            "human_decision": "",
        },
        config={
            "configurable": {
                "thread_id": "test-max-revisions"
            }
        },
    )

    # -------------------------
    # Verify safety boundary
    # -------------------------

    # Exactly two revisions should have been allowed.
    assert result["revision_count"] == 2

    # The second revision must be the final explanation.
    # There should NOT be a third revision.
    assert result["explanation"]["summary"] == "Revision two"

    # The final AI review still wants another revision...
    assert result["review"]["needs_revision"] is True

    # ...but the automated workflow stops because the configured
    # maximum of two revisions has been reached.
    assert result["review_status"] == "max_revisions_reached"

    # The unresolved case is now escalated to a human reviewer.
    assert result["human_review_required"] is True