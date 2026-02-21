"""
JIRA connector for the Bridge app.

Supports:
- Fetching tasks (by key, JQL search, or project)
- Creating issues
- Updating status (transitions), description, and comments

Configure via environment variables (see .env.example) or pass options to JiraConnector().
"""

import os
from typing import Any

from jira import JIRA
from jira.resources import Issue
from jira.exceptions import JIRAError


class JiraConnector:
    """Connects to JIRA and provides methods to fetch, create, and update issues."""

    def __init__(
        self,
        server: str | None = None,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        **options: Any,
    ):
        """
        Initialize the JIRA client.

        For Jira Cloud: use server, username (email), and token (API token).
        For Jira Server/Data Center: use server, username, and password.

        Args:
            server: JIRA base URL (e.g. https://your-domain.atlassian.net)
            username: Email (Cloud) or username (Server)
            password: Password (Server). Ignored if token is set.
            token: API token (Cloud). Preferred over password for Cloud.
            **options: Extra options passed to jira.JIRA (e.g. verify, timeout).
        """
        server = server or os.environ.get("JIRA_SERVER", "").rstrip("/")
        username = username or os.environ.get("JIRA_USERNAME") or os.environ.get("JIRA_EMAIL")
        password = password or os.environ.get("JIRA_PASSWORD")
        token = token or os.environ.get("JIRA_API_TOKEN")

        if not server or not username:
            raise ValueError("JIRA_SERVER and JIRA_USERNAME (or JIRA_EMAIL) must be set")

        # Cloud: API token; Server: password
        basic_auth = (username, token or password or "")
        if not basic_auth[1]:
            raise ValueError("Set JIRA_API_TOKEN (Cloud) or JIRA_PASSWORD (Server)")

        self._jira = JIRA(server=server, basic_auth=basic_auth, **options)
        self._server = server

    # -------------------------------------------------------------------------
    # Fetch tasks
    # -------------------------------------------------------------------------

    def get_issue(self, issue_key: str) -> Issue:
        """Fetch a single issue by key (e.g. KAN-123)."""
        return self._jira.issue(issue_key)

    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        fields: str | list[str] | None = None,
    ) -> list[Issue]:
        """
        Search issues using JQL.

        Args:
            jql: JQL query (e.g. 'project = MYPROJ AND status = Open')
            start_at: Index of first result
            max_results: Max issues to return (0 = no limit, fetches in batches)
            fields: Fields to return (default all). Use list or comma-separated string.

        Returns:
            List of Issue objects.
        """
        return self._jira.search_issues(
            jql,
            startAt=start_at,
            maxResults=max_results,
            fields=fields or "*all",
        )

    def get_project_issues(
        self,
        project_key: str,
        status: str | None = None,
        max_results: int = 50,
    ) -> list[Issue]:
        """Fetch issues for a project, optionally filtered by status."""
        jql = f"project = {project_key}"
        if status:
            jql += f" AND status = \"{status}\""
        return self.search_issues(jql, max_results=max_results)

    def get_my_open_issues(self, max_results: int = 50) -> list[Issue]:
        """Fetch issues assigned to the current user that are not done."""
        return self.search_issues(
            "assignee = currentUser() AND status != Done ORDER BY updated DESC",
            max_results=max_results,
        )

    # -------------------------------------------------------------------------
    # Create
    # -------------------------------------------------------------------------

    def create_issue(
        self,
        project: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        **field_overrides: Any,
    ) -> Issue:
        """
        Create a new issue.

        Args:
            project: Project key (e.g. KAN)
            summary: Issue title/summary
            description: Issue description (optional)
            issue_type: Type name (e.g. Task, Bug, Story). Default: Task.
            **field_overrides: Any other JIRA fields (e.g. assignee={'name': 'user'}, priority='High').

        Returns:
            The created Issue.
        """
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }
        fields.update(field_overrides)
        return self._jira.create_issue(fields=fields)

    # -------------------------------------------------------------------------
    # Update status, description, comments
    # -------------------------------------------------------------------------

    def update_description(self, issue_key: str, description: str) -> Issue:
        """Update an issue's description. Returns the issue after refresh."""
        issue = self._jira.issue(issue_key)
        issue.update(fields={"description": description})
        return self._jira.issue(issue_key)

    def update_summary(self, issue_key: str, summary: str) -> Issue:
        """Update an issue's summary/title."""
        issue = self._jira.issue(issue_key)
        issue.update(fields={"summary": summary})
        return self._jira.issue(issue_key)

    def transition_issue(self, issue_key: str, transition_name: str) -> None:
        """
        Move an issue to a new status by transition name.

        Examples: 'In Progress', 'Done', 'To Do', 'Closed'.
        Available transitions depend on your workflow.
        """
        self._jira.transition_issue(issue_key, transition_name)

    def add_comment(self, issue_key: str, body: str) -> Any:
        """Add a comment to an issue. Returns the created Comment."""
        return self._jira.add_comment(issue_key, body)

    def get_comments(self, issue_key: str) -> list[Any]:
        """Get all comments for an issue."""
        issue = self._jira.issue(issue_key, expand="renderedFields")
        return list(issue.fields.comment.comments)

    def update_issue_fields(self, issue_key: str, **fields: Any) -> Issue:
        """
        Update arbitrary issue fields.

        Examples:
            connector.update_issue_fields("KAN-1", description="New desc", summary="New title")
            connector.update_issue_fields("KAN-1", assignee={"name": "jane"})
        """
        issue = self._jira.issue(issue_key)
        issue.update(fields=fields)
        return self._jira.issue(issue_key)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def available_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        """List transitions available for an issue (e.g. to show possible status changes)."""
        return self._jira.transitions(issue_key)

    @property
    def jira(self) -> JIRA:
        """Access the underlying jira.JIRA client for advanced use."""
        return self._jira


