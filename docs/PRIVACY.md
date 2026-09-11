# Privacy

X-Ray runs locally. It has no account, analytics, telemetry, tracking pixel, cloud backend, or upload path. Inspection results remain on the computer and are held only in process memory unless the user explicitly redirects CLI output.

Local targets use local sources such as `/proc`, `/sys`, Hyprland IPC, systemd, and pacman. External network activity occurs only for an explicitly requested domain or IP inspection. Domain inspection can perform DNS resolution, an HTTPS/TLS connection, a route lookup, and an optional bounded trace. IP inspection can perform one ICMP echo, reverse DNS, a route lookup, and a local neighbour lookup. No aggressive scanning occurs.

X-Ray does not inspect browser credentials, SSH keys, process environments, or unrelated files.
