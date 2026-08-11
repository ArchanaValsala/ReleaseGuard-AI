# ReleaseGuard AI

ReleaseGuard AI is a software release risk assessment project built with Python, LangGraph, OpenAI, FastAPI, Streamlit, GitHub API, pytest and GitHub Actions.

It uses live GitHub issue data and the latest CI result to assess whether a release should be:

- **GO**
- **GO WITH CONDITIONS**
- **NO-GO**

The release decision itself is made using deterministic Python rules. The LLM is used to explain the decision, review the explanation for consistency, and revise it when needed.

<img width="442" height="573" alt="image" src="https://github.com/user-attachments/assets/91c76e84-9f81-470b-9710-1e7b10a84066" />

## How it works

1. The user starts a release assessment from the Streamlit app.
2. ReleaseGuard fetches the latest GitHub data:
   - open issues and their severity
   - the latest CI test result from GitHub Actions, showing whether the automated checks passed or failed
3. Python rules decide whether the release is **GO**, **GO WITH CONDITIONS**, or **NO-GO**.
4. OpenAI creates a short explanation of that decision.
5. A review step checks whether the explanation matches the actual release decision.
6. If the explanation is not consistent, it is revised and checked again.
7. After two failed revision attempts, the case is sent for human review.
8. The assessment state is saved with a unique thread ID, and progress is shown live in the Streamlit app.

## Release rules

| Condition | Decision |
| --- | --- |
| CI failed | NO-GO |
| Critical issue exists | NO-GO |
| High-severity issue exists | GO WITH CONDITIONS |
| Otherwise | GO |

## Architecture

```text
Streamlit
   ↓
FastAPI
   ↓
LangGraph
   ↓
GitHub Issues + GitHub Actions
   ↓
Deterministic Release Rules
   ↓
GO / GO WITH CONDITIONS / NO-GO
   ↓
AI Explanation
   ↓
AI Review
   ↓
Revision / Human Review if needed
```
<img width="540" height="340" alt="image" src="https://github.com/user-attachments/assets/af6a829d-9b59-4863-bbdd-30a2cb6857e8" />

## Tech stack

- Python
- LangGraph
- LangChain / OpenAI
- FastAPI
- Streamlit
- GitHub REST API
- Pydantic
- pytest
- GitHub Actions

## Run locally

Install the dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file and add:

```text
OPENAI_API_KEY=
GITHUB_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
```

Start the FastAPI backend:

```bash
uvicorn api:app --reload
```

In a second terminal, start the Streamlit UI:

```bash
streamlit run streamlit_app.py
```

Then open the Streamlit URL shown in the terminal and click **Assess Release**.

## Tests and CI

GitHub Actions runs the pytest suite automatically on pushes and pull requests.

<img width="1376" height="739" alt="image" src="https://github.com/user-attachments/assets/fc42be84-76a5-49f1-99de-74b8cbb63449" />



