def assess_release(
    ci_passed: bool,
    critical_issues: int,
    high_issues: int,
) -> str:

    if not ci_passed:
        return "NO-GO"

    if critical_issues > 0:
        return "NO-GO"

    if high_issues > 0:
        return "GO WITH CONDITIONS"

    return "GO"