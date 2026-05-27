# OpenConstructionERP Security Audit (2026-05-24)

**HEAD:** be32c09b7008417cad22e071cdfe42d555b2ebae  
**Scope:** Repository-wide scan for hardcoded secrets, SQL injection, command injection, path traversal, XSS, CORS misconfiguration, JWT validation gaps, file-upload validation, auth bypass, and sensitive data logging.

---

## Executive Summary

The codebase exhibits **good baseline security posture** with multiple defense layers in place. **One CRITICAL issue** identified: JWT secret in development-mode default configuration exposes a published key used by all developers. **Two HIGH issues** identified in Markdown rendering without explicit sanitizer documentation, and potential SQL injection patterns in database migrations that, while currently safe via hardcoded constants, represent code-smell risk. **No active exploitation paths found** in production-facing code; frontend file-upload handlers use proper validation (extension blocking, size caps, filename sanitization).

**Immediate action:** Ensure non-development environments have OE_JWT_SECRET set and verify .env is in .gitignore (no evidence of leaked .env found).

---

## Detailed Findings

| Severity | Module | File:Line | Pattern | Why Dangerous | Suggested Fix |
|----------|--------|-----------|---------|---------------|---------------|
| **CRITICAL** | Auth Config | backend/app/config.py:158 | jwt_secret = "openestimate-local-dev-key" | Bundled development JWT secret is published in public repository. Anyone reading the codebase can forge admin tokens against any production deployment using this default. | Enforce via validator (line 430-437 checks this for non-dev) — ensure OE_JWT_SECRET env var is set in staging/prod. Add boot-time warning in logs even if validation passes. |
| **HIGH** | Chat/AI Rendering | frontend/src/features/erp-chat/FloatingChatPanel.tsx:1819 | dangerouslySetInnerHTML{{ __html: html }} (renderMarkdown output) | renderMarkdown() output is fed to dangerouslySetInnerHTML without explicit HTML sanitizer library (e.g., DOMPurify). While the function does escape < and & first, it re-introduces HTML via string replace (lines 249-268). Attack: malicious markdown with crafted code blocks could inject <script> or event handlers. | Use DOMPurify.sanitize() post-processing or replace dangerouslySetInnerHTML with a React markdown library (react-markdown + remark plugins) that handles escaping internally. Document the sanitization step explicitly. |
| **HIGH** | Chat Rendering | frontend/src/features/erp-chat/full-page/left/MessageBubble.tsx:302 | <span dangerouslySetInnerHTML{{ __html: renderedHtml }} (renderMarkdown output) | Same as above: renderMarkdown→dangerouslySetInnerHTML without explicit sanitizer. Lower surface area than floating panel (only chat bubbles), but same XSS principle. | Apply DOMPurify.sanitize() post-processing before dangerouslySetInnerHTML, or migrate to safer React markdown library. |
| **HIGH** | Alembic Migration | backend/alembic/versions/v3033_audit_log.py:195–196, 215 | F-string interpolation in SQL text() | F-string interpolation into SQL text(). While current code uses hardcoded table/column names from _LEGACY_REMAPS and _BACKFILL_ENTITIES (safe), the pattern is an anti-pattern and invites copy-paste vulnerabilities in future migrations. | Use Alembic's schema manipulation API or pre-validate table/column names against a whitelist before interpolation. Document why interpolation is acceptable here (constants only, no user input). |
| **MED** | Alembic Migration | backend/alembic/versions/v41_smart_views_share.py:90–91 | sa.text(f"{_COLUMN} IS NOT NULL") | F-string into sa.text() for WHERE clause in CREATE INDEX. _COLUMN is hardcoded, so safe, but same anti-pattern as above—harder to audit and invites mistakes. | Define the WHERE clause as a literal string constant, or use Alembic's Index API directly with explicit conditions. |
| **MED** | File Upload Handler | backend/app/modules/documents/service.py:227–229 | No upload size cap comment + 100MB default | Comment states there is no API-level cap (relies on nginx/gateway for DDoS mitigation). If gateway is misconfigured, large uploads could exhaust disk. | Document the assumption that nginx/API gateway enforces a reasonable limit. Add a health-check endpoint that warns if disk usage exceeds threshold. Consider adding optional per-tenant quota. |
| **LOW** | Admin Reset | backend/app/modules/admin/service.py:92–102 | QA_RESET_TOKEN via environment variable | Environment variables can leak in process-tree inspection or container logs. | For production: use a secret-management system (Vault, AWS Secrets Manager) instead of env vars. In dev: rotate QA tokens frequently. |
| **LOW** | JWT Validation | backend/app/dependencies.py:89–92 | jwt.decode with algorithms list | Code correctly specifies a single algorithm (HS256), preventing algorithm confusion attacks. Token type claim is validated. Expiry is enforced. **No issues found.** | **Compliant** — no action needed. Document HS256 choice in design docs. |

