import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from translator import JiraCommandTranslator
from connector import JiraConnector


# ----------------------------------------
# Hardcoded credentials (edit here once)
# ----------------------------------------
JIRA_SERVER = "https://bridgeexample.atlassian.net"
JIRA_EMAIL = "asimazizov5@gmail.com"
JIRA_TOKEN = "ATATT3xFfGF0j9C2yYNw_vDzdcsy4vhBTppG0wUO6GVwl751XIFB73wfHfM9Dz-YY6c42BQbZP5dsRSFLu0gvctdQy3RD0jrdsm8IYOaS51nRDuCE1fEW833vKn32RIoNVxsy7__xFjr_gg3EGnrQBWKRzCIFZ7h_Bl5EgXK3075oaNLPqBLJ2U=7C6C0246"

# Default path for "Take all issues" export (text-based JSON for AI)
DEFAULT_ISSUES_EXPORT_PATH = "issues_export.txt"

# Statuses to exclude from export (e.g. completed); issues with these statuses are not written to the file
EXCLUDED_EXPORT_STATUSES = frozenset({"Done", "Готово"})


def _issue_to_json(connector: JiraConnector, issue: Any, include_comments: bool = True) -> dict[str, Any]:
    """Convert a JIRA Issue to a JSON-serializable dict (for AI / export)."""
    fields = issue.fields
    out: dict[str, Any] = {
        "key": issue.key,
        "id": getattr(issue, "id", None),
        "project": getattr(getattr(fields, "project", None), "key", None),
        "summary": getattr(fields, "summary", None),
        "description": getattr(fields, "description", None) or "",
        "status": getattr(getattr(fields, "status", None), "name", None),
        "issue_type": getattr(getattr(fields, "issuetype", None), "name", None),
        "assignee": getattr(getattr(fields, "assignee", None), "displayName", None),
        "reporter": getattr(getattr(fields, "reporter", None), "displayName", None),
        "priority": getattr(getattr(fields, "priority", None), "name", None),
        "created": getattr(fields, "created", None),
        "updated": getattr(fields, "updated", None),
        "labels": list(getattr(fields, "labels", None) or []),
    }
    if include_comments:
        try:
            comments = connector.get_comments(issue.key)
            out["comments"] = [
                {
                    "author": getattr(getattr(c, "author", None), "displayName", None),
                    "body": getattr(c, "body", None),
                    "created": getattr(c, "created", None),
                }
                for c in comments
            ]
        except Exception:
            out["comments"] = []
    else:
        out["comments"] = []
    return out


def take_all_issues(
    connector: JiraConnector,
    *,
    project_key: str | None = "KAN",
    jql: str | None = None,
    output_file: str | Path = DEFAULT_ISSUES_EXPORT_PATH,
    max_results: int = 0,
    include_comments: bool = True,
) -> dict[str, Any]:
    """
    Fetch all issues (optionally filtered by project or JQL), convert to JSON,
    and store in a text-based file for later use (e.g. sending to AI).
    """
    if jql:
        query = jql
    elif project_key:
        query = f'project = {project_key} ORDER BY updated DESC'
    else:
        query = "assignee = currentUser() ORDER BY updated DESC"

    issues = connector.search_issues(query, max_results=max_results)
    status_name = lambda i: getattr(getattr(i.fields, "status", None), "name", None)
    issues = [i for i in issues if status_name(i) not in EXCLUDED_EXPORT_STATUSES]

    exported_at = datetime.now(timezone.utc).isoformat()

    payload: list[dict[str, Any]] = []
    for issue in issues:
        payload.append(_issue_to_json(connector, issue, include_comments=include_comments))

    data = {
        "exported_at": exported_at,
        "total": len(payload),
        "query": query,
        "issues": payload,
    }

    path = Path(output_file)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"path": str(path.resolve()), "total": len(payload), "output_file": path}


def get_current_tasks_text(
    connector: JiraConnector,
    *,
    project_key: str = "KAN",
    max_results: int = 100,
    include_comments: bool = False,
) -> str:
    """
    Fetch current (non-Done) tasks from JIRA and return them as a single string
    for sending to the chatbot.
    """
    jql = f'project = {project_key} ORDER BY updated DESC'
    issues = connector.search_issues(jql, max_results=max_results)
    status_name = lambda i: getattr(getattr(i.fields, "status", None), "name", None)
    issues = [i for i in issues if status_name(i) not in EXCLUDED_EXPORT_STATUSES]
    payload = [_issue_to_json(connector, i, include_comments=include_comments) for i in issues]
    return json.dumps({"total": len(payload), "issues": payload}, ensure_ascii=False, indent=2)


def _parse_bot_json(raw: str) -> dict[str, Any]:
    """Parse JSON from bot response; strip markdown code blocks if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


# ✅ FIX: Accept user_message as a parameter instead of prompting again
def run_chat_flow(connector: JiraConnector, user_message: str) -> None:
    """
    1. Use the user_message passed from main().
    2. Fetch current tasks from JIRA.
    3. Send user message + current tasks to chatbot.ask_gemini.
    4. Parse response as JSON and execute via translator; print result.
    """
    from chatbot import ask_gemini

    if not user_message:
        print("No message entered.")
        return

    print("\nFetching current tasks from JIRA...")
    try:
        current_tasks = get_current_tasks_text(connector, project_key="KAN", include_comments=False)
    except Exception as e:
        print(f"Failed to fetch tasks: {e}")
        return

    print("Asking Gemini for JSON command...")
    try:
        print("Current tasks:")
        print(current_tasks)
        print("User message:")
        print(user_message)
        response_text = ask_gemini(user_message, current_tasks)
    except Exception as e:
        print(f"Chatbot error: {e}")
        return

    print("\nBot response (raw):", response_text[:500] + ("..." if len(response_text) > 500 else ""))

    try:
        command = _parse_bot_json(response_text)
    except json.JSONDecodeError as e:
        print(f"Could not parse bot output as JSON: {e}")
        print("Raw output above.")
        return

    translator = JiraCommandTranslator(connector)
    try:
        result = translator.execute(command)
        print("\nJIRA result:\n")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("\nError executing command:", e)


def main() -> None:
    connector = JiraConnector(
        server=JIRA_SERVER,
        username=JIRA_EMAIL,
        token=JIRA_TOKEN,
    )

    print("\nJIRA AI Agent ready.")
    print("Type your request in plain English and press Enter.")
    print("Commands:")
    print("  /export  → export all issues")
    print("  /quit    → exit\n")

    while True:
        # ✅ FIX: Single input prompt — one Enter sends the message
        user_input = input("> ").strip()

        if not user_input:
            continue

        if user_input.lower() in {"/quit", "exit"}:
            break

        if user_input.lower() == "/export":
            result = take_all_issues(connector)
            print(f"Exported {result['total']} issues to {result['path']}")
            continue

        # ✅ FIX: Pass user_input directly — no re-prompting inside run_chat_flow
        run_chat_flow(connector, user_input)


if __name__ == "__main__":
    main()