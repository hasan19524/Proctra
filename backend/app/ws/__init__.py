"""Application WebSocket gateway (Phase 6).

Will host: authenticated connect handshake, versioned JSON event envelope,
per-meeting room registry, Redis pub/sub fan-out, reconnect sync (see REALTIME.md).
"""
