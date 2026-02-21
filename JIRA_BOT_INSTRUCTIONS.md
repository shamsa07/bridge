# JIRA connector – bot instructions

Use this document as the single source of truth for what the JIRA integration can do and how to call it.

**How to call:** Send **one** JSON object per action. The object must have a `"type"` field. All other fields depend on the type. The receiver (translator) runs the action and returns a result object (`ok: true/false`, plus data or error message).

**Project and issue keys:** In this project, the JIRA project key is **KAN**. Issues are **KAN-1**, **KAN-2**, etc. Use these in examples and in real commands.

**Important:** For any command that needs an issue, you can use **either** `issueKey`, or `key`, or `issue` (same meaning).

---

## 1. Create – create a new issue

Create a new JIRA issue in project KAN (or another project if you set `project`).

**Required:** `type`, `project`, `summary`  
**Optional:** `description`, `issueType` (or `issue_type`), `fields`, `changeStatus`, `addComment`

### Minimal – project + summary only

```json
{
  "type": "Create",
  "project": "KAN",
  "summary": "Fix login timeout"
}
```

### With description and issue type

```json
{
  "type": "Create",
  "project": "KAN",
  "summary": "Fix login timeout",
  "description": "Users see timeout after 30s. Stacktrace attached.",
  "issueType": "Bug"
}
```

### With extra fields (priority, labels, assignee)

```json
{
  "type": "Create",
  "project": "KAN",
  "summary": "Add health check endpoint",
  "description": "We need GET /health for the load balancer.",
  "issueType": "Task",
  "fields": {
    "priority": { "name": "High" },
    "labels": ["backend", "ops"],
    "assignee": { "name": "jane.doe" }
  }
}
```

### Create and move to a status + add comment

```json
{
  "type": "Create",
  "project": "KAN",
  "summary": "Hotfix for payment bug",
  "description": "Critical; repro steps in description.",
  "issueType": "Bug",
  "changeStatus": "In Progress",
  "addComment": "Created from monitoring alert #42"
}
```

### Multiple comments (array)

```json
{
  "type": "Create",
  "project": "KAN",
  "summary": "Investigate slow search",
  "description": "Search takes >2s under load.",
  "addComment": [
    "Initial triage started",
    "Logs attached"
  ]
}
```

---

## 2. Edit – update an existing issue

Change summary, description, status, and/or add comments for one issue. You can combine any of the optional fields.

**Required:** `type`, and one of `issueKey` / `key` / `issue` (the issue key, e.g. KAN-5)  
**Optional:** `summary`, `description`, `changeStatus`, `addComment`, `fields`

### Change status only

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "changeStatus": "In Progress"
}
```

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "changeStatus": "Done"
}
```

### Add one comment only

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "addComment": "Deployed to staging. Ready for QA."
}
```

### Add multiple comments

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "addComment": [
    "First update: repro confirmed",
    "Second: fix implemented"
  ]
}
```

### Update summary only

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "summary": "Fix login timeout (backend)"
}
```

### Update description only

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "description": "Full stacktrace:\n\n...\n\nSteps to reproduce: 1. ..."
}
```

### Update summary and description (no status/comment)

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "summary": "Fix login timeout",
  "description": "Updated with stacktrace and repro steps."
}
```

### Full edit – status + comment + summary + description

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "changeStatus": "Done",
  "addComment": "Verified in production.",
  "summary": "Fix login timeout",
  "description": "Stacktrace attached. Root cause: connection pool."
}
```

