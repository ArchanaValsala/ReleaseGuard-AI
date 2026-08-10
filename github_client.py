import os
import requests

from dotenv import load_dotenv


load_dotenv()

github_token = os.getenv("GITHUB_TOKEN")


def get_repository_info():
    url = "https://api.github.com/repos/ArchanaValsala/ReleaseGuard-AI"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    response = requests.get(
        url,
        headers=headers,
    )

    response.raise_for_status()

    return response.json()


def get_open_issues():
    url = "https://api.github.com/repos/ArchanaValsala/ReleaseGuard-AI/issues"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

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


def simplify_issues(issues):
    simplified_issues = []

    for issue in issues:
        labels = [
            label["name"]
            for label in issue["labels"]
        ]

        severity = "unknown"

        for label in labels:
            if label in ["critical", "high", "medium", "low"]:
                severity = label

        simplified_issues.append(
            {
                "number": issue["number"],
                "title": issue["title"],
                "severity": severity,
            }
        )

    return simplified_issues

def count_issues_by_severity(issues):
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

def get_latest_workflow_run():
    url = "https://api.github.com/repos/ArchanaValsala/ReleaseGuard-AI/actions/runs"

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

def simplify_workflow_run(workflow_data):
    latest_run = workflow_data["workflow_runs"][0]

    ci_passed = latest_run["conclusion"] == "success"

    return {
        "ci_passed": ci_passed,
        "status": latest_run["status"],
        "conclusion": latest_run["conclusion"],
        "branch": latest_run["head_branch"],
    }

if __name__ == "__main__":
    repo_info = get_repository_info()

    print("Repository:", repo_info["name"])
    print("Owner:", repo_info["owner"]["login"])
    print("Visibility:", repo_info["visibility"])
    print("Default branch:", repo_info["default_branch"])

    issues = get_open_issues()

    simplified_issues = simplify_issues(issues)

    print("\nOpen issues:")

    for issue in simplified_issues:
        print(issue)

    severity_counts = count_issues_by_severity(simplified_issues)

    print("\nSeverity counts:")
    print("Critical:", severity_counts["critical"])
    print("High:", severity_counts["high"])
    print("Medium:", severity_counts["medium"])
    print("Low:", severity_counts["low"])

    workflow_data = get_latest_workflow_run()

    workflow_result = simplify_workflow_run(workflow_data)

    print("\nLatest workflow:")
    print(workflow_result)