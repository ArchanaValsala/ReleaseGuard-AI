from app import assess_release


def test_release_go():
    result = assess_release(
        ci_passed=True,
        critical_issues=0,
    )

    assert result == "GO"


def test_release_no_go_when_ci_fails():
    result = assess_release(
        ci_passed=False,
        critical_issues=0,
    )

    assert result == "NO-GO"


def test_release_no_go_with_critical_issue():
    result = assess_release(
        ci_passed=True,
        critical_issues=1,
    )

    assert result == "NO-GO"