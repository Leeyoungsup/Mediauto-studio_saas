# MeDIAuto Studio Docs

This directory contains user, operations, database, security, and compliance
documentation for MeDIAuto Studio SaaS.

Some legacy documents still contain mojibake from an earlier encoding mismatch.
Do not guess-rewrite regulatory or clinical text unless the original source is
available. Prefer adding corrected UTF-8 documents or replacing a document only
when the intended content is clear.

## Recommended Reading Order

1. [PRODUCT_BROCHURE.md](PRODUCT_BROCHURE.md): product positioning and feature overview.
2. [USER_GUIDE.md](USER_GUIDE.md): user workflow and screen-level guidance.
3. [FEATURES.md](FEATURES.md): implemented behavior and API-level feature notes.
4. [DATABASE.md](DATABASE.md): PostgreSQL tables, indexes, and storage boundaries.
5. [SECURITY.md](SECURITY.md): authentication, authorization, audit, and security controls.
6. [COMPLIANCE_STATUS.md](COMPLIANCE_STATUS.md): regulatory control implementation status.
7. [DEPLOYMENT.md](DEPLOYMENT.md): PostgreSQL security, secrets, reverse proxy, Philips bridge, and backup/restore checklist.
8. [color_match_analysis.md](color_match_analysis.md): Hamamatsu/NDP color matching notes.
9. [ACTIVITY_LOGS.md](ACTIVITY_LOGS.md): annotation and upload event coverage, Admin filters, and logging limits.

## Documentation Rules

- Keep new and edited files as UTF-8.
- Prefer ASCII for technical operations docs unless Korean wording is required.
- Do not paste text from applications that may change encoding silently.
- If a legacy file is unreadable, add a clean replacement section or a new doc
  instead of trying to infer clinical or regulatory wording.
- Keep duplicate content short and link to the owning document.
