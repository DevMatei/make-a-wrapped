---
name: API bug report
about: Report a problem with the Make a Wrapped API
title: ''
labels: ''
assignees: ''

---

**Endpoint**
Which endpoint and HTTP method are you calling? For example, `POST /api/v1/wrapped`.

**Request**
Share a minimal request that reproduces the problem. Redact usernames or other personal data if needed.

```json
{
  "source": {
    "type": "provider",
    "provider": "listenbrainz",
    "username": "REDACTED"
  }
}
```

If the request depends on headers or a particular client, include a sanitized `curl` command or a short code sample.

**Expected behavior**
What did you expect the API to return?

**Actual behavior**
Include the HTTP status code, response content type, and relevant response body or error message. Redact private information.

**Environment**
- API host: (public service or self-hosted; include app version or commit if known)
- Client or language:
- Operating system:

**Additional context**
Include anything else that may help reproduce the issue.

Do not include API keys, passwords, authorization headers, private server credentials, or other secrets.
