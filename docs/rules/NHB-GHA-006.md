# NHB-GHA-006: AI coding agent workflow combines untrusted trigger with NHI privileges

A job invoking an AI coding agent action or compiled `*.lock.yml` agentic workflow runs on an untrusted trigger (`issues`, `issue_comment`, `pull_request`, `pull_request_review`, `discussion`, `discussion_comment`) while holding secrets or `id-token: write`.

## Remediation

Remove secrets and `id-token: write` from agentic jobs on untrusted triggers. When the finding hits a compiled `*.lock.yml`, update the sibling `.md` source.
