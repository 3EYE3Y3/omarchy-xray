# Security policy

## Model

X-Ray is local-first and read-only by default. It does not use `sudo`, `pkexec`, `eval`, shell interpolation, or automatic package installation. Probe commands use fixed executable names and direct argument arrays; inspected strings are passed as individual argv values and treated as untrusted data. Every subprocess has a timeout and bounded captured output.

X-Ray never executes an inspected command line or executable, sources an inspected file, extracts an archive, reads process environment variables, or inspects browser credentials, SSH keys, or unrelated paths. Archive inspection lists entries only. File names, window titles, and process names are rendered as plain text by QML.

The v0.9 acceptance candidate exposes no enabled destructive action. Service restart/stop capability is declared unavailable. Future state-changing actions must have explicit confirmation, narrow argv construction, and tests before activation. X-Ray never invokes automatic firewall changes.

Omarchy plugins run unsandboxed inside `omarchy-shell`; install only from a repository you trust. Missing permissions or optional utilities produce limitations, never privilege escalation.

## Reporting

Please use GitHub private vulnerability reporting when enabled, or open a minimal issue that contains no secrets. Include X-Ray version, Omarchy version, target type, and sanitized reproduction steps.
