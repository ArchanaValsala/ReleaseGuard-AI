# -------------------------------------------------------------------
# DETERMINISTIC RELEASE DECISION RULES
# -------------------------------------------------------------------

def assess_release(
    ci_passed: bool,
    critical_issues: int,
    high_issues: int,
) -> str:
    """
    Decide whether a release should proceed based on fixed business rules.

    This function is intentionally deterministic.

    The LLM does NOT make the actual GO / NO-GO decision because release
    gates should be predictable, auditable, and easy to test.

    Decision rules:

    1. If CI failed:
       → NO-GO

    2. If there is at least one critical issue:
       → NO-GO

    3. If there is at least one high-severity issue:
       → GO WITH CONDITIONS

    4. Otherwise:
       → GO
    """

    # A release should never proceed when CI has failed.
    if not ci_passed:
        return "NO-GO"

    # Even with passing CI, a critical open issue blocks the release.
    if critical_issues > 0:
        return "NO-GO"

    # High-severity issues do not fully block the release in the current
    # policy, but they require additional conditions or attention.
    if high_issues > 0:
        return "GO WITH CONDITIONS"

    # If CI passed and there are no critical or high-severity issues,
    # the release is considered safe to proceed.
    return "GO"