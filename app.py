from github_client import (
    get_open_issues,
    simplify_issues,
    count_issues_by_severity,
    get_latest_workflow_run,
    simplify_workflow_run,
)


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


def main():
    issues = get_open_issues()
    simplified_issues = simplify_issues(issues)
    severity_counts = count_issues_by_severity(simplified_issues)

    workflow_data = get_latest_workflow_run()
    workflow_result = simplify_workflow_run(workflow_data)

    decision = assess_release(
        ci_passed=workflow_result["ci_passed"],
        critical_issues=severity_counts["critical"],
        high_issues=severity_counts["high"],
    )

    print("CI passed:", workflow_result["ci_passed"])
    print("Critical issues:", severity_counts["critical"])
    print("High issues:", severity_counts["high"])
    print("Release decision:", decision)


if __name__ == "__main__":
    main()