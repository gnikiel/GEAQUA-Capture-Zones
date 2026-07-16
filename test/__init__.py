# Import QGIS when tests run inside QGIS, but keep pure algorithm tests
# runnable in a standard Python environment.
try:
    import qgis  # pylint: disable=W0611  # noqa: F401
except ImportError:
    qgis = None
