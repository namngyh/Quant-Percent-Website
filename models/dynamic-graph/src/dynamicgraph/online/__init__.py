"""Online (per-session) update layer.

The batch tier (`run-all`) rebuilds every graph snapshot in the history - 3526
of them on the current data - selects the graphical-lasso penalty, and trains
the stress model. The online tier here advances the published state by exactly
one trading session without refitting anything: it builds the *one* new
snapshot with the same `build_snapshot` and the same frozen alpha the batch tier
used, updates the quantities that depend on history, and republishes
`artifacts/latest/`.

Measured on this data, the cost of a session is dominated by the bootstrap edge
stability of the core layer (~1-4 s); the covariance estimate itself is 0.4 ms,
which is why the online tier reuses the batch estimator verbatim instead of
substituting a recursive one and inviting a train/serve mismatch.
"""

from __future__ import annotations

__all__ = ["session", "state"]
