import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from typing import TypedDict
from langgraph.graph import StateGraph
from pydantic import BaseModel
from release_rules import assess_release
from github_client import (
    get_open_issues,
    simplify_issues,
    count_issues_by_severity,
    get_latest_workflow_run,
    simplify_workflow_run,
)

load_dotenv()

def get_structured_model():
    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        raise ValueError("OPENAI_API_KEY is required to generate the explanation.")

    model = ChatOpenAI(
        api_key=openai_key,
        model="gpt-5-mini",
    )

    return model.with_structured_output(ReleaseExplanation)

class ReleaseState(TypedDict):
    release_evidence: dict
    decision: str
    explanation: dict
    action_type: str
    review: dict
    revision_count: int
    review_status: str
    human_review_required: bool

def fetch_release_evidence(state: ReleaseState):
    issues = get_open_issues()
    simplified_issues = simplify_issues(issues)
    severity_counts = count_issues_by_severity(simplified_issues)

    workflow_data = get_latest_workflow_run()
    workflow_result = simplify_workflow_run(workflow_data)

    release_evidence = {
        "ci_passed": workflow_result["ci_passed"],
        "ci_status": workflow_result["status"],
        "ci_conclusion": workflow_result["conclusion"],
        "branch": workflow_result["branch"],
        "critical_issues": severity_counts["critical"],
        "high_issues": severity_counts["high"],
        "medium_issues": severity_counts["medium"],
        "low_issues": severity_counts["low"],
    }

    return {
        "release_evidence": release_evidence
    }

def evaluate_release(state: ReleaseState):
    evidence = state["release_evidence"]

    decision = assess_release(
        ci_passed=evidence["ci_passed"],
        critical_issues=evidence["critical_issues"],
        high_issues=evidence["high_issues"],
    )

    return {
        "decision": decision
    }

class ReleaseExplanation(BaseModel):
    summary: str
    risk_level: str
    recommended_action: str

class ReleaseReview(BaseModel):
    is_consistent: bool
    review_comment: str
    needs_revision: bool


def generate_explanation(state: ReleaseState):
    evidence = state["release_evidence"]
    decision = state["decision"]
    action_type = state["action_type"]

    prompt = f"""
    You are assisting a software release manager.

    Release evidence:
    - CI passed: {evidence["ci_passed"]}
    - Critical issues: {evidence["critical_issues"]}
    - High issues: {evidence["high_issues"]}
    - Medium issues: {evidence["medium_issues"]}
    - Low issues: {evidence["low_issues"]}

    Deterministic release decision:
    {decision}
    Action type: {action_type}
    
    Do not change the decision or action type.

    Provide:
    - a short summary
    - a risk level
    - a recommended action
    Keep the recommended action concise.
    """

    structured_model = get_structured_model()
    response = structured_model.invoke(prompt)

    return {
        "explanation": response.model_dump()
    }

def get_review_model():
    openai_key = os.getenv("OPENAI_API_KEY")

    if not openai_key:
        raise ValueError("OPENAI_API_KEY is required to review the explanation.")

    model = ChatOpenAI(
        api_key=openai_key,
        model="gpt-5-mini",
    )

    return model.with_structured_output(ReleaseReview)

def review_explanation(state: ReleaseState):
    explanation = state["explanation"]
    decision = state["decision"]
    action_type = state["action_type"]

    review_model = get_review_model()

    prompt = f"""
You are reviewing an AI-generated software release recommendation.

Deterministic decision:
{decision}

Action type:
{action_type}

AI explanation:
{explanation}

Check whether the explanation is consistent with the deterministic decision
and action type.

Respond with one short sentence saying whether it is consistent.
"""

    response = review_model.invoke(prompt)

    return {
        "review": response.model_dump()
    }

def revise_explanation(state: ReleaseState):
    evidence = state["release_evidence"]
    decision = state["decision"]
    action_type = state["action_type"]
    explanation = state["explanation"]
    review = state["review"]

    structured_model = get_structured_model()
    revision_count = state["revision_count"]

    prompt = f"""
You are revising a software release explanation.

Release evidence:
{evidence}

Deterministic decision:
{decision}

Action type:
{action_type}

Current explanation:
{explanation}

Reviewer feedback:
{review}

Revise the explanation so that it is fully consistent with the deterministic
decision and action type.

Do not change the decision or action type.

Keep the response concise.
"""

    response = structured_model.invoke(prompt)

    return {
        "explanation": response.model_dump(),
        "revision_count": revision_count + 1,
   }

def route_review(state: ReleaseState):
    review = state["review"]
    revision_count = state["revision_count"]

    if review["needs_revision"] and revision_count < 2:
        return "revise"

    return "end"

def finalize_review_status(state: ReleaseState):
    review = state["review"]
    revision_count = state["revision_count"]

    if not review["needs_revision"]:
        status = "approved"
        human_review_required = False

    elif revision_count >= 2:
        status = "max_revisions_reached"
        human_review_required = True

    else:
        status = "pending"
        human_review_required = False

    return {
        "review_status": status,
        "human_review_required": human_review_required,
    }

def handle_go(state: ReleaseState):
    return {
        "action_type": "release"
    }


def handle_go_with_conditions(state: ReleaseState):
    return {
        "action_type": "conditional_release"
    }


def handle_no_go(state: ReleaseState):
    return {
        "action_type": "block_release"
    }

def route_release(state: ReleaseState):
    decision = state["decision"]

    if decision == "GO":
        return "go"

    elif decision == "GO WITH CONDITIONS":
        return "go_with_conditions"

    else:
        return "no_go"

  
builder = StateGraph(ReleaseState)

builder.add_node(
    "fetch_release_evidence",
    fetch_release_evidence,
)

builder.add_node(
    "evaluate_release",
    evaluate_release,
)
builder.add_node(
    "generate_explanation",
    generate_explanation,
)
builder.add_node(
    "handle_go",
    handle_go,
)

builder.add_node(
    "handle_go_with_conditions",
    handle_go_with_conditions,
)

builder.add_node(
    "handle_no_go",
    handle_no_go,
)
builder.add_node(
    "review_explanation",
    review_explanation,
)
builder.add_node(
    "revise_explanation",
    revise_explanation,
)
builder.add_node(
    "finalize_review_status",
    finalize_review_status,
)
builder.set_entry_point("fetch_release_evidence")
builder.add_edge(
    "fetch_release_evidence",
    "evaluate_release",
)
builder.add_conditional_edges(
    "evaluate_release",
    route_release,
    {
        "go": "handle_go",
        "go_with_conditions": "handle_go_with_conditions",
        "no_go": "handle_no_go",
    },
)
builder.add_conditional_edges(
    "review_explanation",
    route_review,
    {
        "revise": "revise_explanation",
        "end": "finalize_review_status",
    },
)
builder.add_edge(
    "handle_go",
    "generate_explanation",
)

builder.add_edge(
    "handle_go_with_conditions",
    "generate_explanation",
)

builder.add_edge(
    "handle_no_go",
    "generate_explanation",
)
builder.add_edge(
    "generate_explanation",
    "review_explanation",
)
builder.add_edge(
    "revise_explanation",
    "review_explanation",
)
builder.set_finish_point("finalize_review_status")

graph = builder.compile()