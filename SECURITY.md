# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue.** Please report security vulnerabilities via:

1. GitHub private security advisory: https://github.com/spire-studio/cloakbot/security/advisories
2. Email: me@laurie.pro

Include a description, steps to reproduce, and potential impact.

---

## Security Configuration

### API Keys

Store all API keys (remote LLM providers, channel tokens) in `~/.cloakbot/config.json` with restricted permissions. Never commit keys to version control.

```bash
chmod 700 ~/.cloakbot/
chmod 600 ~/.cloakbot/config.json
```

### Session Vault

The Vault holds plaintext `token ↔ raw value` mappings for the current session. Protect it accordingly:

```bash
chmod 700 ~/.cloakbot/workspace/privacy_vault/
```

Do not log vault contents, sync vault files to cloud storage, or leave stale vaults from old sessions on disk.

### Local Model Service (vLLM / Ollama)

The local inference service should bind to 127.0.0.1 only, or to a trusted internal network interface if accessed by other services within a secured private network. Exposing it on a public interface allows any process on the network to submit arbitrary prompts to your local models.

### Channel Access Control

Always set `allowFrom` for every enabled channel in production. An empty `allowFrom` denies all users by default; use `["*"]` to explicitly allow everyone.

```json
{
  "channels": {
    "telegram": { "allowFrom": ["123456789"] },
    "whatsapp": { "allowFrom": ["+1234567890"] }
  }
}
```

### Exec Sandbox (Linux)

Enable bwrap to isolate local code execution at the kernel level. This hides `~/.cloakbot/config.json` and API keys from any spawned process:

```json
{ "tools.exec.sandbox": "bwrap" }
```

Requires `bwrap` (`apt install bubblewrap`). Not available on macOS or Windows.

---

## Operational Security

- **Run as a non-root dedicated user.** Never run Cloakbot as root.
- **Set spending limits** on all remote LLM provider accounts to cap blast radius if a key is compromised.
- **Secure log files.** Logs may contain sanitized prompts. Set `chmod 600` on log files and rotate them regularly.

---

## Incident Response

If you suspect a key or session has been compromised:

1. Revoke all remote/local LLM API keys and channel bot tokens immediately.
2. Delete session Vault files under `~/.cloakbot/workspace/privacy_vault/`.
3. Review logs for unauthorized access attempts.
4. Update to the latest release.
5. Report to maintainers via the channels above.

---

**Last updated**: 2026-04-21 · Advisories: https://github.com/spire-studio/cloakbot/security/advisories
