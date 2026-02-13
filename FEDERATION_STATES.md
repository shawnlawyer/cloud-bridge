# Federation States

## States

- `discovered`
- `handshaking`
- `trusted`
- `quarantined`
- `disconnected`

## Allowed Transitions

- `discovered -> handshaking`
- `handshaking -> trusted`
- `handshaking -> quarantined`
- `trusted -> quarantined`
- `trusted -> disconnected`
- `quarantined -> disconnected`
- `disconnected -> discovered`

## Forbidden Transitions

- `discovered -> trusted`
- `discovered -> quarantined`
- `handshaking -> discovered`
- `quarantined -> trusted`
- `disconnected -> trusted`

## Auto-Fail Behavior

- Handshake validation failure transitions to `quarantined`.
- Duplicate bridge identity transitions to `quarantined`.
- Protocol mismatch transitions to `quarantined`.
- Any forbidden transition request is rejected and remains in current state.
