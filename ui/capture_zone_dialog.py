"""Interactive dialog for GEAQUA Capture Zones.

The dialog validates hydrogeological input, calculates one or several
Ceric–Haitjema (2005) time-of-travel capture-zone variants, previews the
geometries on the QGIS map canvas, and supports project/report export.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QMessageBox, QDialogButtonBox, QLabel, QComboBox,
    QHBoxLayout, QVBoxLayout, QGridLayout, QSpacerItem, QSizePolicy, QPushButton,
    QLineEdit, QCheckBox, QGroupBox, QPlainTextEdit, QFileDialog, QApplication,
    QWidget, QScrollArea, QFrame, QLayout,
)
from qgis.PyQt.QtGui import QDoubleValidator, QPainter, QPen, QBrush, QPolygonF, QPixmap, QColor
from qgis.PyQt.QtCore import QLocale, pyqtSignal, Qt, QPointF
from qgis.PyQt import uic
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsMapLayerProxyModel,
    QgsUnitTypes,
)
from qgis.gui import QgsMapLayerComboBox
import os
import sys
from typing import Tuple, Optional, Dict, List, Any

from ..plugin_utils import (
    is_preferred_polish_crs, assess_zone_scale, STANDARD_TIME_VARIANTS,
    build_calculation_name, zone_dimensions, polygon_area,
)
from ..version import PLUGIN_VERSION, WINDOW_TITLE
from ..translations import DEFAULT_LANGUAGE, translate, zone_display_name
from ..calculation_io import build_document, save_document, load_document, build_summary_text, result_variants
from ..qt_compat import (
    QT_ALIGN_CENTER, QT_TRANSPARENT, QT_SOLID_LINE, QT_NO_PEN, QT_ROUND_CAP,
    QT_NON_MODAL, QT_WINDOW_MINMAX_HINT, QT_SCROLLBAR_AS_NEEDED,
    QPAINTER_ANTIALIASING, QSIZEPOLICY_EXPANDING, QSIZEPOLICY_MINIMUM,
    QFRAME_NO_FRAME, QLAYOUT_SET_MIN_MAX, QPLAINTEXT_NO_WRAP,
    QVALIDATOR_STANDARD_NOTATION, QDIALOG_OK, QDIALOG_CANCEL, QDIALOG_HELP,
    QMESSAGE_YES, QMESSAGE_NO, QLOCALE_C, QGIS_POINT_LAYER_FILTER,
    QGIS_GEOMETRY_POINT, QGIS_DISTANCE_METERS,
)

try:
    from ..qgis_logger import get_logger
    logger = get_logger(__name__)
except (ImportError, ValueError):
    # Fallback for direct development execution in a QGIS Python environment.
    import logging
    logger = logging.getLogger(__name__)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )




class FlowDirectionPreview(QLabel):
    """Small compass-style arrow preview for the entered flow azimuth."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self.setFixedSize(64, 48)
        self.setAlignment(QT_ALIGN_CENTER)
        self.setToolTip("0° = N, 90° = E, 180° = S, 270° = W")
        self.update_arrow(0.0)

    def update_arrow(self, angle):
        try:
            self._angle = float(angle) % 360.0
        except (TypeError, ValueError):
            self._angle = 0.0
        pixmap = QPixmap(self.size())
        pixmap.fill(QT_TRANSPARENT)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPAINTER_ANTIALIASING, True)
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawEllipse(12, 4, 40, 40)
        painter.drawText(27, 13, "N")
        import math
        cx, cy = 32.0, 26.0
        radius = 15.0
        rad = math.radians(self._angle)
        dx, dy = math.sin(rad), -math.cos(rad)
        tip = QPointF(cx + dx * radius, cy + dy * radius)
        tail = QPointF(cx - dx * 8.0, cy - dy * 8.0)
        painter.setPen(QPen(QColor(0, 100, 190), 3, QT_SOLID_LINE, QT_ROUND_CAP))
        painter.drawLine(tail, tip)
        px, py = -dy, dx
        base = QPointF(tip.x() - dx * 7.0, tip.y() - dy * 7.0)
        head = QPolygonF([
            tip,
            QPointF(base.x() + px * 4.0, base.y() + py * 4.0),
            QPointF(base.x() - px * 4.0, base.y() - py * 4.0),
        ])
        painter.setPen(QT_NO_PEN)
        painter.setBrush(QBrush(QColor(0, 100, 190)))
        painter.drawPolygon(head)
        painter.end()
        self.setPixmap(pixmap)

class FlexibleDoubleValidator(QDoubleValidator):
    """
    Custom QDoubleValidator that accepts both dot (.) and comma (,) as decimal separators.

    This validator is designed to accommodate users from different locales:
    - English/US format: uses dot as decimal separator (e.g., 3.14)
    - European format (Polish, German, etc.): uses comma as decimal separator (e.g., 3,14)

    The validator accepts both formats for maximum user convenience.
    """

    def __init__(self, bottom, top, decimals, parent=None):
        """
        Initialize the flexible double validator.

        Args:
            bottom: Minimum allowed value
            top: Maximum allowed value
            decimals: Maximum number of decimal places
            parent: Parent widget
        """
        super().__init__(bottom, top, decimals, parent)
        # Set to C locale to ensure consistent behavior
        self.setLocale(QLocale(QLOCALE_C))

    def validate(self, input_str, pos):
        """
        Validate input string, accepting both dot and comma as decimal separators.

        Args:
            input_str: Input string to validate
            pos: Cursor position

        Returns:
            Tuple of (validation_state, validated_string, position)
        """
        # Replace comma with dot for validation
        normalized = input_str.replace(',', '.')

        # Call parent validator with normalized string
        state, validated, new_pos = super().validate(normalized, pos)

        # Return original string (with comma if present) to preserve user input
        return state, input_str, new_pos


