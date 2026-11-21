# Security policy

## Supported versions

Security fixes are prepared for the latest published release.

## Reporting a vulnerability

Please do not open a public issue for an exploitable security problem. Use GitHub's private vulnerability reporting for this repository. Include affected versions, impact, and reproduction details. Do not include API keys, private recordings, or other user data.

Addy Clips has no built-in login. It binds to loopback by default. For remote access, deploy behind HTTPS and an access-controlled reverse proxy. Keep Docker, dependencies, and the host patched.

