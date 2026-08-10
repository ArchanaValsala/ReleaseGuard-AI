from release_graph import (
    route_release,
    handle_go,
    handle_go_with_conditions,
    handle_no_go,
    evaluate_release,
    fetch_release_evidence,
    graph,
)
from unittest.mock import patch
from release_graph import graph

def test_route_go():
    state = {
        "decision": "GO"
    }

    result = route_release(state)

    assert result == "go"


def test_route_go_with_conditions():
    state = {
        "decision": "GO WITH CONDITIONS"
    }

    result = route_release(state)

    assert result == "go_with_conditions"


def test_route_no_go():
    state = {
        "decision": "NO-GO"
    }

    result = route_release(state)

    assert result == "no_go"

from release_graph import (
    route_release,
    handle_go,
    handle_go_with_conditions,
    handle_no_go,
)


def test_handle_go():
    result = handle_go({})

    assert result["action_type"] == "release"


def test_handle_go_with_conditions():
    result = handle_go_with_conditions({})

    assert result["action_type"] == "conditional_release"


def test_handle_no_go():
    result = handle_no_go({})

    assert result["action_type"] == "block_release"

def test_evaluate_release():
    state = {
        "release_evidence": {
            "ci_passed": True,
            "critical_issues": 0,
            "high_issues": 1,
        }
    }

    result = evaluate_release(state)

    assert result["decision"] == "GO WITH CONDITIONS"

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
    mock_get_open_issues.return_value = []
    mock_simplify_issues.return_value = []

    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 1,
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

    result = fetch_release_evidence({})

    evidence = result["release_evidence"]

    assert evidence["ci_passed"] is True
    assert evidence["critical_issues"] == 0
    assert evidence["high_issues"] == 1
    assert evidence["low_issues"] == 1


@patch("release_graph.structured_model")
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
    mock_structured_model,
):
    mock_get_open_issues.return_value = []

    mock_simplify_issues.return_value = []

    mock_count_issues_by_severity.return_value = {
        "critical": 0,
        "high": 1,
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

    mock_structured_model.invoke.return_value.model_dump.return_value = {
        "summary": "Test summary",
        "risk_level": "Moderate",
        "recommended_action": "Test action",
    }

    result = graph.invoke(
        {
            "release_evidence": {},
            "decision": "",
            "explanation": {},
            "action_type": "",
        }
    )

    assert result["decision"] == "GO WITH CONDITIONS"

    assert result["action_type"] == "conditional_release"

    assert result["explanation"]["risk_level"] == "Moderate"