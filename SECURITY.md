# Security Policy

Afya Sahihi processes information adjacent to Protected Health Information (PHI) and supports clinical decision-making. A security vulnerability in this system could cause direct patient harm. We take every report seriously.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Email `security@aku.edu` with:

- A description of the vulnerability
- Steps to reproduce (if available)
- Your assessment of the impact
- Whether you have disclosed this to anyone else
- Whether you would like credit in the fix announcement

You will receive an acknowledgement within 48 hours. We operate on a 90-day coordinated disclosure window by default, extendable by mutual agreement if the fix is operationally complex.

For anything time-critical (active exploitation, data exposure), also page the on-call engineer via the contact listed on the AKU IT security page.

## Clinical safety reports

If the issue you have found is a **clinical correctness** problem (wrong dose, wrong indication, unsafe recommendation) rather than a cybersecurity issue, email `clinical-safety@aku.edu` directly. These reports are triaged by a clinician within 24 hours.

## Scope

In scope for our security program:

- The code in this repository
- The deployed application at `afya-sahihi.aku.edu`
- Container images published to our registry
- Infrastructure operated by AKU in support of Afya Sahihi

Out of scope:

- Third-party dependencies (please report upstream; we will expedite the fix in our repo once patched)
- Social engineering of AKU staff
- Physical security of AKU facilities
- Denial of service via volumetric attack
- Anything requiring already-compromised user credentials

## Safe harbor

We will not pursue legal action against researchers who:

- Act in good faith
- Report promptly and do not disclose publicly before we have released a fix
- Do not exfiltrate data beyond what is needed to demonstrate the vulnerability
- Do not degrade service availability for real users
- Respect patient privacy and do not attempt to access clinical data

## Hall of thanks

We acknowledge reporters who help us improve the security of Afya Sahihi. If you would like public credit, say so in your initial report.

## Our disclosure process

1. Triage (within 48 hours): we confirm receipt and assign severity.
2. Investigation: we reproduce and assess impact.
3. Fix development: we build and test a fix, ideally without public reference to the issue in commits.
4. Coordinated release: we ship the fix to production, then publish a security advisory.
5. Credit: we thank the reporter (with consent) in the advisory.

Severity scale:

- **Critical** — patient harm possible, or full PHI exposure. Fix target: 72 hours.
- **High** — partial PHI exposure, privilege escalation, or availability risk. Fix target: 7 days.
- **Medium** — limited data exposure, minor privilege issues. Fix target: 30 days.
- **Low** — best-practice deviations without direct exposure. Fix target: next release.

## Non-security-issue filings

If you find something that is not quite a vulnerability but concerns you (for example, an outdated dependency with a known CVE that does not appear exploitable in our context, or a configuration recommendation we have not followed), please open a regular issue with the `type/security` label.
