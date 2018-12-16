#!/usr/bin/env python3


class JobNotFoundError(LookupError):
    """Raised when a render job is not found."""

    pass


class NodeNotFoundError(LookupError):
    """Raised when a render node is not found."""

    pass

class JobStatusError(RuntimeError):
    """Raised when a job is not in the correct state for the requested action."""
    pass
