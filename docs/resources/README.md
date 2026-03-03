# Docs Assets Policy

This folder stores documentation images only.

Rules:

- Use synthetic data when possible; otherwise redact all real/personal content.
- Do not include secrets, tokens, emails, or local machine identifiers.
- Before commit, strip metadata from all PNG files.

Commands:

```bash
make docs-assets-sanitize
make docs-assets-check
```

Current UI walkthrough images live in `docs/resources/ui/`.
