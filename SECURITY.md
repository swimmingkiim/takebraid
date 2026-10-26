# Security

Before reporting a vulnerability, use GitHub's private vulnerability reporting feature if enabled
for this repository. If it is unavailable, open an issue asking for a private contact without
including exploit details, credentials or private footage.

Takebraid is pre-alpha and has no supported production release. Treat media files, metadata,
filenames and model responses as untrusted input. Implementations must use structured subprocess
arguments, validate model-proposed IDs and ranges, and never execute generated shell commands.
Future remote inference is opt-in; reports and exported projects must not expose credentials.
