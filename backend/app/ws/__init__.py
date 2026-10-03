"""Application WebSocket gateway (Phase 4).

Hosts: authenticated connect handshake (gateway), versioned JSON event
envelope, per-meeting connection registry, Redis presence + pub/sub fan-out,
heartbeat/idle handling (see REALTIME.md).
"""
