import os
import requests

from dotenv import load_dotenv


# -------------------------------------------------------------------
# ENVIRONMENT CONFIGURATION
# -------------------------------------------------------------------

# Load values from the local .env file.
#
# Expected variables:
# - GITHUB_TOKEN
# - GITHUB_OWNER
# - GITHUB_REPO
#
# Keeping repository details in .env makes the code reusable for a
# different GitHub repository without changing the Python source.
load_dotenv()

github_token = os.getenv("GITHUB_TOKEN")
github_owner = os.getenv("GITHUB_OWNER")
github_repo = os.getenv("GITHUB_REPO")


# -------------------------------------------------------------------
# REPOSITORY INFORMATION
# -------------------------------------------------------------------

def get_repository_info():
    """
    Fetch basic information about the configured GitHub repository.

    This function is mainly useful for:
    - checking that authentication/configuration works
    - confirming the repository being used
    - local debugging

    It is not part of the main release-risk calculation.
    """

    url = f"https://api.github.com/repos/{github_owner}/{github_repo}"

    # GitHub uses the token for authenticated API access.
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(
        url,
        headers=headers,
    )

    # Convert HTTP errors such as 401, 403, or 404 into Python exceptions
    # instead of silently continuing with an invalid response.
    response.raise_for_status()

    return response.json()


# -------------------------------------------------------------------
# OPEN ISSUES
# -------------------------------------------------------------------

def get_open_issues():
    """
    Fetch all currently open items from GitHub's /issues endpoint.

    Important:
    GitHub's /issues endpoint can return both real issues and pull requests.

    This function only fetches the raw API response.
    Pull requests are filtered later inside simplify_issues().
    """

    url = (
        f"https://api.github.com/repos/"
        f"{github_owner}/{github_repo}/issues"
    )

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    # Only request items that are currently open.
    params = {
        "state": "open"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
    )

    response.raise_for_status()

    return response.json()


# -------------------------------------------------------------------
# SIMPLIFY ISSUE DATA
# -------------------------------------------------------------------

def simplify_issues(issues):
    """
    Convert the large GitHub issue response into the small structure
    ReleaseGuard actually needs.

    For each real issue, we keep:
    - issue number
    - issue title
    - severity

    Pull requests are ignored because GitHub's /issues endpoint may
    return them alongside normal issues.

    If an issue accidentally contains more than one severity label,
    the highest severity is selected using this priority:

    critical > high > medium > low
    """

    simplified_issues = []

    for issue in issues:

        # GitHub includes a "pull_request" field when the item is a PR.
        # Skip these so PR labels do not incorrectly affect release risk.
        if "pull_request" in issue:
            continue

        # Extract only the label names from GitHub's label objects.
        labels = [
            label["name"]
            for label in issue["labels"]
        ]

        # If no supported severity label is found, keep the issue as unknown.
        severity = "unknown"

        # Use explicit severity precedence.
        #
        # This avoids relying on the order of labels returned by GitHub.
        # If multiple severity labels exist, the most serious one wins.
        for severity_level in ["critical", "high", "medium", "low"]:
            if severity_level in labels:
                severity = severity_level
                break

        simplified_issues.append(
            {
                "number": issue["number"],
                "title": issue["title"],
                "severity": severity,
            }
        )

    return simplified_issues


# -------------------------------------------------------------------
# COUNT ISSUES BY SEVERITY
# -------------------------------------------------------------------

def count_issues_by_severity(issues):
    """
    Count the simplified issues by severity.

    The resulting totals are later used by the deterministic
    release decision rules.
    """

    counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "unknown": 0,
    }

    for issue in issues:
        severity = issue["severity"]

        counts[severity] += 1

    return counts


# -------------------------------------------------------------------
# GITHUB ACTIONS / CI
# -------------------------------------------------------------------

def get_latest_workflow_run():
    """
    Fetch the latest GitHub Actions workflow run.

    ReleaseGuard currently uses this as the CI signal for the release
    assessment.

    per_page=1 tells GitHub that we only need the latest run.
    """

    url = (
        f"https://api.github.com/repos/"
        f"{github_owner}/{github_repo}/actions/runs"
    )

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    params = {
        "per_page": 1
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
    )

    response.raise_for_status()

    data = response.json()

    return data


# -------------------------------------------------------------------
# SIMPLIFY CI / WORKFLOW DATA
# -------------------------------------------------------------------

def simplify_workflow_run(workflow_data):
    """
    Convert the GitHub Actions API response into the small CI structure
    used by ReleaseGuard.

    It also safely handles the case where the repository has no
    workflow runs at all.
    """

    # get() with a default empty list avoids KeyError if workflow_runs
    # is missing from the API response.
    workflow_runs = workflow_data.get("workflow_runs", [])

    # Edge case:
    # If there is no CI run, ReleaseGuard should not assume that CI passed.
    #
    # ci_passed=False is a conservative fallback because there is no
    # evidence that the release has passed CI.
    if not workflow_runs:
        return {
            "ci_passed": False,
            "status": "not_found",
            "conclusion": None,
            "branch": None,
        }

    # Because get_latest_workflow_run() requests per_page=1,
    # the first item should be the latest workflow run.
    latest_run = workflow_runs[0]

    # Only an explicit GitHub Actions conclusion of "success"
    # is treated as a passing CI result.
    ci_passed = latest_run["conclusion"] == "success"

    return {
        "ci_passed": ci_passed,
        "status": latest_run["status"],
        "conclusion": latest_run["conclusion"],
        "branch": latest_run["head_branch"],
    }


# ===================================================================
# LOCAL MANUAL TEST / DEBUG SECTION
# ===================================================================

# This block runs only when the file is executed directly:
#
#     python github_client.py
#
# It does NOT run when github_client.py is imported by release_graph.py.
#
# This is useful for quickly verifying:
# - GitHub credentials
# - repository configuration
# - issue retrieval
# - severity counting
# - GitHub Actions retrieval
if __name__ == "__main__":

    # ---------------------------------------------------------------
    # Repository information
    # ---------------------------------------------------------------

    repo_info = get_repository_info()

    print("Repository:", repo_info["name"])
    print("Owner:", repo_info["owner"]["login"])
    print("Visibility:", repo_info["visibility"])
    print("Default branch:", repo_info["default_branch"])

    # ---------------------------------------------------------------
    # Open issues
    # ---------------------------------------------------------------

    issues = get_open_issues()

    simplified_issues = simplify_issues(issues)

    print("\nOpen issues:")

    for issue in simplified_issues:
        print(issue)

    # ---------------------------------------------------------------
    # Severity counts
    # ---------------------------------------------------------------

    severity_counts = count_issues_by_severity(simplified_issues)

    print("\nSeverity counts:")
    print("Critical:", severity_counts["critical"])
    print("High:", severity_counts["high"])
    print("Medium:", severity_counts["medium"])
    print("Low:", severity_counts["low"])

    # ---------------------------------------------------------------
    # Latest GitHub Actions run
    # ---------------------------------------------------------------

    workflow_data = get_latest_workflow_run()

    workflow_result = simplify_workflow_run(workflow_data)

    print("\nLatest workflow:")
    print(workflow_result)