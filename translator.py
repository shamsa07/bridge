"""
Translator from simple JSON commands to JIRA actions via JiraConnector.

Usage pattern (programmatic):

    from translator import JiraCommandTranslator

    translator = JiraCommandTranslator()  # uses env vars for auth
    result = translator.execute({
        "type": "Edit",
        "issueKey": "KAN-123",
        "changeStatus": "Done",
        "addComment": "Everything is fine",
        "summary": "Fix a bug",
        "description": "Stacktrace attached",
    })

The same structure can be provided as a JSON string.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Union

from jira.exceptions import JIRAError

from connector import JiraConnector

JsonDict = Dict[str, Any]
JsonLike = Union[str, JsonDict]


class JiraCommandTranslator:
    """
    Translates high-level JSON commands into calls on JiraConnector.

    Supported command types (case-insensitive):

    - "Create": create a new issue, optionally transition and/or comment
    - "Edit": edit an existing issue (summary, description, fields, status, comments)
    - "GetIssue": fetch a single issue
    - "Search": search with JQL
    - "GetProjectIssues": fetch issues for a project (optional status filter)
    - "GetMyOpenIssues": fetch current user's open issues
    - "GetComments": list comments for an issue
    - "GetTransitions": list available transitions for an issue
    """

    def __init__(self, connector: JiraConnector | None = None) -> None:
        self._connector = connector or JiraConnector()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def execute(self, payload: JsonLike) -> JsonDict:
        """
        Execute a JIRA command described by JSON / dict.

        Args:
            payload: JSON string or already-parsed dict.

        Returns:
            A JSON-serializable dict summarising the result.
        """
        data = self._parse_payload(payload)
        cmd_type_raw = data.get("type")
        if not isinstance(cmd_type_raw, str):
            raise ValueError('Command must include string field "type".')

        cmd_type = cmd_type_raw.lower()

        try:
            if cmd_type == "create":
                return self._handle_create(data)
            if cmd_type == "edit":
                return self._handle_edit(data)
            if cmd_type == "getissue":
                return self._handle_get_issue(data)
            if cmd_type == "search":
                return self._handle_search(data)
            if cmd_type == "getprojectissues":
                return self._handle_get_project_issues(data)
            if cmd_type == "getmyopenissues":
                return self._handle_get_my_open_issues(data)
            if cmd_type == "getcomments":
                return self._handle_get_comments(data)
            if cmd_type == "gettransitions":
                return self._handle_get_transitions(data)
        except JIRAError as e:
            return {
                "ok": False,
                "error": "JIRAError",
                "status_code": getattr(e, "status_code", None),
                "message": str(e),
            }

        raise ValueError(f"Unsupported command type: {cmd_type_raw}")

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def _parse_payload(self, payload: JsonLike) -> JsonDict:
        if isinstance(payload, dict):
            return payload

        text = payload.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Very light "JSON-like" fix: single quotes -> double quotes.
            fixed = text.replace("'", '"')
            return json.loads(fixed)

    # ------------------------------------------------------------------ #
    # Handlers
    # ------------------------------------------------------------------ #

    def _handle_create(self, data: JsonDict) -> JsonDict:
        project = data.get("project")
        summary = data.get("summary")
        if not isinstance(project, str) or not isinstance(summary, str):
            raise ValueError('Create requires "project" (str) and "summary" (str).')

        description = data.get("description") or ""
        issue_type = data.get("issueType") or data.get("issue_type") or "Task"

        # Arbitrary extra JIRA fields
        extra_fields: Dict[str, Any] = data.get("fields") or {}
        if not isinstance(extra_fields, dict):
            raise ValueError('"fields" must be an object when present.')

        issue = self._connector.create_issue(
            project=project,
            summary=summary,
            description=description,
            issue_type=issue_type,
            **extra_fields,
        )

        # Optional post-create status transition
        change_status = data.get("changeStatus")
        if isinstance(change_status, str):
            self._connector.transition_issue(issue.key, change_status)

        # Optional post-create comments
        add_comment = data.get("addComment")
        for comment_body in self._normalize_comments(add_comment):
            self._connector.add_comment(issue.key, comment_body)

        refreshed = self._connector.get_issue(issue.key)
        return {
            "ok": True,
            "type": "Create",
            "issue": self._serialize_issue(refreshed),
        }

    def _handle_edit(self, data: JsonDict) -> JsonDict:
        issue_key = (
            data.get("issueKey")
            or data.get("key")
            or data.get("issue")
        )
        if not isinstance(issue_key, str):
            raise ValueError('Edit requires "issueKey" (or "key"/"issue") as a string.')

        actions: List[str] = []

        # Summary
        if "summary" in data and isinstance(data.get("summary"), str):
            self._connector.update_summary(issue_key, data["summary"])
            actions.append("summary")

        # Description
        if "description" in data and isinstance(data.get("description"), str):
            self._connector.update_description(issue_key, data["description"])
            actions.append("description")

        # Arbitrary fields
        if "fields" in data:
            fields = data["fields"]
            if not isinstance(fields, dict):
                raise ValueError('"fields" must be an object when present.')
            self._connector.update_issue_fields(issue_key, **fields)
            actions.append("fields")

        # Status / transition
        if "changeStatus" in data and isinstance(data.get("changeStatus"), str):
            self._connector.transition_issue(issue_key, data["changeStatus"])
            actions.append("status")

        # Comments
        if "addComment" in data:
            comments = self._normalize_comments(data["addComment"])
            for c in comments:
                self._connector.add_comment(issue_key, c)
            if comments:
                actions.append("comments")

        refreshed = self._connector.get_issue(issue_key)
        return {
            "ok": True,
            "type": "Edit",
            "issue": self._serialize_issue(refreshed),
            "actions": actions,
        }

    def _handle_get_issue(self, data: JsonDict) -> JsonDict:
        issue_key = (
            data.get("issueKey")
            or data.get("key")
            or data.get("issue")
        )
        if not isinstance(issue_key, str):
            raise ValueError('GetIssue requires "issueKey" (or "key"/"issue").')
        issue = self._connector.get_issue(issue_key)
        return {"ok": True, "type": "GetIssue", "issue": self._serialize_issue(issue)}

    def _handle_search(self, data: JsonDict) -> JsonDict:
        jql = data.get("jql")
        if not isinstance(jql, str):
            raise ValueError('Search requires "jql" (str).')
        max_results = int(data.get("maxResults", 50))
        issues = self._connector.search_issues(jql, max_results=max_results)
        return {
            "ok": True,
            "type": "Search",
            "jql": jql,
            "total": len(issues),
            "issues": [self._serialize_issue(i) for i in issues],
        }

    def _handle_get_project_issues(self, data: JsonDict) -> JsonDict:
        project = data.get("project")
        if not isinstance(project, str):
            raise ValueError('GetProjectIssues requires "project" (str).')
        status = data.get("status")
        max_results = int(data.get("maxResults", 50))
        issues = self._connector.get_project_issues(project, status=status, max_results=max_results)
        return {
            "ok": True,
            "type": "GetProjectIssues",
            "project": project,
            "status": status,
            "total": len(issues),
            "issues": [self._serialize_issue(i) for i in issues],
        }

    def _handle_get_my_open_issues(self, data: JsonDict) -> JsonDict:
        max_results = int(data.get("maxResults", 50))
        issues = self._connector.get_my_open_issues(max_results=max_results)
        return {
            "ok": True,
            "type": "GetMyOpenIssues",
            "total": len(issues),
            "issues": [self._serialize_issue(i) for i in issues],
        }

    def _handle_get_comments(self, data: JsonDict) -> JsonDict:
        issue_key = (
            data.get("issueKey")
            or data.get("key")
            or data.get("issue")
        )
        if not isinstance(issue_key, str):
            raise ValueError('GetComments requires "issueKey" (or "key"/"issue").')
        comments = self._connector.get_comments(issue_key)
        return {
            "ok": True,
            "type": "GetComments",
            "issueKey": issue_key,
            "total": len(comments),
            "comments": [
                {
                    "id": getattr(c, "id", None),
                    "author": getattr(getattr(c, "author", None), "displayName", None),
                    "body": getattr(c, "body", None),
                    "created": getattr(c, "created", None),
                }
                for c in comments
            ],
        }

    def _handle_get_transitions(self, data: JsonDict) -> JsonDict:
        issue_key = (
            data.get("issueKey")
            or data.get("key")
            or data.get("issue")
        )
        if not isinstance(issue_key, str):
            raise ValueError('GetTransitions requires "issueKey" (or "key"/"issue").')
        transitions = self._connector.available_transitions(issue_key)
        return {
            "ok": True,
            "type": "GetTransitions",
            "issueKey": issue_key,
            "transitions": transitions,
        }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _serialize_issue(self, issue: Any) -> JsonDict:
        """Return a compact, JSON-friendly representation of a JIRA Issue."""
        fields = issue.fields
        return {
            "key": issue.key,
            "id": getattr(issue, "id", None),
            "summary": getattr(fields, "summary", None),
            "description": getattr(fields, "description", None),
            "status": getattr(getattr(fields, "status", None), "name", None),
            "assignee": getattr(getattr(fields, "assignee", None), "displayName", None),
            "reporter": getattr(getattr(fields, "reporter", None), "displayName", None),
            "project": getattr(getattr(fields, "project", None), "key", None),
        }

    def _normalize_comments(self, add_comment_value: Any) -> List[str]:
        """
        Normalize addComment payload to a list of strings.

        - If None / missing -> []
        - If string -> [string]
        - If list[str] -> that list
        """
        if add_comment_value is None:
            return []
        if isinstance(add_comment_value, str):
            return [add_comment_value]
        if isinstance(add_comment_value, list):
            return [str(v) for v in add_comment_value]
        return [str(add_comment_value)]


def _main() -> None:
    """Simple CLI: read one JSON command from stdin and execute."""
    import sys

    raw = sys.stdin.read()
    translator = JiraCommandTranslator()
    try:
        result = translator.execute(raw)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()

