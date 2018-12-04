#!/usr/bin/env python3


class JobNotFoundError(LookupError):
    """Raised when a render job is not found."""

    pass


class NodeNotFoundError(LookupError):
    """Raised when a render node is not found."""

    pass
