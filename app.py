def assess_release(ci_passed: bool, critical_issues: int) -> str:
    if not ci_passed:
        return "NO-GO"

    if critical_issues > 0:
        return "NO-GO"

    return "GO"


def main():
    decision = assess_release(
        ci_passed=False,
        critical_issues=0,
    )

    print("Release decision:", decision)


if __name__ == "__main__":
    main()