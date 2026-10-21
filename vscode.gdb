# Sourced by dqix-decomp/.vscode/launch.json.
# VS Code's C/C++ debugger stops a session with `kill`, and melonDS's stub answers vKill by resetting
# emulation and wedging. Detach first, so Stop just lets the game keep running.
define hook-kill
  detach
end
# melonDS keeps no-ack mode after a client leaves, so the next connect never gets acks and fails.
set remote noack-packet off