# -----------------------------------------------------------------------------
# CLI / script usage
# -----------------------------------------------------------------------------

def _main() -> None:
    """Example usage when run as script. Set env vars or edit below."""
    import argparse

    parser = argparse.ArgumentParser(description="JIRA connector: fetch, create, update issues")
    parser.add_argument("--server", default=os.environ.get("JIRA_SERVER"), help="JIRA URL")
    parser.add_argument("--user", default=os.environ.get("JIRA_USERNAME", os.environ.get("JIRA_EMAIL")), help="Username/email")
    parser.add_argument("--token", default=os.environ.get("JIRA_API_TOKEN"), help="API token (Cloud) or use JIRA_PASSWORD")
    sub = parser.add_subparsers(dest="action", required=True)

    # Fetch
    p_fetch = sub.add_parser("fetch", help="Fetch issue by key")
    p_fetch.add_argument("key", help="Issue key (e.g. KAN-123)")

    p_search = sub.add_parser("search", help="Search with JQL")
    p_search.add_argument("jql", help="JQL query")
    p_search.add_argument("--max", type=int, default=10, help="Max results")

    # Create
    p_create = sub.add_parser("create", help="Create issue")
    p_create.add_argument("--project", "-p", required=True, help="Project key")
    p_create.add_argument("--summary", "-s", required=True, help="Summary/title")
    p_create.add_argument("--description", "-d", default="", help="Description")
    p_create.add_argument("--type", "-t", default="Task", dest="issue_type", help="Issue type")

    # Update
    p_desc = sub.add_parser("description", help="Update description")
    p_desc.add_argument("key", help="Issue key")
    p_desc.add_argument("text", help="New description")

    p_status = sub.add_parser("status", help="Transition status")
    p_status.add_argument("key", help="Issue key")
    p_status.add_argument("transition", help="Transition name (e.g. In Progress, Done)")

    p_comment = sub.add_parser("comment", help="Add comment")
    p_comment.add_argument("key", help="Issue key")
    p_comment.add_argument("text", help="Comment body")

    args = parser.parse_args()

    try:
        conn = JiraConnector(
            server="https://bridgeexample.atlassian.net",
            username="shamsabakhshaliyeva@gmail.com",
            token="ATATT3xFfGF0vGCF8WxWw2xrq_Q5tEX_mSYqO8tJm2i-8nHuM04PJs5gzf_lotgYFLJJUsgb4_Vn5zFLZGLE2Gn70hOT6v03vZyYDmMmVXyall8Stv6rDO-qh58LeYpr9xCMRNfSSHQh_OandMJBAfE248Lu21FqH7oSuNtHnuMJpUa06qVeCWE=6C207FBD",
        )
    except (ValueError, JIRAError) as e:
        print(f"Connection error: {e}")
        return

    if args.action == "fetch":
        issue = conn.get_issue(args.key)
        print(f"{issue.key}: {issue.fields.summary}")
        print(f"  Status: {issue.fields.status.name}")
        print(f"  Description: {(issue.fields.description or '')[:200]}...")

    elif args.action == "search":
        issues = conn.search_issues(args.jql, max_results=args.max)
        for i in issues:
            print(f"  {i.key}: {i.fields.summary} [{i.fields.status.name}]")

    elif args.action == "create":
        issue = conn.create_issue(
            project=args.project,
            summary=args.summary,
            description=args.description,
            issue_type=args.issue_type,
        )
        print(f"Created: {issue.key} - {issue.fields.summary}")

    elif args.action == "description":
        conn.update_description(args.key, args.text)
        print(f"Updated description of {args.key}")

    elif args.action == "status":
        conn.transition_issue(args.key, args.transition)
        print(f"Moved {args.key} to '{args.transition}'")

    elif args.action == "comment":
        conn.add_comment(args.key, args.text)
        print(f"Comment added to {args.key}")


if __name__ == "__main__":
    _main()
