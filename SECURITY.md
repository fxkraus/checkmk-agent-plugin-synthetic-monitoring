# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Report them privately through
GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
(*Security* tab → *Report a vulnerability*) of this repository.

Include the affected component (executor, agent plugin, MKP, deploy scripts), the version or
commit, and steps to reproduce. You can expect an acknowledgement within a week.

## Supported versions

Only the latest release receives fixes.

## Scope notes

- Journey credentials must come from the environment / podman secrets; never commit them to
  journey files. A report showing that the executor or agent plugin leaks them (spool, artifacts,
  agent output, logs) is in scope.
- Screenshots written on failure can contain whatever the monitored page shows. They are
  created mode `0640` in `/var/lib/synmon/artifacts`, which `deploy/install.sh` creates as mode
  `2750` (owner `synmon`, group-readable only); do not widen it.
- Playwright traces are off by default because they record typed credentials and session
  cookies. `SYNMON_TRACE=1` enables them for debugging only.