class CaptureZoneDialog(QDialog):
    # The main plugin listens to these signals and manages temporary map layers.
    previewRequested = pyqtSignal(object, object, object)
    clearPreviewRequested = pyqtSignal()
    reportRequested = pyqtSignal(str, object, object, object, str)

    """
    Dialog for analytical capture-zone calculation with comprehensive validation.

    This dialog provides an interactive interface for calculating groundwater
    capture zones using the Ceric–Haitjema (2005) method. It includes:
    - Real-time input validation with visual feedback
    - Layer validation (must be single-point layer)
    - Parameter range checking with appropriate validators
    - Color-coded status messages
    - Calculation triggering and result display
    - Error handling and user guidance
    """

    def __init__(self, parent=None):
        """
        Initialize the capture-zone dialog.

        Args:
            parent: Parent widget (default: None)
        """
        super().__init__(parent)

        # Load UI file
        ui_path = os.path.join(os.path.dirname(__file__), 'capture_zone_dialog.ui')
        uic.loadUi(ui_path, self)

        # Polish is the default interface language. The selector allows the
        # user to switch languages immediately without reopening the dialog.
        self.current_language = DEFAULT_LANGUAGE

        # Initialize instance variables
        self.calculation_result = None
        self.is_calculated = False
        self.cached_layer = None
        self.cached_parameters = None
        self.calculation_signature = None
        self._auto_calculation_name = True
        self._loading_json = False
        self.last_scale_warnings = []

        # Setup logging - use module-level logger
        self.logger = logger

        # Initialize UI components
        self.setup_ui()
        self.setup_validators()
        self.connect_signals()

        self.logger.info("CaptureZoneDialog initialized")

    def setup_ui(self):
        """
        Initialize UI state and configure components.

        Sets up:
        - Map layer combo box to filter point layers only
        - Disables OK button initially
        - Sets placeholder text for all input fields
        - Clears result fields
        - Sets initial status message
        """
        # Keep the current plugin version visible in the dialog title.
        self.setWindowTitle(WINDOW_TITLE)

        # Add a language selector as the first row of the dialog.
        self.setup_language_selector()
        self.setup_calculation_name_controls()
        self.setup_direction_preview()
        self.setup_time_variant_controls()
        self.setup_enhanced_results_panel()
        self.setup_preview_controls()
        self.setup_scrollable_dialog()

        # Configure map layer combo box to show only point layers
        self.mMapLayerComboBox.setFilters(QGIS_POINT_LAYER_FILTER)

        # Disable OK button initially - only enable after successful calculation
        self.buttonBox.button(QDIALOG_OK).setEnabled(False)

        # Set placeholder text with example values
        self.lineEdit_k.setPlaceholderText("8.64")
        self.lineEdit_m.setPlaceholderText("41.0")
        self.lineEdit_n.setPlaceholderText("0.2")
        self.lineEdit_Q.setPlaceholderText("2640")
        self.lineEdit_I.setPlaceholderText("0.002809")
        self.lineEdit_flow_direction.setPlaceholderText("111.67")
        self.lineEdit_time.setPlaceholderText("25")
        self.update_flow_direction_preview()
        self.update_gradient_dependent_controls()
        self.update_calculation_name_suggestion(force=True)

        # Clear result fields
        self.clear_results()

        # Apply Polish interface text by default and set the initial status.
        self.apply_language(refresh_status=False)
        self.set_status(self._t("ready_initial"), "info")

        self.logger.debug("UI setup completed")

    def _t(self, key: str, **kwargs) -> str:
        """Translate a user-visible interface string."""
        return translate(key, self.current_language, **kwargs)

    def setup_scrollable_dialog(self):
        """Make the long parameter form resizable and vertically scrollable.

        The status line and command buttons remain fixed at the bottom, while
        all parameter and result groups are moved to a QScrollArea. This keeps
        the dialog usable on small screens without forcing a large minimum
        height.
        """
        self.setMinimumSize(480, 420)
        self.setMaximumSize(16777215, 16777215)
        self.setSizeGripEnabled(True)
        self.setWindowModality(QT_NON_MODAL)
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | QT_WINDOW_MINMAX_HINT)

        self.scrollContent = QWidget(self)
        self.scrollContent.setObjectName("scrollContent")
        self.scrollContentLayout = QVBoxLayout(self.scrollContent)
        self.scrollContentLayout.setObjectName("verticalLayout_scroll_content")
        self.scrollContentLayout.setContentsMargins(4, 4, 4, 4)
        self.scrollContentLayout.setSpacing(10)
        self.scrollContentLayout.setSizeConstraint(QLAYOUT_SET_MIN_MAX)

        fixed_items = []
        while self.verticalLayout_main.count():
            item = self.verticalLayout_main.takeAt(0)
            widget = item.widget()
            layout = item.layout()

            if widget is self.labelStatus or layout is self.horizontalLayout_buttons:
                fixed_items.append((widget, layout, item))
                continue

            if widget is not None:
                widget.setParent(self.scrollContent)
                self.scrollContentLayout.addWidget(widget)
            elif layout is not None:
                self.scrollContentLayout.addLayout(layout)
            else:
                self.scrollContentLayout.addItem(item)

        self.scrollArea = QScrollArea(self)
        self.scrollArea.setObjectName("scrollAreaParameters")
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QFRAME_NO_FRAME)
        self.scrollArea.setHorizontalScrollBarPolicy(QT_SCROLLBAR_AS_NEEDED)
        self.scrollArea.setVerticalScrollBarPolicy(QT_SCROLLBAR_AS_NEEDED)
        self.scrollArea.setWidget(self.scrollContent)
        self.verticalLayout_main.addWidget(self.scrollArea, 1)

        for widget, layout, item in fixed_items:
            if widget is not None:
                self.verticalLayout_main.addWidget(widget)
            elif layout is not None:
                self.verticalLayout_main.addLayout(layout)
            else:
                self.verticalLayout_main.addItem(item)

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            target_width = min(680, max(500, int(available.width() * 0.55)))
            target_height = min(820, max(500, int(available.height() * 0.82)))
            self.resize(target_width, target_height)
        else:
            self.resize(620, 760)

    def setup_language_selector(self):
        """Add the Polish/English language selector at the top of the dialog."""
        self.languageLayout = QHBoxLayout()
        self.languageLayout.setObjectName("horizontalLayout_language")

        self.labelLanguage = QLabel(self)
        self.labelLanguage.setObjectName("labelLanguage")
        self.comboLanguage = QComboBox(self)
        self.comboLanguage.setObjectName("comboLanguage")
        self.comboLanguage.addItem("Polski", "pl")
        self.comboLanguage.addItem("English", "en")
        self.comboLanguage.setCurrentIndex(0)
        self.comboLanguage.setMinimumWidth(125)

        self.languageLayout.addWidget(self.labelLanguage)
        self.languageLayout.addItem(
            QSpacerItem(20, 20, QSIZEPOLICY_EXPANDING, QSIZEPOLICY_MINIMUM)
        )
        self.languageLayout.addWidget(self.comboLanguage)
        self.verticalLayout_main.insertLayout(0, self.languageLayout)

    def setup_calculation_name_controls(self):
        """Add the editable calculation/layer name directly below language selection."""
        self.calculationNameLayout = QHBoxLayout()
        self.labelCalculationName = QLabel(self)
        self.lineEditCalculationName = QLineEdit(self)
        self.lineEditCalculationName.setMinimumWidth(300)
        self.calculationNameLayout.addWidget(self.labelCalculationName)
        self.calculationNameLayout.addWidget(self.lineEditCalculationName, 1)
        self.verticalLayout_main.insertLayout(1, self.calculationNameLayout)

    def setup_direction_preview(self):
        """Show a live compass arrow next to the flow-direction field."""
        self.flowDirectionPreview = FlowDirectionPreview(self)
        self.gridLayout_well_flow.addWidget(self.flowDirectionPreview, 2, 3, 1, 1)

    def setup_time_variant_controls(self):
        """Add the optional standard 1/5/10/25/50-year calculation mode."""
        self.checkBoxStandardTimes = QCheckBox(self)
        self.gridLayout_time.addWidget(self.checkBoxStandardTimes, 1, 0, 1, 3)

    def setup_enhanced_results_panel(self):
        """Replace the legacy six-field result grid with a detailed text panel."""
        for index in range(self.gridLayout_results.count()):
            item = self.gridLayout_results.itemAt(index)
            widget = item.widget() if item else None
            if widget:
                widget.hide()

        self.resultSummary = QPlainTextEdit(self.groupBox_results)
        self.resultSummary.setObjectName("resultSummary")
        self.resultSummary.setReadOnly(True)
        self.resultSummary.setMinimumHeight(205)
        self.resultSummary.setLineWrapMode(QPLAINTEXT_NO_WRAP)
        self.gridLayout_results.addWidget(self.resultSummary, 0, 0, 1, 3)

        self.resultButtonsLayout = QGridLayout()
        self.buttonCopyResults = QPushButton(self.groupBox_results)
        self.buttonSaveJson = QPushButton(self.groupBox_results)
        self.buttonLoadJson = QPushButton(self.groupBox_results)
        self.buttonReportHtml = QPushButton(self.groupBox_results)
        self.buttonReportPdf = QPushButton(self.groupBox_results)
        for button in (self.buttonCopyResults, self.buttonSaveJson, self.buttonReportHtml, self.buttonReportPdf):
            button.setEnabled(False)
        self.resultButtonsLayout.addWidget(self.buttonCopyResults, 0, 0)
        self.resultButtonsLayout.addWidget(self.buttonSaveJson, 0, 1)
        self.resultButtonsLayout.addWidget(self.buttonLoadJson, 0, 2)
        self.resultButtonsLayout.addWidget(self.buttonReportHtml, 1, 0, 1, 2)
        self.resultButtonsLayout.addWidget(self.buttonReportPdf, 1, 2)
        self.gridLayout_results.addLayout(self.resultButtonsLayout, 1, 0, 1, 3)

    def set_result_actions_enabled(self, enabled: bool):
        for button in (self.buttonCopyResults, self.buttonSaveJson, self.buttonReportHtml, self.buttonReportPdf):
            button.setEnabled(bool(enabled))

    def update_flow_direction_preview(self, *_):
        text = self.lineEdit_flow_direction.text().strip().replace(',', '.')
        try:
            angle = float(text) if text else 0.0
        except ValueError:
            angle = 0.0
        self.flowDirectionPreview.update_arrow(angle)

    def on_calculation_name_edited(self, *_):
        self._auto_calculation_name = False
        if self.is_calculated and self.calculation_result:
            self.display_results(self.calculation_result)

    def update_calculation_name_suggestion(self, force: bool = False):
        if not force and not self._auto_calculation_name:
            return
        layer = self.mMapLayerComboBox.currentLayer()
        source = layer.name() if layer else "S1"
        time_text = self.lineEdit_time.text().strip().replace(',', '.')
        try:
            time_years = float(time_text) if time_text else 25.0
        except ValueError:
            time_years = 25.0
        name = build_calculation_name(source, time_years, self.checkBoxStandardTimes.isChecked())
        self.lineEditCalculationName.setText(name)
        self._auto_calculation_name = True

    def on_standard_times_changed(self, checked: bool):
        self.lineEdit_time.setEnabled(not checked)
        self.update_calculation_name_suggestion()
        self.on_input_changed()

    def copy_results_to_clipboard(self):
        if not self.resultSummary.toPlainText().strip():
            return
        QApplication.clipboard().setText(self.resultSummary.toPlainText())
        self.set_status(self._t("results_copied"), "success")

    def save_calculation_json(self):
        if not self.is_calculated or not self.calculation_result:
            self.show_warning_dialog(self._t("no_calculation_title"), self._t("no_calculation_message"))
            return
        default_name = self.lineEditCalculationName.text().strip() or "Capture_zone"
        path, _ = QFileDialog.getSaveFileName(
            self, self._t("save_json_title"), default_name + ".gcz.json",
            self._t("project_file_filter")
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".gcz.json"
        try:
            params = self.get_parameters()
            document = build_document(default_name, params, self.calculation_result)
            save_document(path, document)
            self.set_status(self._t("json_saved", path=path), "success")
        except Exception as exc:
            self.show_error_dialog(self._t("error_title"), self._t("json_save_error", error=str(exc)))

    def load_calculation_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._t("load_json_title"), "", self._t("project_file_filter")
        )
        if not path:
            return
        try:
            document = load_document(path)
            params = document["input_parameters"]
            self._loading_json = True
            self._auto_calculation_name = False
            self.lineEditCalculationName.setText(document.get("calculation_name") or "Capture_zone")
            mapping = {
                self.lineEdit_k: params.get("k"), self.lineEdit_m: params.get("m"),
                self.lineEdit_n: params.get("n"), self.lineEdit_Q: params.get("Q"),
                self.lineEdit_I: params.get("I"), self.lineEdit_time: params.get("t"),
                self.lineEdit_flow_direction: params.get("flow_direction"),
            }
            for widget, value in mapping.items():
                if value is not None:
                    widget.setText(str(value))
            self.checkBoxStandardTimes.setChecked(bool(params.get("standard_time_variants", False)))

            project = QgsProject.instance()
            layer = project.mapLayer(str(params.get("source_layer_id", "")))
            if layer is None:
                source_name = str(params.get("source_layer", ""))
                matches = project.mapLayersByName(source_name) if source_name else []
                layer = matches[0] if matches else None
            self.mMapLayerComboBox.setLayer(layer)
            self._loading_json = False
            self.invalidate_calculation()
            valid, _ = self.validate_all_inputs()
            if valid:
                self.on_calculate()
                self.set_status(self._t("json_loaded_recalculated", path=path), "success")
            else:
                self.set_status(self._t("json_loaded_needs_layer", path=path), "warning")
        except Exception as exc:
            self._loading_json = False
            self.show_error_dialog(self._t("error_title"), self._t("json_load_error", error=str(exc)))

    def request_report(self, report_format: str):
        if not self.is_calculated or not self.calculation_result:
            self.show_warning_dialog(self._t("no_calculation_title"), self._t("no_calculation_message"))
            return
        try:
            self.reportRequested.emit(
                report_format, self.calculation_result, self.mMapLayerComboBox.currentLayer(),
                self.get_parameters(), self.lineEditCalculationName.text().strip(),
            )
        except Exception as exc:
            self.show_error_dialog(self._t("error_title"), str(exc))

    def setup_preview_controls(self):
        """Add a one-click button for clearing the temporary canvas preview."""
        self.buttonClearPreview = QPushButton(self)
        self.buttonClearPreview.setObjectName("buttonClearPreview")
        self.buttonClearPreview.setMinimumHeight(32)
        self.buttonClearPreview.setEnabled(False)
        self.horizontalLayout_buttons.insertWidget(1, self.buttonClearPreview)

    def set_preview_available(self, available: bool):
        """Synchronize the preview-removal button with the QGIS map state."""
        self.buttonClearPreview.setEnabled(bool(available))

    def request_preview_removal(self, show_status: bool = True):
        """Ask the plugin to clear all temporary preview canvas items."""
        self.clearPreviewRequested.emit()
        self.set_preview_available(False)
        if show_status:
            self.set_status(self._t("preview_removed"), "info")

    def get_language(self) -> str:
        """Return the currently selected interface language code."""
        return self.current_language

    def on_language_changed(self, *_):
        """Translate the open dialog and an existing preview without recalculation."""
        language = self.comboLanguage.currentData()
        self.current_language = language if language in ("pl", "en") else DEFAULT_LANGUAGE
        preview_was_visible = self.buttonClearPreview.isEnabled()
        self.apply_language(refresh_status=True)
        if preview_was_visible and self.is_calculated and self.calculation_result:
            try:
                params = self.get_parameters()
                self.previewRequested.emit(
                    self.calculation_result,
                    self.mMapLayerComboBox.currentLayer(),
                    params,
                )
            except Exception as exc:
                self.logger.warning(f"Could not refresh translated preview: {exc}")

    def apply_language(self, refresh_status: bool = True):
        """Apply the selected language to all visible labels and tooltips."""
        self.setWindowTitle(WINDOW_TITLE)
        self.labelLanguage.setText(self._t("language_label"))
        self.labelCalculationName.setText(self._t("calculation_name"))
        self.lineEditCalculationName.setToolTip(self._t("calculation_name_tooltip"))

        self.groupBox_well.setTitle(self._t("well_location"))
        self.label_layer.setText(self._t("select_well_layer"))
        self.mMapLayerComboBox.setToolTip(self._t("well_layer_tooltip"))
        self.label_layer_info.setText(self._t("well_layer_info"))

        self.groupBox_aquifer.setTitle(self._t("aquifer_parameters"))
        self.label_k.setText(self._t("hydraulic_conductivity"))
        self.lineEdit_k.setToolTip(self._t("hydraulic_conductivity_tooltip"))
        self.label_m.setText(self._t("aquifer_thickness"))
        self.lineEdit_m.setToolTip(self._t("aquifer_thickness_tooltip"))
        self.label_n.setText(self._t("effective_porosity"))
        self.lineEdit_n.setToolTip(self._t("effective_porosity_tooltip"))

        self.groupBox_well_flow.setTitle(self._t("well_flow_conditions"))
        self.label_Q.setText(self._t("well_discharge"))
        self.lineEdit_Q.setToolTip(self._t("well_discharge_tooltip"))
        self.label_I.setText(self._t("hydraulic_gradient"))
        self.lineEdit_I.setToolTip(self._t("hydraulic_gradient_tooltip"))
        self.label_flow_direction.setText(self._t("flow_direction"))
        self.lineEdit_flow_direction.setToolTip(self._t("flow_direction_tooltip"))
        self.label_flow_direction_unit.setText(self._t("degrees_from_north"))
        self.label_flow_help.setText(self._t("flow_help"))

        self.groupBox_time.setTitle(self._t("time_of_travel"))
        self.label_time.setText(self._t("protection_time"))
        self.lineEdit_time.setToolTip(self._t("protection_time_tooltip"))
        self.label_time_unit.setText(self._t("years"))
        self.label_time_help.setText(self._t("time_help"))
        self.checkBoxStandardTimes.setText(self._t("standard_time_variants"))

        self.groupBox_results.setTitle(self._t("calculation_results"))
        self.label_result_T_tilde.setText(self._t("dimensionless_time"))
        self.label_result_zone_type.setText(self._t("zone_type"))
        self.label_result_Qo.setText(self._t("ambient_flow"))
        self.label_result_Ls.setText(self._t("stagnation_point"))
        self.label_result_Lu.setText(self._t("upstream_extent"))
        self.label_result_Ydiv.setText(self._t("max_width"))

        self.buttonCalculate.setText(self._t("calculate"))
        self.buttonCalculate.setToolTip(self._t("calculate_tooltip"))
        self.buttonClearPreview.setText(self._t("clear_preview"))
        self.buttonClearPreview.setToolTip(self._t("clear_preview_tooltip"))
        self.buttonCopyResults.setText(self._t("copy_results"))
        self.buttonSaveJson.setText(self._t("save_json"))
        self.buttonLoadJson.setText(self._t("load_json"))
        self.buttonReportHtml.setText(self._t("report_html"))
        self.buttonReportPdf.setText(self._t("report_pdf"))
        ok_button = self.buttonBox.button(QDIALOG_OK)
        cancel_button = self.buttonBox.button(QDIALOG_CANCEL)
        help_button = self.buttonBox.button(QDIALOG_HELP)
        if ok_button:
            ok_button.setText(self._t("ok"))
        if cancel_button:
            cancel_button.setText(self._t("cancel"))
        if help_button:
            help_button.setText(self._t("help"))

        self.update_gradient_dependent_controls()

        if self.calculation_result:
            self.display_results(self.calculation_result)

        if refresh_status:
            if self.is_calculated and self.calculation_result:
                variants = result_variants(self.calculation_result)
                if len(variants) > 1:
                    self.set_status(self._t("calculation_success_variants"), "success")
                else:
                    primary = variants[0] if variants else self.calculation_result
                    zone_name = zone_display_name(primary.get("zone_type", ""), self.current_language)
                    self.set_status(self._t("calculation_success", zone_type=zone_name), "success")
            else:
                self.validate_all_inputs()

    def setup_validators(self):
        """
        Setup FlexibleDoubleValidators for numeric input fields.

        Creates validators with appropriate ranges that accept both dot and comma
        as decimal separators for international compatibility:
        - Positive values (k, m, Q, t): 0.0 to large number
        - Porosity (n): 0.0 to 1.0
        - Gradient (I): 0.0 to 1.0
        - Flow direction: 0.0 to 360.0
        """
        # Validator for positive values (k, m, Q, t)
        positive_validator = FlexibleDoubleValidator(0.0, 1000000.0, 10, self)
        positive_validator.setNotation(QVALIDATOR_STANDARD_NOTATION)

        # Validator for porosity (0 to 1)
        porosity_validator = FlexibleDoubleValidator(0.0, 1.0, 10, self)
        porosity_validator.setNotation(QVALIDATOR_STANDARD_NOTATION)

        # Validator for hydraulic gradient (0 to 1)
        gradient_validator = FlexibleDoubleValidator(0.0, 1.0, 10, self)
        gradient_validator.setNotation(QVALIDATOR_STANDARD_NOTATION)

        # Validator for flow direction (0 to 360)
        angle_validator = FlexibleDoubleValidator(0.0, 360.0, 10, self)
        angle_validator.setNotation(QVALIDATOR_STANDARD_NOTATION)

        # Apply validators to fields
        self.lineEdit_k.setValidator(positive_validator)
        self.lineEdit_m.setValidator(positive_validator)
        self.lineEdit_Q.setValidator(positive_validator)
        self.lineEdit_time.setValidator(positive_validator)
        self.lineEdit_n.setValidator(porosity_validator)
        self.lineEdit_I.setValidator(gradient_validator)
        self.lineEdit_flow_direction.setValidator(angle_validator)

        self.logger.debug("Validators setup completed")

    def connect_signals(self):
        """
        Connect UI signals to appropriate slot methods.

        Connections:
        - Calculate button -> calculation handler
        - Layer changed -> layer validation
        - All input fields -> validation check
        - Button box -> accept/reject handlers
        - Help button -> help display
        """
        # Language selector
        self.comboLanguage.currentIndexChanged.connect(self.on_language_changed)
        self.lineEditCalculationName.textEdited.connect(self.on_calculation_name_edited)
        self.checkBoxStandardTimes.toggled.connect(self.on_standard_times_changed)

        # Calculate and preview buttons
        self.buttonCalculate.clicked.connect(self.on_calculate)
        self.buttonClearPreview.clicked.connect(self.request_preview_removal)

        # Layer selection changed
        self.mMapLayerComboBox.layerChanged.connect(self.on_layer_changed)

        # Any change in an input invalidates the previously calculated result.
        self.lineEdit_k.textChanged.connect(self.on_input_changed)
        self.lineEdit_m.textChanged.connect(self.on_input_changed)
        self.lineEdit_n.textChanged.connect(self.on_input_changed)
        self.lineEdit_Q.textChanged.connect(self.on_input_changed)
        self.lineEdit_I.textChanged.connect(self.on_input_changed)
        self.lineEdit_I.textChanged.connect(self.update_gradient_dependent_controls)
        self.lineEdit_flow_direction.textChanged.connect(self.on_input_changed)
        self.lineEdit_flow_direction.textChanged.connect(self.update_flow_direction_preview)
        self.lineEdit_time.textChanged.connect(self.on_input_changed)
        self.lineEdit_time.textChanged.connect(self.update_calculation_name_suggestion)

        self.buttonCopyResults.clicked.connect(self.copy_results_to_clipboard)
        self.buttonSaveJson.clicked.connect(self.save_calculation_json)
        self.buttonLoadJson.clicked.connect(self.load_calculation_json)
        self.buttonReportHtml.clicked.connect(lambda: self.request_report("html"))
        self.buttonReportPdf.clicked.connect(lambda: self.request_report("pdf"))

        # Button box
        # Note: accept/reject connections are in UI file, but we override the methods

        # Help button
        help_button = self.buttonBox.button(QDIALOG_HELP)
        if help_button:
            help_button.clicked.connect(self.show_help)

        self.logger.debug("Signal connections completed")

    def invalidate_calculation(self, reason: Optional[str] = None):
        """Discard a result that no longer matches the current input data."""
        had_result = self.is_calculated or self.calculation_result is not None
        self.calculation_result = None
        self.is_calculated = False
        self.calculation_signature = None
        self.cached_layer = None
        self.cached_parameters = None
        self.clear_results()
        self.set_result_actions_enabled(False)
        self.buttonBox.button(QDIALOG_OK).setEnabled(False)

        if had_result and reason:
            self.set_status(reason, "warning")
            self.logger.info(reason)

    def on_input_changed(self):
        """Handle a changed hydrogeological input value."""
        if self._loading_json:
            return
        had_result = self.is_calculated
        if had_result:
            self.request_preview_removal(show_status=False)
        self.invalidate_calculation()
        is_valid, _ = self.validate_all_inputs()
        if had_result and is_valid:
            self.set_status(
                self._t("input_changed"),
                "warning",
            )

    def prepare_for_run(self):
        """Prepare a reused dialog for a new plugin invocation."""
        self.setWindowTitle(WINDOW_TITLE)
        self.request_preview_removal(show_status=False)
        self.invalidate_calculation()
        self.validate_all_inputs()

    def get_input_signature(self):
        """Return a signature used to detect stale results before acceptance."""
        layer_valid, layer_error, _ = self.validate_layer()
        if not layer_valid:
            raise ValueError(layer_error or self._t("invalid_layer"))
        layer = self.mMapLayerComboBox.currentLayer()
        params = self.get_parameters()
        signature_keys = (
            "k", "m", "n", "Q", "I", "t", "flow_direction",
            "well_x", "well_y", "source_layer_id", "crs_authid",
            "standard_time_variants", "time_variants",
        )
        return tuple((key, params[key]) for key in signature_keys)

    def validate_layer(self) -> Tuple[bool, Optional[str], int]:
        """
        Validate the selected well layer.

        Checks:
        - Layer is not None
        - Layer is a valid QgsVectorLayer
        - Layer geometry type is Point
        - Layer is valid
        - Feature count is exactly 1
        - Feature has geometry

        Returns:
            Tuple of (is_valid, error_message, feature_count)
            - is_valid: True if layer passes all checks
            - error_message: Description of error if invalid, None if valid
            - feature_count: Number of features in layer
        """
        layer = self.mMapLayerComboBox.currentLayer()

        # Check if layer is selected
        if layer is None:
            return False, self._t("no_layer"), 0

        # Check if layer is a vector layer
        if not isinstance(layer, QgsVectorLayer):
            return False, self._t("not_vector"), 0

        # Check if layer is valid
        if not layer.isValid():
            return False, self._t("invalid_layer"), 0

        # Check geometry type. Multipart point layers are not accepted because
        # the calculation requires one unambiguous well coordinate.
        if layer.geometryType() != QGIS_GEOMETRY_POINT:
            return False, self._t("point_required"), 0
        if QgsWkbTypes.isMultiType(layer.wkbType()):
            return False, self._t("single_point_not_multipoint"), 0

        # The analytical equations operate in metres. Polish national systems
        # EPSG:2180 and EPSG:2176-2179 are explicitly recognised as preferred.
        crs = layer.crs()
        if not crs or not crs.isValid():
            return False, self._t("invalid_crs"), 0
        if crs.isGeographic():
            return False, self._t("geographic_crs", crs=crs.authid()), 0
        if crs.mapUnits() != QGIS_DISTANCE_METERS:
            return False, self._t("non_metric_crs", crs=crs.authid()), 0

        # Check feature count
        feature_count = layer.featureCount()
        if feature_count == 0:
            return False, self._t("no_features"), 0
        elif feature_count > 1:
            return False, self._t("one_feature_required", count=feature_count), feature_count

        # Check if feature has geometry
        feature = next(layer.getFeatures())
        if not feature.hasGeometry():
            return False, self._t("feature_no_geometry"), feature_count
        if feature.geometry().isMultipart():
            return False, self._t("feature_single_point"), feature_count

        # All checks passed
        self.logger.debug(f"Layer validation passed: {layer.name()}")
        return True, None, feature_count

    def on_layer_changed(self):
        """Handle well-layer changes and invalidate any previous result."""
        if self._loading_json:
            return
        self.update_calculation_name_suggestion()
        had_result = self.is_calculated
        if had_result:
            self.request_preview_removal(show_status=False)
        self.invalidate_calculation()
        is_valid, error_msg, _ = self.validate_layer()

        if is_valid:
            layer = self.mMapLayerComboBox.currentLayer()
            crs = layer.crs()
            preferred = is_preferred_polish_crs(crs.authid())
            crs_note = self._t("preferred_polish_crs") if preferred else self._t("projected_metric_crs")
            self.set_status(
                self._t("layer_selected", layer=layer.name(), crs=crs.authid(), crs_note=crs_note),
                "success",
            )
            self.mark_layer_valid()
        else:
            if error_msg:
                self.set_status(self._t("layer_error", error=error_msg), "error")
            self.mark_layer_invalid()

        inputs_valid, _ = self.validate_all_inputs()
        if had_result and inputs_valid:
            self.set_status(
                self._t("layer_changed"),
                "warning",
            )

    def validate_numeric_input(
        self,
        widget,
        name: str,
        min_val: float,
        max_val: float,
        exclude_zero: bool = False
    ) -> Tuple[Optional[float], Optional[str]]:
        """
        Validate a numeric input field.

        Accepts both dot (.) and comma (,) as decimal separators for international
        compatibility. Normalizes input before parsing.

        Args:
            widget: QLineEdit widget to validate
            name: Display name for error messages
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            exclude_zero: If True, zero is not allowed (default: False)

        Returns:
            Tuple of (value, error_message)
            - value: Parsed float value if valid, None if invalid
            - error_message: Description of error if invalid, None if valid
        """
        text = widget.text().strip()

        # Check if empty
        if not text:
            return None, self._t("required", name=name)

        # Normalize: replace comma with dot for parsing
        # This allows both "3.14" and "3,14" to be valid inputs
        normalized_text = text.replace(',', '.')

        # Try to parse as float
        try:
            value = float(normalized_text)
        except ValueError:
            return None, self._t("valid_number", name=name)

        # Check if zero when not allowed
        if exclude_zero and value == 0:
            return None, self._t("cannot_be_zero", name=name)

        # Check range
        if value < min_val or value > max_val:
            return None, self._t("range", name=name, min_val=min_val, max_val=max_val)

        return value, None

    def update_gradient_dependent_controls(self):
        """Disable flow-direction controls when the ambient gradient is zero."""
        try:
            gradient = float(self.lineEdit_I.text().strip().replace(',', '.'))
        except (TypeError, ValueError):
            gradient = None

        has_direction = gradient is None or abs(gradient) > 1e-15
        for widget_name in (
            "lineEdit_flow_direction",
            "label_flow_direction",
            "label_flow_direction_unit",
            "flowDirectionPreview",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(has_direction)

        if has_direction:
            self.lineEdit_flow_direction.setToolTip(self._t("flow_direction_tooltip"))
        else:
            self.lineEdit_flow_direction.setToolTip(self._t("gradient_zero_note"))

    def validate_all_inputs(self) -> Tuple[bool, List[str]]:
        """
        Validate all input fields and update UI accordingly.

        Validates:
        - Layer selection
        - All numeric parameters with appropriate ranges

        Updates:
        - Visual feedback (red borders on invalid fields)
        - Calculate button enabled state
        - Status message

        Returns:
            Tuple of (is_valid, errors)
            - is_valid: True if all inputs are valid
            - errors: List of error messages
        """
        errors = []

        # Validate layer
        layer_valid, layer_error, _ = self.validate_layer()
        if not layer_valid:
            errors.append(self._t("layer_prefix", error=layer_error))

        # Validate numeric inputs
        validations = [
            (self.lineEdit_k, self._t("param_k"), 0.0, 10000.0, True),
            (self.lineEdit_m, self._t("param_m"), 0.0, 1000.0, True),
            (self.lineEdit_n, self._t("param_n"), 0.0, 1.0, True),
            (self.lineEdit_Q, self._t("param_Q"), 0.0, 100000.0, True),
            (self.lineEdit_I, self._t("param_I"), 0.0, 1.0, False),
        ]
        try:
            gradient_for_validation = float(self.lineEdit_I.text().strip().replace(',', '.'))
        except (TypeError, ValueError):
            gradient_for_validation = None
        if gradient_for_validation is None or abs(gradient_for_validation) > 1e-15:
            validations.append(
                (self.lineEdit_flow_direction, self._t("param_flow_direction"), 0.0, 360.0, False)
            )
        else:
            self.mark_field_valid(self.lineEdit_flow_direction)
        if not self.checkBoxStandardTimes.isChecked():
            validations.insert(5, (self.lineEdit_time, self._t("param_t"), 0.0, 100.0, True))
        else:
            self.mark_field_valid(self.lineEdit_time)

        for widget, name, min_val, max_val, exclude_zero in validations:
            value, error = self.validate_numeric_input(widget, name, min_val, max_val, exclude_zero)

            if not error and widget is self.lineEdit_n and value >= 1.0:
                error = self._t("between_zero_one", name=name)
            if not error and widget is self.lineEdit_I and value >= 1.0:
                error = self._t("range", name=name, min_val=0.0, max_val="< 1")

            if error:
                errors.append(error)
                self.mark_field_invalid(widget)
            else:
                self.mark_field_valid(widget)

        # Update UI based on validation
        is_valid = len(errors) == 0

        # Enable/disable Calculate button
        self.buttonCalculate.setEnabled(is_valid)

        # Update status message
        if is_valid:
            self.set_status(self._t("ready_calculate"), "success")
        else:
            # Show first error in status
            if errors:
                self.set_status(self._t("validation_error", error=errors[0]), "error")

        return is_valid, errors

    def mark_field_valid(self, widget):
        """
        Mark an input field as valid by removing error styling.

        Args:
            widget: QLineEdit widget to mark as valid
        """
        widget.setStyleSheet("")

    def mark_field_invalid(self, widget):
        """
        Mark an input field as invalid with red border.

        Args:
            widget: QLineEdit widget to mark as invalid
        """
        widget.setStyleSheet("border: 2px solid red;")

    def mark_layer_valid(self):
        """
        Mark layer selection as valid (optional visual feedback).
        """
        # Optional: could add visual feedback for layer combo box
        pass

    def mark_layer_invalid(self):
        """
        Mark layer selection as invalid (optional visual feedback).
        """
        # Optional: could add visual feedback for layer combo box
        pass

    def on_calculate(self):
        """Calculate one zone or the standard 1/5/10/25/50-year variants."""
        self.logger.info("Calculate button clicked")
        is_valid, errors = self.validate_all_inputs()
        if not is_valid:
            error_text = self._t("fix_errors", errors="\n".join(f"• {e}" for e in errors))
            self.show_error_dialog(self._t("invalid_input_title"), error_text)
            return

        self.set_status(self._t("calculating"), "info")
        self.buttonCalculate.setEnabled(False)
        try:
            params = self.get_parameters()
            from ..algorithms.ceric_haitjema import calculate_capture_zone, CaptureZoneParameters

            variants = []
            warnings = []
            for time_years in params["time_variants"]:
                zone_params = CaptureZoneParameters(
                    k=params["k"], m=params["m"], n=params["n"], Q=params["Q"],
                    I=params["I"], t=float(time_years),
                    flow_direction=params["flow_direction"],
                    well_x=params["well_x"], well_y=params["well_y"],
                )
                result = calculate_capture_zone(zone_params)
                result["time_years"] = float(time_years)
                variant_params = dict(params)
                variant_params["t"] = float(time_years)
                warning = assess_zone_scale(result, variant_params)
                if warning:
                    result["scale_warning"] = warning
                    warnings.append((float(time_years), warning))
                variants.append(result)

            self.calculation_result = {
                "variants": variants,
                "multi_variant": len(variants) > 1,
                "primary_time_years": 25.0 if any(abs(v["time_years"] - 25.0) < 1e-9 for v in variants) else variants[-1]["time_years"],
                "plugin_version": PLUGIN_VERSION,
            }
            self.last_scale_warnings = warnings
            lu_warning_times = [
                float(item["time_years"]) for item in variants
                if item.get("lu_approximation_warning")
            ]

            if warnings:
                time_years, scale_warning = max(warnings, key=lambda item: item[1]["max_dimension_m"])
                self.show_warning_dialog(
                    self._t("large_zone_title"),
                    self._t(
                        "large_zone_message",
                        max_dimension_km=scale_warning["max_dimension_m"] / 1000.0,
                        area_km2=scale_warning["area_km2"],
                        reference_km=scale_warning["reference_scale_m"] / 1000.0,
                        ratio=scale_warning["dimension_ratio"],
                    ) + f"\n\n t = {time_years:g} " + self._t("years"),
                )

            if lu_warning_times:
                times_text = ", ".join(f"{value:g}" for value in lu_warning_times)
                self.show_warning_dialog(
                    self._t("lu_approximation_title"),
                    self._t("lu_approximation_message")
                    + f"\n\n t = {times_text} " + self._t("years"),
                )

            self.display_results(self.calculation_result)
            preview_layer = self.mMapLayerComboBox.currentLayer()
            self.previewRequested.emit(self.calculation_result, preview_layer, params)

            self.calculation_signature = self.get_input_signature()
            self.buttonBox.button(QDIALOG_OK).setEnabled(True)
            self.is_calculated = True
            self.set_result_actions_enabled(True)

            if len(variants) > 1:
                self.set_status(self._t("calculation_success_variants"), "success")
            else:
                zone_type = zone_display_name(variants[0]["zone_type"], self.current_language)
                self.set_status(self._t("calculation_success", zone_type=zone_type), "success")
            self.logger.info(f"Calculation completed successfully for {len(variants)} variant(s)")

        except Exception as e:
            self.logger.error(f"Calculation error: {str(e)}", exc_info=True)
            self.show_error_dialog(
                self._t("calculation_error_title"),
                self._t("calculation_error_message", error=str(e)),
            )
            self.set_status(self._t("calculation_failed"), "error")
            self.invalidate_calculation()
        finally:
            self.buttonCalculate.setEnabled(True)

    def get_parameters(self) -> Dict[str, Any]:
        """
        Extract all parameters from UI fields.

        Accepts both dot (.) and comma (,) as decimal separators by normalizing
        input before parsing.

        Returns:
            Dictionary containing all calculation parameters:
            - k, m, n, Q, I, t, flow_direction: numeric parameters
            - well_x, well_y: well coordinates from layer

        Raises:
            ValueError: If layer or geometry is invalid
        """
        # Get well layer
        layer = self.mMapLayerComboBox.currentLayer()
        if not layer:
            raise ValueError(self._t("no_layer"))

        # Get first (and only) feature
        feature = next(layer.getFeatures())
        if not feature.hasGeometry():
            raise ValueError(self._t("feature_no_geometry"))

        # Get point coordinates
        point = feature.geometry().asPoint()
        well_x = point.x()
        well_y = point.y()

        # Helper function to normalize and parse float values
        def parse_float(text: str) -> float:
            """Normalize comma to dot and parse as float."""
            return float(text.replace(',', '.'))

        # Preserve source well attributes for JSON and calculation reports.
        well_attributes = {}
        for field, value in zip(layer.fields(), feature.attributes()):
            if value is None:
                continue
            # calculation_io converts provider-specific values (e.g. dates)
            # to portable JSON text when required.
            well_attributes[field.name()] = value

        # Extract numeric parameters with normalization
        params = {
            'k': parse_float(self.lineEdit_k.text()),
            'm': parse_float(self.lineEdit_m.text()),
            'n': parse_float(self.lineEdit_n.text()),
            'Q': parse_float(self.lineEdit_Q.text()),
            'I': parse_float(self.lineEdit_I.text()),
            't': 25.0 if self.checkBoxStandardTimes.isChecked() else parse_float(self.lineEdit_time.text()),
            'flow_direction': (
                parse_float(self.lineEdit_flow_direction.text())
                if self.lineEdit_flow_direction.text().strip()
                else 0.0
            ),
            'standard_time_variants': self.checkBoxStandardTimes.isChecked(),
            'time_variants': tuple(STANDARD_TIME_VARIANTS) if self.checkBoxStandardTimes.isChecked() else (parse_float(self.lineEdit_time.text()),),
            'calculation_name': self.lineEditCalculationName.text().strip() or build_calculation_name(layer.name(), 25.0 if self.checkBoxStandardTimes.isChecked() else parse_float(self.lineEdit_time.text()), self.checkBoxStandardTimes.isChecked()),
            'well_x': well_x,
            'well_y': well_y,
            'source_layer': layer.name(),
            'source_layer_id': layer.id(),
            'crs_authid': layer.crs().authid(),
            'crs_name': layer.crs().description(),
            'well_attributes': well_attributes,
            'plugin_version': PLUGIN_VERSION,
            'ui_language': self.current_language,
        }

        self.logger.debug(f"Parameters extracted: {params}")
        return params

    def display_results(self, result: Dict[str, Any]):
        """Display detailed single- or multi-variant results in the panel."""
        try:
            params = self.get_parameters()
            name = self.lineEditCalculationName.text().strip() or "Capture_zone"
            summary = build_summary_text(name, params, result, self.current_language)
            self.resultSummary.setPlainText(summary)
            self.set_result_actions_enabled(True)
            variants = result_variants(result)
            self.logger.info(f"Displayed {len(variants)} capture zone result variant(s)")
        except Exception as exc:
            self.resultSummary.setPlainText(str(exc))
            self.logger.error(f"Could not display results: {exc}", exc_info=True)

    def clear_results(self):
        """Clear the detailed result panel."""
        if hasattr(self, "resultSummary"):
            self.resultSummary.clear()
        self.set_result_actions_enabled(False) if hasattr(self, "buttonCopyResults") else None

    def set_status(self, message: str, status_type: str = "info"):
        """
        Set status message with color coding.

        Args:
            message: Status message to display
            status_type: Type of status - 'info', 'success', 'error', or 'warning'

        Colors:
        - info: blue (#0066cc)
        - success: green (#009900)
        - error: red (#cc0000)
        - warning: orange (#ff6600)
        """
        colors = {
            'info': '#0066cc',
            'success': '#009900',
            'error': '#cc0000',
            'warning': '#ff6600'
        }

        color = colors.get(status_type, colors['info'])
        self.labelStatus.setText(message)
        self.labelStatus.setStyleSheet(f"color: {color}; padding: 5px;")

    def show_error_dialog(self, title: str, message: str):
        """
        Show error message dialog.

        Args:
            title: Dialog title
            message: Error message to display
        """
        QMessageBox.critical(self, title, message)

    def show_warning_dialog(self, title: str, message: str):
        """
        Show warning message dialog.

        Args:
            title: Dialog title
            message: Warning message to display
        """
        QMessageBox.warning(self, title, message)

    def show_info_dialog(self, title: str, message: str):
        """
        Show information message dialog.

        Args:
            title: Dialog title
            message: Information message to display
        """
        QMessageBox.information(self, title, message)

    def show_help(self):
        """Show method, assumptions and workflow in the selected language."""
        if self.current_language == "pl":
            help_text = f"""
<h3>GEAQUA Capture Zones v{PLUGIN_VERSION} — pomoc</h3>
<p><b>Cel:</b> analityczne wyznaczanie stref dopływu o zadanym czasie przepływu dla pojedynczej studni w jednorodnym regionalnym polu przepływu wód podziemnych.</p>
<h4>Dane wejściowe</h4>
<p><b>Lokalizacja studni:</b> punktowa warstwa wektorowa zawierająca dokładnie jeden obiekt punktowy.</p>
<ul>
<li><b>k</b> [m/d] — współczynnik filtracji; <b>m</b> [m] — miąższość zawodniona; <b>n</b> [-] — porowatość efektywna.</li>
<li><b>Q</b> [m³/d] — wydajność pompowania; <b>I</b> [-] — spadek hydrauliczny. I = 0 oznacza brak przepływu regionalnego.</li>
<li><b>Kierunek przepływu</b> — azymut liczony zgodnie z ruchem wskazówek zegara od północy: 0° — północ, 90° — wschód, 180° — południe, 270° — zachód. Przy I = 0 jest ignorowany.</li>
<li><b>t</b> [lata] — czas dopływu albo warianty 1, 5, 10, 25 i 50 lat.</li>
</ul>
<h4>Typy obliczanych stref</h4>
<ul>
<li><b>Strefa kołowa centryczna:</b> T̃ ≤ 0,1.</li>
<li><b>Strefa kołowa ekscentryczna:</b> 0,1 &lt; T̃ ≤ 1.</li>
<li><b>Strefa dopływu w jednorodnym polu przepływu:</b> T̃ &gt; 1.</li>
</ul>
<p>Progi klasyfikacji, współczynniki i wzory aproksymacyjne przyjęto według Ceric i Haitjema (2005). Dla I = 0 przyjmuje się Q₀ = 0, T₀ → ∞ i T̃ = 0, dlatego stosowana jest strefa kołowa centryczna. Czas w latach przeliczany jest jako 365,25 dnia na rok.</p>
<h4>Podstawy metodyczne</h4>
<ul>
<li><b>Ceric, A. i Haitjema, H. (2005)</b>, <i>On Using Simple Time-of-Travel Capture Zone Delineation Methods</i>, Ground Water 43(3), 408–412, DOI: 10.1111/j.1745-6584.2005.0035.x — główne źródło zastosowanych równań i progów.</li>
<li><b>Grubb, S. (1993)</b>, <i>Analytical Model for Estimation of Steady-State Capture Zones of Pumping Wells in Confined and Unconfined Aquifers</i>, Ground Water 31(1), 27–32 — punkt stagnacji, granica dopływu i linia rozdziału.</li>
<li><b>Bear, J. i Jacobs, M. (1965)</b>, <i>On the movement of water bodies injected into aquifers</i>, Journal of Hydrology 3, 37–57 — rozwiązanie bazowe dla izochron.</li>
</ul>
<h4>Najważniejsze ograniczenia</h4>
<p>Zakłada się pojedynczą, w pełni ujmującą studnię o stałej wydajności, jednorodną i izotropową warstwę o stałej miąższości, poziomy przepływ zgodny z założeniem Dupuita oraz brak dyspersji. Przepływ regionalny jest jednorodny albo zerowy. Nie są odwzorowane granice hydrodynamiczne, lokalne zasilanie, przecieki, retencja, sorpcja ani współdziałanie wielu studni. Obliczona strefa dopływu nie jest automatycznie prawną strefą ochronną i wymaga oceny hydrogeologicznej.</p>
<h4>Sposób pracy</h4>
<ol>
<li>Wybierz studnię, wpisz parametry i nazwę obliczenia.</li>
<li>Kliknij „Oblicz strefę dopływu”, skontroluj podgląd i panel wyników.</li>
<li>Zapisz projekt, utwórz raport albo kliknij „Zapisz wynik”, aby dodać końcową warstwę poligonową.</li>
</ol>
<p><b>CRS:</b> zalecany EPSG:2180 oraz EPSG:2176–2179; dopuszczalne są inne projekcyjne układy metryczne.</p>
"""
        else:
            help_text = f"""
<h3>GEAQUA Capture Zones v{PLUGIN_VERSION} — Help</h3>
<p><b>Purpose:</b> analytical delineation of time-of-travel capture zones for one pumping well in a uniform regional groundwater-flow field.</p>
<h4>Input</h4>
<p><b>Well location:</b> a point vector layer containing exactly one point feature.</p>
<ul>
<li><b>k</b> [m/d] hydraulic conductivity; <b>m</b> [m] saturated thickness; <b>n</b> [-] effective porosity.</li>
<li><b>Q</b> [m³/d] pumping rate; <b>I</b> [-] hydraulic gradient. I = 0 means no ambient flow.</li>
<li><b>Flow direction</b> — azimuth measured clockwise from North: 0° North, 90° East, 180° South and 270° West. It is ignored when I = 0.</li>
<li><b>t</b> [years] travel time, or the standard 1, 5, 10, 25 and 50 year variants.</li>
</ul>
<h4>Calculated zone types</h4>
<ul>
<li><b>Centric circular zone:</b> T̃ ≤ 0.1.</li>
<li><b>Eccentric circular zone:</b> 0.1 &lt; T̃ ≤ 1.</li>
<li><b>Capture zone in uniform flow:</b> T̃ &gt; 1.</li>
</ul>
<p>The classification thresholds, coefficients and approximation equations follow Ceric and Haitjema (2005). For I = 0, Q₀ = 0, T₀ → ∞ and T̃ = 0, so the centric circular zone is used. Years are converted using 365.25 days per year.</p>
<h4>Methodological basis</h4>
<ul>
<li><b>Ceric, A. and Haitjema, H. (2005)</b>, <i>On Using Simple Time-of-Travel Capture Zone Delineation Methods</i>, Ground Water 43(3), 408–412, DOI: 10.1111/j.1745-6584.2005.0035.x — primary source of the equations and thresholds used.</li>
<li><b>Grubb, S. (1993)</b>, <i>Analytical Model for Estimation of Steady-State Capture Zones of Pumping Wells in Confined and Unconfined Aquifers</i>, Ground Water 31(1), 27–32 — stagnation point, upgradient divide and dividing streamline.</li>
<li><b>Bear, J. and Jacobs, M. (1965)</b>, <i>On the movement of water bodies injected into aquifers</i>, Journal of Hydrology 3, 37–57 — underlying isochrone solution.</li>
</ul>
<h4>Main limitations</h4>
<p>The method assumes one fully penetrating well pumping at a constant rate, a homogeneous and isotropic aquifer of constant thickness, horizontal flow under the Dupuit assumption, and no hydrodynamic dispersion. Ambient flow is uniform or zero. The method does not represent hydrodynamic boundaries, local recharge, leakage, storage, sorption or interacting wells. A calculated capture zone is not automatically a legally designated protection area and requires hydrogeological review.</p>
<h4>Workflow</h4>
<ol>
<li>Select the well, enter parameters and a calculation name.</li>
<li>Click “Calculate capture zone” and review the canvas preview and result panel.</li>
<li>Save a project, generate a report, or click “Save Result” to add the final polygon layer.</li>
</ol>
<p><b>CRS:</b> EPSG:2180 and EPSG:2176–2179 are recommended; other projected metric CRSs are accepted.</p>
"""
        self.show_info_dialog(self._t("help_title", version=PLUGIN_VERSION), help_text)

    def accept(self):
        """
        Handle dialog acceptance (OK button).

        Only allows acceptance if calculation has been performed successfully.
        Shows warning if user tries to accept without calculating.

        Caches layer and parameters before closing to prevent data loss.
        """
        if not self.is_calculated:
            self.show_warning_dialog(
                self._t("no_calculation_title"),
                self._t("no_calculation_message"),
            )
            return

        # Verify that the selected layer, its CRS, well coordinate and every
        # parameter still match the values used for the calculation.
        try:
            current_signature = self.get_input_signature()
        except Exception as e:
            self.invalidate_calculation()
            self.show_error_dialog(self._t("invalid_input_title"), str(e))
            return

        if current_signature != self.calculation_signature:
            self.invalidate_calculation()
            self.show_warning_dialog(
                self._t("outdated_title"),
                self._t("outdated_message"),
            )
            return

        # Cache layer and parameters BEFORE dialog closes.
        try:
            self.cached_layer = self.mMapLayerComboBox.currentLayer()
            self.cached_parameters = self.get_parameters()
            self.logger.info(f"Cached layer: {self.cached_layer.name() if self.cached_layer else 'None'}")
            self.logger.info(f"Cached parameters: {self.cached_parameters}")
        except Exception as e:
            self.logger.error(f"Error caching data before closing: {str(e)}", exc_info=True)
            self.show_error_dialog(
                self._t("error_title"),
                self._t("cache_error", error=str(e)),
            )
            return

        self.logger.info("Dialog accepted with valid calculation")
        super().accept()

    def reject(self):
        """
        Handle dialog rejection (Cancel button).

        If calculation has been performed, asks for confirmation before closing.
        """
        if self.is_calculated:
            reply = QMessageBox.question(
                self,
                self._t("confirm_cancel_title"),
                self._t("confirm_cancel_message"),
                QMESSAGE_YES | QMESSAGE_NO,
                QMESSAGE_NO
            )

            if reply == QMESSAGE_NO:
                return

        self.logger.info("Dialog rejected")
        super().reject()

    def get_calculation_result(self) -> Optional[Dict[str, Any]]:
        """
        Get the calculation result for use by main plugin.

        Returns:
            Dictionary containing calculation results, or None if not calculated
        """
        return self.calculation_result

    def get_cached_layer(self) -> Optional[QgsVectorLayer]:
        """
        Get the cached layer reference from before dialog closed.

        Returns:
            QgsVectorLayer that was selected when dialog was accepted, or None
        """
        return self.cached_layer

    def get_cached_parameters(self) -> Optional[Dict[str, Any]]:
        """
        Get the cached parameters from before dialog closed.

        Returns:
            Dictionary containing all calculation parameters, or None
        """
        return self.cached_parameters


# Test block for standalone testing
if __name__ == '__main__':
    """
    Standalone test block for dialog development and testing.

    Usage:
        python ui/capture_zone_dialog.py

    Note: Requires QGIS environment to be initialized.
    """
    # Create application
    app = QApplication(sys.argv)

    # Create and show dialog
    dialog = CaptureZoneDialog()
    dialog.show()

    # Run application
    sys.exit((getattr(app, "exec", None) or getattr(app, "exec_"))())
