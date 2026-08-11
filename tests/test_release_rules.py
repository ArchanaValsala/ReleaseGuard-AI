from release_rules import assess_release


# -------------------------------------------------------------------
# TEST DETERMINISTIC RELEASE RULES
# -------------------------------------------------------------------

# These tests verify the core release policy independently from:
# - LangGraph
# - GitHub
# - OpenAI
# - FastAPI
#
# This is important because the actual GO / NO-GO decision is based on
# deterministic Python rules and should be easy to verify in isolation.


def test_release_go():
    """
    A release should be GO when:
    - CI passed
    - there are no critical issues
    - there are no high-severity issues
    """

    result = assess_release(
        ci_passed=True,
        critical_issues=0,
        high_issues=0,
    )

    assert result == "GO"


def test_release_go_with_conditions():
    """
    A release should be GO WITH CONDITIONS when:
    - CI passed
    - there are no critical issues
    - at least one high-severity issue exists
    """

    result = assess_release(
        ci_passed=True,
        critical_issues=0,
        high_issues=1,
    )

    assert result == "GO WITH CONDITIONS"


def test_release_no_go_when_ci_fails():
    """
    A failed CI result should always block the release,
    even when there are no critical or high-severity issues.
    """

    result = assess_release(
        ci_passed=False,
        critical_issues=0,
        high_issues=0,
    )

    assert result == "NO-GO"


def test_release_no_go_with_critical_issue():
    """
    A critical issue should block the release even when CI passed.
    """

    result = assess_release(
        ci_passed=True,
        critical_issues=1,
        high_issues=0,
    )

    assert result == "NO-GO"