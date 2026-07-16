# -*- coding: utf-8 -*-
"""Pure-Python helpers used by the Qt/QGIS compatibility layer."""


def enum_member(owner, enum_name, member):
    """Return a scoped enum member with an unscoped legacy fallback.

    Parameters are deliberately generic, so this helper can be tested without
    importing QGIS or Qt.
    """
    enum_type = getattr(owner, enum_name, None) if enum_name else None
    if enum_type is not None and hasattr(enum_type, member):
        return getattr(enum_type, member)
    if hasattr(owner, member):
        return getattr(owner, member)
    owner_name = getattr(owner, "__name__", repr(owner))
    scoped = f"{enum_name}.{member}" if enum_name else member
    raise AttributeError(f"{owner_name} has no enum member {scoped}")


def first_enum_member(*candidates):
    """Return the first available member from ``(owner, enum, member)`` tuples."""
    last_error = None
    for owner, enum_name, member in candidates:
        try:
            return enum_member(owner, enum_name, member)
        except AttributeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise AttributeError("No enum candidates supplied")