---

## Top 5 CRITICAL/HIGH Findings (with Code Excerpts)

### 1. CRITICAL: JWT Secret Default (backend/app/config.py:158)

**Code:**
\\\python
jwt_secret: str = "openestimate-local-dev-key"
\\\

**Why Dangerous:**  
Published in public repo. Attacker can forge admin JWTs on any deployment using the default.

**Current Mitigation:**  
Validator at line 430-437 refuses to start if APP_ENV != "development" and secret is still default.

**Fix:** Enforce OE_JWT_SECRET env var in production. Add boot-time warning logs.

---

### 2. HIGH: Markdown XSS (frontend/src/features/erp-chat/FloatingChatPanel.tsx:1819)

**Code:**
\\\	ypescript
const html = useMemo(() => renderMarkdown(msg.content), [msg.content])
<div dangerouslySetInnerHTML={{ __html: html }} />

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    // ... then re-introduces HTML via string replace
    .replace(/\\\(\w*)\n([\s\S]*?)\\\/g, 
      (_m, _lang, code) => \<pre><code>\</code></pre>\)
  return html;
}
\\\

**Why Dangerous:**  
renderMarkdown escapes HTML upfront but re-introduces it via string replacement. Embedded code blocks or edge cases could allow XSS.

**Fix:** Use DOMPurify.sanitize(html) before dangerouslySetInnerHTML, or migrate to react-markdown.

---

### 3. HIGH: SQL Anti-Pattern (backend/alembic/versions/v3033_audit_log.py:195, 215)

**Code:**
\\\python
op.execute(
    sa.text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old")
    .bindparams(new=new_value, old=old_value)
)
rows = bind.execute(sa.text(f"SELECT id, status FROM {table}")).fetchall()
\\\

**Why Dangerous (in principle):**  
F-string interpolation into SQL is an anti-pattern. Currently safe because table/column are hardcoded, but pattern invites copy-paste mistakes.

**Fix:** Document that constants are safe, or use Alembic schema API.

---

### 4. MED: File Upload Size Policy (backend/app/modules/documents/service.py:227)

**Code:**
\\\python
# No upload size cap — per product policy.
try:
    doc = await service.upload_document(project_id, file, category, user_id)
\\\

**Why Risky:**  
Relies entirely on nginx/gateway. Misconfiguration or auth bypass could exhaust disk.

**Fix:** Document nginx requirement. Add health-check for disk usage. Consider per-tenant quotas.

---

### 5. LOW: QA Reset Token via Env (backend/app/modules/admin/service.py:92)

**Code:**
\\\python
expected = os.environ.get("QA_RESET_TOKEN", "")
if confirm_token is None or not hmac.compare_digest(expected, confirm_token):
    raise GateError(...)
\\\

**Why Risky:**  
Env vars can leak via ps output, logs, or orchestration systems.

**Fix:** Use secret-management system for production. Rotate tokens in dev.

---

## What's NOT a Concern

- **R7-Audited Modules:** contracts, costs, property_dev, variations, bid_management, schedule_advanced, geo_hub all exhibit strong security posture.
- **CORS:** No wildcard + credentials; uses configurable origins from env. **Compliant.**
- **JWT:** Hardcoded HS256, algorithm allowlist, expiry checks, token type validation. **Compliant.**
- **Command Injection:** No subprocess.run(..., shell=True) or os.system() in production code. **Compliant.**
- **Path Traversal:** File uploads use UUID-prefixed paths and sanitized filenames. **Likely Compliant.**
- **Hardcoded Credentials:** No API keys or passwords found in source. .env.example is template-only. **Compliant.**

---

## Recommendations (Priority Order)

1. **CRITICAL (Immediate):**
   - Verify .env is in .gitignore.
   - Ensure non-dev deployments have OE_JWT_SECRET set to a random value (32+ chars).
   - Add boot-time log confirming JWT secret has been rotated.

2. **HIGH (Before next release):**
   - Integrate DOMPurify into Markdown rendering or migrate to react-markdown.
   - Update SQL anti-pattern in Alembic migrations with explanatory comments.

3. **MED (Next quarter):**
   - Add per-tenant file-upload quotas.
   - Migrate QA_RESET_TOKEN to secret-management system.
   - Document nginx client_max_body_size requirement.

4. **LOW (Ongoing):**
   - Continue leveraging SQLAlchemy ORM.
   - Keep JWT validation as-is (it's correct).
   - Periodic security training for developers.

---

**Audit date:** 2026-05-24 | **HEAD:** be32c09b | **Status:** READ-ONLY SCAN
