# -*- coding: utf-8 -*-
"""Qt5/Qt6 and QGIS 3/QGIS 4 enum compatibility helpers.

Qt6 Python bindings require many enum values to be accessed through their
scoped enum classes, while Qt5-era plugins commonly use legacy flat aliases.
This module resolves the scoped value first and falls back to the legacy alias,
allowing the plugin to run under both generations without version checks.
"""

from qgis.PyQt.QtCore import Qt, QLocale, QMetaType
try:
    from qgis.PyQt.QtCore import QVariant
except ImportError:  # Qt 6 bindings may omit the legacy QVariant wrapper.
    QVariant = None
from qgis.PyQt.QtGui import QPainter, QDoubleValidator
from qgis.PyQt.QtWidgets import (
    QDialogButtonBox,
    QMessageBox,
    QSizePolicy,
    QFrame,
    QLayout,
    QPlainTextEdit,
)
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import Qgis, QgsMapLayerProxyModel, QgsWkbTypes, QgsUnitTypes



from .compat_utils import enum_member, first_enum_member

# QtCore.Qt
QT_ALIGN_CENTER = enum_member(Qt, "AlignmentFlag", "AlignCenter")
QT_TRANSPARENT = enum_member(Qt, "GlobalColor", "transparent")
QT_SOLID_LINE = enum_member(Qt, "PenStyle", "SolidLine")
QT_DASH_LINE = enum_member(Qt, "PenStyle", "DashLine")
QT_NO_PEN = enum_member(Qt, "PenStyle", "NoPen")
QT_ROUND_CAP = enum_member(Qt, "PenCapStyle", "RoundCap")
QT_NON_MODAL = enum_member(Qt, "WindowModality", "NonModal")
QT_WINDOW_MINMAX_HINT = enum_member(Qt, "WindowType", "WindowMinMaxButtonsHint")
QT_SCROLLBAR_AS_NEEDED = enum_member(Qt, "ScrollBarPolicy", "ScrollBarAsNeeded")

# QtGui / QtWidgets
QPAINTER_ANTIALIASING = enum_member(QPainter, "RenderHint", "Antialiasing")
QSIZEPOLICY_EXPANDING = enum_member(QSizePolicy, "Policy", "Expanding")
QSIZEPOLICY_MINIMUM = enum_member(QSizePolicy, "Policy", "Minimum")
QFRAME_NO_FRAME = enum_member(QFrame, "Shape", "NoFrame")
QLAYOUT_SET_MIN_MAX = enum_member(QLayout, "SizeConstraint", "SetMinAndMaxSize")
QPLAINTEXT_NO_WRAP = enum_member(QPlainTextEdit, "LineWrapMode", "NoWrap")
QVALIDATOR_STANDARD_NOTATION = enum_member(QDoubleValidator, "Notation", "StandardNotation")
QDIALOG_OK = enum_member(QDialogButtonBox, "StandardButton", "Ok")
QDIALOG_CANCEL = enum_member(QDialogButtonBox, "StandardButton", "Cancel")
QDIALOG_HELP = enum_member(QDialogButtonBox, "StandardButton", "Help")
QMESSAGE_YES = enum_member(QMessageBox, "StandardButton", "Yes")
QMESSAGE_NO = enum_member(QMessageBox, "StandardButton", "No")
QLOCALE_C = enum_member(QLocale, "Language", "C")

# Printing
QPRINTER_HIGH_RESOLUTION = enum_member(QPrinter, "PrinterMode", "HighResolution")
QPRINTER_PDF_FORMAT = enum_member(QPrinter, "OutputFormat", "PdfFormat")


# QGIS message levels are scoped in QGIS 4. Legacy aliases are retained as
# fallbacks for older QGIS 3 releases.
QGIS_MESSAGE_INFO = first_enum_member(
    (Qgis, "MessageLevel", "Info"),
    (Qgis, None, "Info"),
)
QGIS_MESSAGE_SUCCESS = first_enum_member(
    (Qgis, "MessageLevel", "Success"),
    (Qgis, None, "Success"),
)
QGIS_MESSAGE_WARNING = first_enum_member(
    (Qgis, "MessageLevel", "Warning"),
    (Qgis, None, "Warning"),
)
QGIS_MESSAGE_CRITICAL = first_enum_member(
    (Qgis, "MessageLevel", "Critical"),
    (Qgis, None, "Critical"),
)

# QGIS enums moved to scoped Qgis enums in QGIS 4.
QGIS_POINT_LAYER_FILTER = first_enum_member(
    (Qgis, "LayerFilter", "PointLayer"),
    (QgsMapLayerProxyModel, "Filter", "PointLayer"),
    (QgsMapLayerProxyModel, None, "PointLayer"),
)
QGIS_GEOMETRY_POINT = first_enum_member(
    (Qgis, "GeometryType", "Point"),
    (QgsWkbTypes, "GeometryType", "PointGeometry"),
    (QgsWkbTypes, None, "PointGeometry"),
)
QGIS_GEOMETRY_POLYGON = first_enum_member(
    (Qgis, "GeometryType", "Polygon"),
    (QgsWkbTypes, "GeometryType", "PolygonGeometry"),
    (QgsWkbTypes, None, "PolygonGeometry"),
)
QGIS_DISTANCE_METERS = first_enum_member(
    (Qgis, "DistanceUnit", "Meters"),
    (QgsUnitTypes, None, "DistanceMeters"),
)

# QgsField uses QMetaType::Type in current QGIS versions. Keep QVariant fallbacks
# for older supported QGIS 3 installations.
FIELD_TYPE_STRING = first_enum_member(
    (QMetaType, "Type", "QString"),
    *((QVariant, "Type", "String"), (QVariant, None, "String")) if QVariant is not None else (),
)
FIELD_TYPE_DOUBLE = first_enum_member(
    (QMetaType, "Type", "Double"),
    *((QVariant, "Type", "Double"), (QVariant, None, "Double")) if QVariant is not None else (),
)