### Edit arbitrary fields (priority, labels, assignee, etc.)

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "fields": {
    "priority": { "name": "High" },
    "labels": ["urgent", "backend"],
    "assignee": { "name": "jane.doe" }
  }
}
```

### Combined: summary + description + status + comments + fields

```json
{
  "type": "Edit",
  "issueKey": "KAN-5",
  "summary": "Fix login timeout",
  "description": "Stacktrace attached.",
  "changeStatus": "Done",
  "addComment": "All good.",
  "fields": {
    "priority": { "name": "Medium" },
    "labels": ["bugfix"]
  }
}
```

---

## 3. GetIssue – fetch one issue by key

Get full details of a single issue.

**Required:** `type`, and one of `issueKey` / `key` / `issue`

```json
{
  "type": "GetIssue",
  "issueKey": "KAN-3"
}
```

```json
{
  "type": "GetIssue",
  "key": "KAN-7"
}
```

---

## 4. Search – search issues with JQL

Run a JQL query and get a list of matching issues.

**Required:** `type`, `jql`  
**Optional:** `maxResults` (number, default 50)

```json
{
  "type": "Search",
  "jql": "project = KAN AND status = \"In Progress\" ORDER BY updated DESC",
  "maxResults": 20
}
```

```json
{
  "type": "Search",
  "jql": "project = KAN ORDER BY created DESC",
  "maxResults": 50
}
```

```json
{
  "type": "Search",
  "jql": "assignee = currentUser() AND project = KAN"
}
```

---

## 5. GetProjectIssues – list issues in a project

Get issues for a project, optionally filtered by status.

**Required:** `type`, `project`  
**Optional:** `status`, `maxResults` (default 50)

```json
{
  "type": "GetProjectIssues",
  "project": "KAN"
}
```

```json
{
  "type": "GetProjectIssues",
  "project": "KAN",
  "status": "To Do",
  "maxResults": 30
}
```

```json
{
  "type": "GetProjectIssues",
  "project": "KAN",
  "status": "In Progress"
}
```

---

## 6. GetMyOpenIssues – list current user’s open issues

Get issues assigned to the current user that are not Done.

**Required:** `type`  
**Optional:** `maxResults` (default 50)

```json
{
  "type": "GetMyOpenIssues"
}
```

```json
{
  "type": "GetMyOpenIssues",
  "maxResults": 20
}
```

---

## 7. GetComments – list comments on an issue

Get all comments for a given issue.

**Required:** `type`, and one of `issueKey` / `key` / `issue`

```json
{
  "type": "GetComments",
  "issueKey": "KAN-5"
}
```

---

## 8. GetTransitions – list allowed status changes

Get the list of transitions (status changes) currently available for an issue. Use this to know valid values for `changeStatus` when editing.

**Required:** `type`, and one of `issueKey` / `key` / `issue`

```json
{
  "type": "GetTransitions",
  "issueKey": "KAN-5"
}
```

---

## Quick reference – command types and fields

| type              | Required fields     | Optional fields                          |
|-------------------|---------------------|------------------------------------------|
| Create            | project, summary    | description, issueType, fields, changeStatus, addComment |
| Edit              | issueKey (or key/issue) | summary, description, changeStatus, addComment, fields |
| GetIssue          | issueKey (or key/issue) | —                                        |
| Search            | jql                 | maxResults                               |
| GetProjectIssues  | project             | status, maxResults                       |
| GetMyOpenIssues   | —                   | maxResults                               |
| GetComments       | issueKey (or key/issue) | —                                    |
| GetTransitions    | issueKey (or key/issue) | —                                    |

---

## Result format

- **Success:** The response is a JSON object with `"ok": true`, plus type-specific data (e.g. `issue`, `issues`, `comments`, `transitions`).
- **Failure:** The response has `"ok": false` and usually `"error"`, `"message"`, and optionally `"status_code"` (for JIRA errors).

Example success (GetIssue):

```json
{
  "ok": true,
  "type": "GetIssue",
  "issue": {
    "key": "KAN-5",
    "id": "12345",
    "summary": "Fix login",
    "description": "...",
    "status": "In Progress",
    "assignee": "Jane Doe",
    "reporter": "John Doe",
    "project": "KAN"
  }
}
```

Example failure:

```json
{
  "ok": false,
  "error": "JIRAError",
  "status_code": 404,
  "message": "Issue not found."
}
```

---

## Summary for the bot

- You can **create** issues (project KAN, summary required; optional description, type, fields, status, comments).
- You can **edit** issues (identify by KAN-&lt;n&gt;; optionally update summary, description, status, comments, or other fields).
- You can **read** one issue (GetIssue), **search** by JQL (Search), **list** by project (GetProjectIssues) or **my open** issues (GetMyOpenIssues).
- You can **list comments** (GetComments) and **list allowed status changes** (GetTransitions) for an issue.
- Always send a single JSON object with `"type"` and the fields listed above. Use the examples in this document as the exact format for each action.
