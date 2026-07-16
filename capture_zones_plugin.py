"""QGIS integration for GEAQUA Capture Zones.

The plugin creates analytical time-of-travel capture-zone polygons for a
single pumping well using the approximations of Ceric and Haitjema (2005).
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QUrl
from qgis.PyQt.QtGui import QAction, QIcon, QColor, QTextDocument
from qgis.PyQt.QtWidgets import QFileDialog, QApplication

# QGIS core imports for spatial operations
from qgis.PyQt.QtPrintSupport import QPrinter

from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsVectorLayer,
    QgsField,
    QgsFields,
    QgsFeature,
    QgsProject,
    QgsFillSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsRectangle,
)

from qgis.gui import QgsRubberBand

# The toolbar icon is loaded from the plugin directory to avoid
# The toolbar icon is loaded from the plugin directory.
# Import the code for the dialog
from .ui.capture_zone_dialog import CaptureZoneDialog
import os.path
import os
import base64
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from .qgis_logger import get_logger
from .plugin_utils import (
    build_layer_base_name, is_preferred_polish_crs, make_unique_layer_name,
    sanitize_layer_component, zone_dimensions, polygon_area,
)
from .version import PLUGIN_VERSION, PLUGIN_AUTHORS, WINDOW_TITLE
from .translations import DEFAULT_LANGUAGE, translate, zone_display_name
from .calculation_io import result_variants, build_report_html
from .qt_compat import (
    QT_DASH_LINE, QT_NON_MODAL, QPRINTER_HIGH_RESOLUTION, QPRINTER_PDF_FORMAT,
    QGIS_GEOMETRY_POLYGON, QGIS_DISTANCE_METERS, FIELD_TYPE_STRING, FIELD_TYPE_DOUBLE,
    QGIS_MESSAGE_INFO, QGIS_MESSAGE_SUCCESS, QGIS_MESSAGE_WARNING, QGIS_MESSAGE_CRITICAL,
)


class GEAQUACaptureZonesPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        self.translator = None
        locale_value = str(QSettings().value('locale/userLocale', 'pl_PL') or 'pl_PL')
        locale = locale_value[:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GEAQUA_Capture_Zones_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&GEAQUA Capture Zones')
        # The modeless dialog is created lazily.  Keeping an explicit
        # attribute prevents run() from failing before the first dialog is
        # constructed and makes plugin reloads safe.
        self.dlg = None

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        # Preview is drawn exclusively as map-canvas rubber bands. It is not
        # registered as a QgsVectorLayer, so clearing it cannot invalidate
        # layer references held by other QGIS plugins.
        self.preview_rubber_bands = []

        # Setup logging with QGIS integration
        self.logger = get_logger(__name__)
        self.logger.info(f"GEAQUA Capture Zones v{PLUGIN_VERSION} plugin initialized")

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GEAQUA_Capture_Zones', message)

    @staticmethod
    def ui_text(key: str, language: str = DEFAULT_LANGUAGE, **kwargs) -> str:
        """Return a Polish or English user-visible message."""
        return translate(key, language, **kwargs)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.setObjectName("GEAQUA_Capture_Zones_main_action")
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create one action in the Plugins menu and Plugins toolbar.

        Using QgisInterface.addToolBarIcon() follows the standard QGIS plugin
        lifecycle and avoids retaining a dedicated toolbar wrapper which may be
        destroyed independently during application shutdown or plugin reload.
        """
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr(WINDOW_TITLE),
            callback=self.run,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip='GEAQUA Capture Zones — otwórz narzędzie / open tool',
            parent=self.iface.mainWindow(),
        )
        # Make the standard Plugins toolbar visible so the icon is available
        # immediately after enabling the plugin. No toolbar reference is kept.
        try:
            self.iface.pluginToolBar().show()
        except (RuntimeError, AttributeError):
            pass
        self.first_start = True


    def unload(self):
        """Remove QGIS actions and temporary canvas items without stale Qt wrappers."""
        try:
            self.clear_preview(immediate=True)
        except (RuntimeError, AttributeError):
            pass

        for action in list(self.actions):
            # QGIS may already be tearing down menus/toolbars. Every removal is
            # independent so a deleted C++ wrapper cannot abort the rest.
            try:
                self.iface.removePluginMenu(self.menu, action)
            except (RuntimeError, AttributeError, TypeError):
                pass
            try:
                self.iface.removeToolBarIcon(action)
            except (RuntimeError, AttributeError, TypeError):
                pass
            try:
                action.triggered.disconnect(self.run)
            except (RuntimeError, TypeError):
                pass
            try:
                action.deleteLater()
            except RuntimeError:
                pass
        self.actions.clear()

        if self.dlg is not None:
            dialog = self.dlg
            self.dlg = None
            try:
                dialog.hide()
                dialog.deleteLater()
            except RuntimeError:
                pass

    # ========================================================================
    # QGIS Integration Methods
    # ========================================================================
    #
    # This section integrates the Ceric–Haitjema analytical method
    # and QGIS spatial operations. The workflow is:
    #
    # 1. Dialog Processing: User completes calculation in CaptureZoneDialog
    # 2. Result Extraction: get_calculation_result() returns coordinates and metadata
    # 3. CRS Validation: validate_crs() checks for projected coordinate system
    # 4. Geometry Creation: create_qgs_geometry() converts coordinates to QgsGeometry
    # 5. Geometry Validation: validate_geometry() checks and repairs if needed
    # 6. Attribute Preparation: prepare_attributes() organizes all metadata
    # 7. Layer Creation: create_capture_zone_layer() builds QGIS vector layer
    # 8. Project Integration: Layer added to QGIS project and displayed
    #
    # Coordinate System Notes:
    # - Algorithm works in the layer's native coordinate system
    # - Algorithm assumes coordinates are in meters
    # - Algorithm performs rotation by flow_direction internally
    # - Algorithm performs translation to well position internally
    # - No CRS transformation between input and output
    # - Geographic CRS (lat/lon) will produce incorrect results
    #
    # Future Enhancement Opportunities:
    # - TODO: Support for multiple wells (batch processing)
    # - TODO: Support for different input/output CRS with transformation
    # - TODO: Clipping to study area boundaries
    # - TODO: Integration with stream network constraints
    # - TODO: Export to shapefile/GeoPackage
    # - TODO: Styling/symbology templates
    #
    # ========================================================================

    def get_well_coordinates(self, layer: QgsVectorLayer) -> Optional[QgsPointXY]:
        """
        Get coordinates of the well point from the layer.

        Args:
            layer: Point vector layer containing the well location

        Returns:
            QgsPointXY with well coordinates, or None if error

        Raises:
            ValueError: If layer is empty or geometry is invalid
        """
        try:
            # Get the first (and only) feature
            features = list(layer.getFeatures())
            if not features:
                raise ValueError("Layer contains no features")

            feature = features[0]
            if not feature.hasGeometry():
                raise ValueError("Feature has no geometry")

            # Extract point coordinates
            point = feature.geometry().asPoint()
            self.logger.debug(f"Well coordinates: ({point.x():.2f}, {point.y():.2f})")
            return point

        except Exception as e:
            self.logger.error(f"Error getting well coordinates: {str(e)}")
            raise

    def validate_crs(self, crs: QgsCoordinateReferenceSystem, language: str = DEFAULT_LANGUAGE) -> Tuple[bool, bool, Optional[str]]:
        """Validate that the calculation CRS is projected and uses metres.

        EPSG:2180 and EPSG:2176-2179 are recognised as the preferred Polish
        systems. Other projected metric systems are accepted because the
        analytical equations depend on units, not a specific projection.
        """
        if not crs or not crs.isValid():
            return False, False, self.ui_text("invalid_crs", language)

        authid = crs.authid() or "custom CRS"
        if crs.isGeographic():
            return (
                False,
                False,
                self.ui_text("geographic_crs", language, crs=authid),
            )

        if crs.mapUnits() != QGIS_DISTANCE_METERS:
            return (
                False,
                True,
                self.ui_text("non_metric_crs", language, crs=authid),
            )

        if is_preferred_polish_crs(authid):
            message = f"{self.ui_text('preferred_polish_crs', language)}: {authid} — {crs.description()}"
        else:
            message = f"{self.ui_text('projected_metric_crs', language)}: {authid} — {crs.description()}"

        self.logger.info(message)
        return True, True, message

    def create_qgs_geometry(self, coordinates: List[Tuple[float, float]]) -> Optional[QgsGeometry]:
        """
        Create QGIS polygon geometry from coordinate list.

        Args:
            coordinates: List of (x, y) tuples forming the polygon boundary

        Returns:
            QgsGeometry polygon object, or None if creation fails

        Note:
            - Coordinates should form a closed polygon (first = last)
            - If not closed, the method will close it automatically
            - Creates a single-ring polygon
        """
        try:
            if not coordinates or len(coordinates) < 3:
                raise ValueError(f"Insufficient coordinates for polygon: {len(coordinates)}")

            # Create QgsPointXY objects
            points = [QgsPointXY(x, y) for x, y in coordinates]

            # Ensure polygon is closed
            if points[0] != points[-1]:
                points.append(points[0])
                self.logger.debug("Polygon automatically closed")

            # Create polygon geometry
            # Note: Double list - outer list for polygon, inner list for exterior ring
            geometry = QgsGeometry.fromPolygonXY([points])

            if geometry.isNull():
                raise ValueError("Failed to create geometry - result is null")

            self.logger.info(
                f"Created polygon with {len(points)} vertices, "
                f"area: {geometry.area():.2f} m²"
            )

            return geometry

        except Exception as e:
            self.logger.error(f"Error creating geometry: {str(e)}")
            return None

    def validate_geometry(self, geometry: QgsGeometry, language: str = DEFAULT_LANGUAGE) -> Tuple[bool, Optional[QgsGeometry], Optional[str]]:
        """Strictly validate a calculated polygon without silently repairing it."""
        if geometry is None or geometry.isNull():
            return False, None, self.ui_text("geometry_null", language)
        if geometry.type() != QGIS_GEOMETRY_POLYGON:
            return False, None, self.ui_text("geometry_not_polygon", language)
        if not geometry.isGeosValid():
            return False, None, self.ui_text("geometry_invalid", language)
        if not geometry.isSimple():
            return False, None, self.ui_text("geometry_self_intersections", language)
        if geometry.area() <= 0:
            return False, None, self.ui_text("geometry_nonpositive_area", language)

        self.logger.info(
            f"Geometry validation passed: area={geometry.area():.2f} m², "
            f"perimeter={geometry.length():.2f} m"
        )
        return True, geometry, None

    def prepare_attributes(
        self,
        calculation_result: Dict[str, Any],
        input_params: Dict[str, Any],
        geometry: QgsGeometry = None
    ) -> Dict[str, Any]:
        """
        Prepare attributes dictionary for the capture-zone feature.

        Args:
            calculation_result: Result dictionary from algorithm
            input_params: Input parameters dictionary from dialog
            geometry: Optional QgsGeometry for calculating area and perimeter

        Returns:
            Dictionary with all attributes ready for feature creation

        Attributes include:
            - Input parameters: k, m, n, Q, I, t_years, flow_direction
            - Calculation results: zone_type, T_dimensionless, Qo, To
            - Zone parameters: Ls, Lu, Ydiv (asymptotic half-width), R, delta
            - Well location: well_x, well_y
            - Geometric properties: area_m2, perimeter_m
            - Metadata: created
        """
        dimensions = zone_dimensions(calculation_result, input_params)
        time_years = float(calculation_result.get("time_years", input_params.get("t", 0.0)))
        area_m2 = geometry.area() if geometry else polygon_area(calculation_result.get("geometry") or [])
        attributes = {
            # Calculation identity
            'calc_name': str(input_params.get('calculation_name', '')).strip(),
            'variant': f"{time_years:g} years",

            # Zone type and calculation parameters
            'zone_type': zone_display_name(calculation_result.get('zone_type', ''), 'en'),
            'T_tilde': round(calculation_result.get('T_dimensionless', 0), 6),
            'Qo': round(calculation_result.get('Qo', 0), 6),
            'To': (
                round(calculation_result['To'], 2)
                if calculation_result.get('To') is not None else None
            ),

            # Input parameters
            'k': round(float(input_params.get('k', 0)), 4),
            'm': round(float(input_params.get('m', 0)), 2),
            'n': round(float(input_params.get('n', 0)), 4),
            'Q': round(float(input_params.get('Q', 0)), 2),
            'I': round(float(input_params.get('I', 0)), 6),
            't_years': round(time_years, 2),
            'flow_dir': (
                None if calculation_result.get('ambient_flow_zero')
                else round(float(input_params.get('flow_direction', 0)), 2)
            ),
            'time_days': round(float(calculation_result.get('time_days', time_years * 365.25)), 2),
            'days_year': round(float(calculation_result.get('days_per_year', 365.25)), 2),
            'flow_case': 'zero ambient flow' if calculation_result.get('ambient_flow_zero') else 'uniform ambient flow',

            # Zone parameters (may be None for some zone types)
            'Ls': round(calculation_result['Ls'], 2) if calculation_result.get('Ls') is not None else None,
            'Lu': round(calculation_result['Lu'], 2) if calculation_result.get('Lu') is not None else None,
            'Ydiv': round(calculation_result['Ydiv'], 2) if calculation_result.get('Ydiv') is not None else None,
            'R': round(calculation_result['R'], 2) if calculation_result.get('R') is not None else None,
            'delta': round(calculation_result['delta'], 2) if calculation_result.get('delta') is not None else None,

            # Well coordinates
            'well_x': round(float(input_params.get('well_x', 0)), 2),
            'well_y': round(float(input_params.get('well_y', 0)), 2),

            # Geometric properties (calculated if geometry provided)
            'area_m2': round(area_m2, 2),
            'area_ha': round(area_m2 / 10000.0, 6),
            'area_km2': round(area_m2 / 1000000.0, 8),
            'perimeter_m': round(geometry.length(), 2) if geometry else None,
            'upstream_m': round(dimensions['upstream_m'], 2),
            'downstream_m': round(dimensions['downstream_m'], 2),
            'length_m': round(dimensions['length_m'], 2),
            'width_m': round(dimensions['width_m'], 2),

            # Source and CRS metadata
            'source_lyr': str(input_params.get('source_layer', '')),
            'crs_authid': str(input_params.get('crs_authid', '')),
            'crs_name': str(input_params.get('crs_name', '')),

            # Metadata
            'plugin_ver': PLUGIN_VERSION,
            'created': datetime.now().isoformat(timespec='seconds')
        }

        self.logger.debug(f"Prepared attributes: {attributes}")
        return attributes

    def create_field_list(self) -> List[QgsField]:
        """
        Create comprehensive field definitions for capture-zone layer attributes.

        Returns:
            List of QgsField objects with proper data types and precision

        Fields include:
            - Zone identification and calculation parameters
            - Input hydrogeological parameters
            - Zone geometric parameters
            - Well location and geometric properties
            - Metadata
        """
        fields = [
            QgsField("calc_name", FIELD_TYPE_STRING, len=160),
            QgsField("variant", FIELD_TYPE_STRING, len=40),
            # Zone type and calculation parameters
            QgsField("zone_type", FIELD_TYPE_STRING, len=80),
            QgsField("T_tilde", FIELD_TYPE_DOUBLE, len=10, prec=6),
            QgsField("Qo", FIELD_TYPE_DOUBLE, len=15, prec=6),
            QgsField("To", FIELD_TYPE_DOUBLE, len=15, prec=2),

            # Input parameters
            QgsField("k", FIELD_TYPE_DOUBLE, len=10, prec=4),
            QgsField("m", FIELD_TYPE_DOUBLE, len=10, prec=2),
            QgsField("n", FIELD_TYPE_DOUBLE, len=10, prec=4),
            QgsField("Q", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("I", FIELD_TYPE_DOUBLE, len=10, prec=6),
            QgsField("t_years", FIELD_TYPE_DOUBLE, len=10, prec=2),
            QgsField("flow_dir", FIELD_TYPE_DOUBLE, len=10, prec=2),
            QgsField("time_days", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("days_year", FIELD_TYPE_DOUBLE, len=8, prec=2),
            QgsField("flow_case", FIELD_TYPE_STRING, len=32),

            # Zone parameters (can be NULL)
            QgsField("Ls", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("Lu", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("Ydiv", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("R", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("delta", FIELD_TYPE_DOUBLE, len=15, prec=2),

            # Well location
            QgsField("well_x", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("well_y", FIELD_TYPE_DOUBLE, len=15, prec=2),

            # Geometric properties
            QgsField("area_m2", FIELD_TYPE_DOUBLE, len=20, prec=2),
            QgsField("area_ha", FIELD_TYPE_DOUBLE, len=20, prec=6),
            QgsField("area_km2", FIELD_TYPE_DOUBLE, len=20, prec=8),
            QgsField("perimeter_m", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("upstream_m", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("downstream_m", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("length_m", FIELD_TYPE_DOUBLE, len=15, prec=2),
            QgsField("width_m", FIELD_TYPE_DOUBLE, len=15, prec=2),

            # Source and CRS metadata
            QgsField("source_lyr", FIELD_TYPE_STRING, len=120),
            QgsField("crs_authid", FIELD_TYPE_STRING, len=30),
            QgsField("crs_name", FIELD_TYPE_STRING, len=120),

            # Metadata
            QgsField("plugin_ver", FIELD_TYPE_STRING, len=12),
            QgsField("created", FIELD_TYPE_STRING, len=30)
        ]

        return fields

    def get_zone_color(self, zone_type: str) -> Tuple[QColor, QColor]:
        """
        Get appropriate colors for zone type.

        Args:
            zone_type: Zone type string (e.g., "Centric Circle", "Eccentric Circle", "Well in Uniform Flow")

        Returns:
            Tuple of (fill_color, outline_color)
            - fill_color: Semi-transparent fill color
            - outline_color: Fully opaque outline color

        Color scheme:
            - Centric/Eccentric: Blue (well-dominated zones)
            - Well in Uniform Flow: Red/Orange (flow-dominated zones)
        """
        zone_lower = zone_type.lower()

        if 'uniform flow' in zone_lower:
            # Well in Uniform Flow: Red/Orange for flow-dominated
            fill_color = QColor(255, 100, 100, 80)  # Semi-transparent red
            outline_color = QColor(200, 0, 0, 255)   # Dark red
        else:
            # Centric/Eccentric: Blue for well-dominated
            fill_color = QColor(0, 120, 255, 80)    # Semi-transparent blue
            outline_color = QColor(0, 60, 200, 255)  # Dark blue

        return fill_color, outline_color

    def apply_default_style(self, layer: QgsVectorLayer, zone_type: str) -> bool:
        """
        Apply default symbology based on zone type.

        Args:
            layer: QgsVectorLayer to apply styling to
            zone_type: Zone type for color selection

        Returns:
            True if styling applied successfully, False otherwise

        Styling includes:
            - Semi-transparent fill color based on zone type
            - Solid outline in darker shade
            - Professional appearance suitable for reports
        """
        try:
            # Get appropriate colors for zone type
            fill_color, outline_color = self.get_zone_color(zone_type)

            # Create fill symbol
            symbol = QgsFillSymbol.createSimple({
                'color': fill_color.name(),
                'outline_color': outline_color.name(),
                'outline_width': '0.75',
                'outline_style': 'solid',
                'style': 'solid'
            })

            # Set symbol transparency
            symbol.setOpacity(fill_color.alphaF())

            # Apply symbol to layer
            layer.renderer().setSymbol(symbol)
            layer.triggerRepaint()

            self.logger.info(f"Applied {zone_type} styling to layer")
            return True

        except Exception as e:
            self.logger.error(f"Error applying style: {str(e)}")
            return False

    def _ensure_preview_rubber_bands(self, count: int):
        """Create enough reusable polygon rubber bands for the preview."""
        canvas = self.iface.mapCanvas()
        while len(self.preview_rubber_bands) < count:
            band = QgsRubberBand(canvas, QGIS_GEOMETRY_POLYGON)
            band.setZValue(10000 + len(self.preview_rubber_bands))
            band.hide()
            self.preview_rubber_bands.append(band)

    def _style_preview_rubber_band(self, band, time_years: float, order: int):
        """Apply a translucent time-variant style to one preview canvas item."""
        fill_rgba, outline_rgba = self._time_variant_color(time_years)
        fill = QColor(fill_rgba[0], fill_rgba[1], fill_rgba[2], min(fill_rgba[3] + 12, 90))
        outline = QColor(outline_rgba[0], outline_rgba[1], outline_rgba[2], outline_rgba[3])
        band.setFillColor(fill)
        band.setStrokeColor(outline)
        band.setSecondaryStrokeColor(QColor(255, 255, 255, 190))
        band.setWidth(2)
        band.setLineStyle(QT_DASH_LINE)
        band.setZValue(10000 + order)

    def clear_preview(self, immediate: bool = False):
        """Hide the canvas preview without creating or deleting any map layer."""
        del immediate  # Kept for backward-compatible signal connections.
        for band in self.preview_rubber_bands:
            try:
                band.reset(QGIS_GEOMETRY_POLYGON)
                band.hide()
            except RuntimeError:
                # The canvas may already be shutting down during QGIS exit.
                pass

        if hasattr(self, "dlg") and self.dlg:
            self.dlg.set_preview_available(False)

        try:
            self.iface.mapCanvas().refresh()
        except Exception:
            pass

    def show_preview(
        self,
        calculation_result: Dict[str, Any],
        well_layer: QgsVectorLayer,
        input_params: Dict[str, Any],
    ):
        """Draw the capture-zone preview above map layers using canvas rubber bands."""
        language = input_params.get("ui_language", DEFAULT_LANGUAGE)
        self.clear_preview()
        try:
            if not well_layer or not well_layer.isValid():
                raise ValueError(self.ui_text("invalid_layer", language))
            crs = well_layer.crs()
            crs_valid, _, crs_message = self.validate_crs(crs, language)
            if not crs_valid:
                raise ValueError(crs_message)

            enriched = dict(input_params)
            enriched.update({
                "source_layer": well_layer.name(),
                "crs_authid": crs.authid(),
                "crs_name": crs.description(),
            })
            records = self.build_variant_records(calculation_result, enriched, language)
            ordered_records = sorted(
                records,
                key=lambda item: float(item[1].get("t_years", 0.0)),
                reverse=True,
            )
            self._ensure_preview_rubber_bands(len(ordered_records))

            combined_extent = QgsRectangle()
            for order, (geometry, attributes) in enumerate(ordered_records):
                band = self.preview_rubber_bands[order]
                time_years = float(attributes.get("t_years", 0.0))
                self._style_preview_rubber_band(band, time_years, order)
                band.setToGeometry(geometry, crs)
                band.show()
                if combined_extent.isNull():
                    combined_extent = QgsRectangle(geometry.boundingBox())
                else:
                    combined_extent.combineExtentWith(geometry.boundingBox())

            # Any surplus reusable bands remain hidden.
            for band in self.preview_rubber_bands[len(ordered_records):]:
                band.reset(QGIS_GEOMETRY_POLYGON)
                band.hide()

            canvas = self.iface.mapCanvas()
            if not combined_extent.isNull() and not combined_extent.isEmpty():
                canvas.setExtent(combined_extent)
            canvas.refresh()
            if hasattr(self, "dlg") and self.dlg:
                self.dlg.set_preview_available(True)
                self.dlg.set_status(self.ui_text("preview_created", language), "success")
        except Exception as exc:
            self.clear_preview()
            message = self.ui_text("preview_error", language, error=str(exc))
            self.logger.error(message, exc_info=True)
            self.show_message(
                self.ui_text("error_bar_title", language, version=PLUGIN_VERSION),
                message, QGIS_MESSAGE_WARNING,
            )

    def create_capture_zone_layer(
        self,
        geometry: QgsGeometry,
        attributes: Dict[str, Any],
        crs: QgsCoordinateReferenceSystem,
        layer_name: str = "Capture_zone",
        enable_labels: bool = False,
    ) -> Optional[QgsVectorLayer]:
        """Backward-compatible wrapper for a one-feature polygon result layer."""
        try:
            return self.create_result_layer(
                [(geometry, attributes)], crs, layer_name, preview=False
            )
        except Exception as exc:
            self.logger.error(f"Error creating capture zone layer: {exc}", exc_info=True)
            return None

    def create_basic_capture_zone_layer(
        self,
        coordinates: List[Tuple[float, float]],
        crs: QgsCoordinateReferenceSystem,
        layer_name: str = "Capture_zone"
    ) -> Optional[QgsVectorLayer]:
        """
        Create a minimal polygon layer with the calculated geometry.

        This is a simplified version for testing that only creates the zone
        without complex attributes or styling.

        Args:
            coordinates: List of (x, y) tuples forming the polygon
            crs: Coordinate reference system for the layer
            layer_name: Name for the layer

        Returns:
            QgsVectorLayer with the zone, or None if creation fails
        """
        try:
            self.logger.info(f"Creating Ceric–Haitjema analytical layer with {len(coordinates)} points")

            geometry = self.create_qgs_geometry(coordinates)
            if geometry is None or geometry.isNull():
                self.logger.error("Geometry creation returned an empty geometry")
                return None

            # Strict validation: an invalid result must not be silently repaired
            # and saved because that could change the calculated protection zone.
            if not geometry.isGeosValid():
                self.logger.error("capture zone geometry is invalid and will not be saved")
                return None
            if geometry.area() <= 0:
                self.logger.error("capture zone geometry has zero or negative area")
                return None

            self.logger.info(f"Geometry validated: area = {geometry.area():.2f} m²")

            # Create memory layer
            crs_string = crs.authid()
            layer = QgsVectorLayer(
                f"Polygon?crs={crs_string}",
                layer_name,
                "memory"
            )

            if not layer.isValid():
                self.logger.error("Layer is not valid")
                return None

            # Add minimal fields
            provider = layer.dataProvider()
            provider.addAttributes([
                QgsField("name", FIELD_TYPE_STRING),
                QgsField("area_m2", FIELD_TYPE_DOUBLE)
            ])
            layer.updateFields()

            # Create and add feature
            feature = QgsFeature()
            feature.setGeometry(geometry)
            feature.setAttributes([
                "Groundwater capture zone",
                round(geometry.area(), 2)
            ])

            provider.addFeature(feature)
            layer.updateExtents()

            # Apply basic blue styling
            symbol = QgsFillSymbol.createSimple({
                'color': '0,120,255,80',
                'outline_color': '0,60,200,255',
                'outline_width': '0.5'
            })
            layer.renderer().setSymbol(symbol)

            self.logger.info(f"Ceric–Haitjema analytical method layer created successfully: {layer.featureCount()} features")
            return layer

        except Exception as e:
            self.logger.error(f"Error creating Ceric–Haitjema analytical layer: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def _time_variant_color(time_years: float):
        """Return stable RGBA fill/outline colours for standard time variants."""
        palette = {
            1.0: ((255, 215, 0, 65), (190, 140, 0, 255)),
            5.0: ((90, 200, 110, 55), (20, 130, 45, 255)),
            10.0: ((70, 190, 220, 50), (0, 120, 160, 255)),
            25.0: ((55, 120, 235, 45), (15, 65, 180, 255)),
            50.0: ((220, 70, 80, 38), (170, 20, 35, 255)),
        }
        key = float(time_years)
        return palette.get(key, ((120, 120, 220, 45), (60, 60, 160, 255)))

    def apply_time_variant_style(self, layer: QgsVectorLayer, time_values, preview: bool = False):
        """Apply a separate transparent style to every time variant."""
        unique_times = sorted({float(value) for value in time_values})
        if len(unique_times) == 1 and not preview:
            feature = next(layer.getFeatures(), None)
            zone_type = feature["zone_type"] if feature is not None else ""
            self.apply_default_style(layer, str(zone_type))
            layer.setLabelsEnabled(False)
            return

        categories = []
        for time_years in unique_times:
            fill_rgba, outline_rgba = self._time_variant_color(time_years)
            if preview:
                fill_rgba = (fill_rgba[0], fill_rgba[1], fill_rgba[2], min(fill_rgba[3] + 12, 90))
            symbol = QgsFillSymbol.createSimple({
                "color": ",".join(str(v) for v in fill_rgba),
                "outline_color": ",".join(str(v) for v in outline_rgba),
                "outline_width": "1.0" if preview else "0.8",
                "outline_style": "dash" if preview else "solid",
            })
            label = f"{time_years:g} lat / years"
            categories.append(QgsRendererCategory(time_years, symbol, label))
        layer.setRenderer(QgsCategorizedSymbolRenderer("t_years", categories))
        layer.setLabelsEnabled(False)
        layer.triggerRepaint()

    def create_result_layer(self, records, crs, layer_name: str, preview: bool = False):
        """Create one polygon layer containing one or more capture-zone time variants."""
        layer = QgsVectorLayer("Polygon", layer_name, "memory")
        layer.setCrs(crs)
        if not layer.isValid():
            raise ValueError(f"Failed to create result layer: {layer_name}")
        provider = layer.dataProvider()
        provider.addAttributes(self.create_field_list())
        layer.updateFields()

        time_values = []
        ordered_records = sorted(
            records,
            key=lambda item: float(item[1].get("t_years", 0.0)),
            reverse=True,
        )
        for geometry, attributes in ordered_records:
            feature = QgsFeature(layer.fields())
            feature.setGeometry(geometry)
            for key, value in attributes.items():
                index = layer.fields().indexOf(key)
                if index >= 0:
                    feature.setAttribute(index, value)
            if not provider.addFeature(feature):
                raise ValueError(f"Failed to add variant feature: {attributes.get('variant')}")
            time_values.append(attributes.get("t_years", 0.0))
        layer.updateExtents()
        if layer.featureCount() != len(ordered_records):
            raise ValueError("Not all capture-zone variants were added to the result layer")
        self.apply_time_variant_style(layer, time_values, preview=preview)
        layer.setCustomProperty("GEAQUA_Capture_Zones/preview", bool(preview))
        layer.setCustomProperty("GEAQUA_Capture_Zones/version", PLUGIN_VERSION)
        layer.setTitle(f"{WINDOW_TITLE} — {layer_name}")
        return layer

    def build_variant_records(self, calculation_bundle, input_params, language):
        """Convert all calculated variants to validated QGIS geometries and attributes."""
        records = []
        for result in result_variants(calculation_bundle):
            coordinates = result.get("geometry") or []
            if not coordinates:
                raise ValueError(self.ui_text("no_geometry", language))
            geometry = self.create_qgs_geometry(coordinates)
            if geometry is None:
                raise ValueError(self.ui_text("geometry_creation_failed", language))
            valid, geometry, message = self.validate_geometry(geometry, language)
            if not valid or geometry is None:
                raise ValueError(message or self.ui_text("geometry_validation_failed", language))
            variant_params = dict(input_params)
            variant_params["t"] = float(result.get("time_years", input_params.get("t", 0.0)))
            attributes = self.prepare_attributes(result, variant_params, geometry)
            records.append((geometry, attributes))
        if not records:
            raise ValueError(self.ui_text("no_geometry", language))
        return records

    def add_layer_at_top(self, layer: QgsVectorLayer):
        """Register one layer and insert it above all existing project layers."""
        project = QgsProject.instance()
        added = project.addMapLayer(layer, False)
        if added is None:
            raise ValueError(f"Failed to register layer: {layer.name()}")
        project.layerTreeRoot().insertLayer(0, layer)
        return layer

    def process_capture_zone_calculation(
        self,
        calculation_result: Dict[str, Any],
        well_layer: QgsVectorLayer,
        input_params: Dict[str, Any]
    ) -> Tuple[bool, Optional[QgsVectorLayer], Optional[str]]:
        """Create one final polygon layer containing all requested time variants."""
        language = input_params.get("ui_language", DEFAULT_LANGUAGE)
        try:
            self.logger.info(f"Starting GEAQUA Capture Zones v{PLUGIN_VERSION} result processing")
            crs = well_layer.crs()
            crs_valid, _, crs_message = self.validate_crs(crs, language)
            if not crs_valid:
                return False, None, crs_message

            enriched_params = dict(input_params)
            enriched_params.update({
                "source_layer": well_layer.name(),
                "crs_authid": crs.authid(),
                "crs_name": crs.description(),
                "plugin_version": PLUGIN_VERSION,
            })
            records = self.build_variant_records(calculation_result, enriched_params, language)

            requested_name = enriched_params.get("calculation_name") or build_layer_base_name(
                well_layer.name(), enriched_params.get("t", 0)
            )
            base_name = str(requested_name).strip().replace("/", "_").replace("\\", "_") or "Capture_zone"
            existing_names = [item.name() for item in QgsProject.instance().mapLayers().values()]
            layer_name = make_unique_layer_name(base_name, existing_names)

            layer = self.create_result_layer(records, crs, layer_name, preview=False)
            self.add_layer_at_top(layer)
            self.iface.mapCanvas().setExtent(layer.extent())
            self.iface.mapCanvas().refresh()

            preferred_note = (
                self.ui_text("preferred_polish_crs", language)
                if is_preferred_polish_crs(crs.authid())
                else self.ui_text("projected_metric_crs", language)
            )
            success_msg = self.ui_text(
                "success_message", language, layer=layer_name, count=len(records),
                crs=crs.authid(), crs_note=preferred_note, version=PLUGIN_VERSION,
            )
            self.logger.info(success_msg)
            return True, layer, success_msg
        except Exception as e:
            error_msg = self.ui_text("processing_error_detail", language, error=str(e))
            self.logger.error(error_msg, exc_info=True)
            return False, None, error_msg

    # ========================================================================
    # End of Integration Methods
    # ========================================================================

    def generate_report(
        self, report_format: str, calculation_result: Dict[str, Any],
        well_layer: QgsVectorLayer, input_params: Dict[str, Any], calculation_name: str,
    ):
        """Generate a self-contained HTML or PDF report with the current QGIS map."""
        language = input_params.get("ui_language", DEFAULT_LANGUAGE)
        try:
            report_format = str(report_format).lower()
            default_base = sanitize_layer_component(calculation_name or "Capture_zone", fallback="GEAQUA Capture Zones")
            if report_format == "pdf":
                path, _ = QFileDialog.getSaveFileName(
                    self.iface.mainWindow(), self.ui_text("report_pdf_title", language),
                    default_base + ".pdf", "PDF (*.pdf)",
                )
                if path and not path.lower().endswith(".pdf"):
                    path += ".pdf"
            else:
                path, _ = QFileDialog.getSaveFileName(
                    self.iface.mainWindow(), self.ui_text("report_html_title", language),
                    default_base + ".html", "HTML (*.html *.htm)",
                )
                if path and not path.lower().endswith((".html", ".htm")):
                    path += ".html"
            if not path:
                return

            fd, map_path = tempfile.mkstemp(prefix="geaqua_capture_zones_map_", suffix=".png")
            os.close(fd)
            try:
                QApplication.processEvents()
                self.iface.mapCanvas().saveAsImage(map_path)
                QApplication.processEvents()
                map_data_uri = ""
                if os.path.exists(map_path) and os.path.getsize(map_path) > 0:
                    if report_format == "pdf":
                        # QTextDocument loads local files more reliably than
                        # base64 data URIs when printing through QPrinter.
                        map_data_uri = QUrl.fromLocalFile(map_path).toString()
                    else:
                        with open(map_path, "rb") as handle:
                            encoded = base64.b64encode(handle.read()).decode("ascii")
                        map_data_uri = "data:image/png;base64," + encoded

                warnings = []
                variants = result_variants(calculation_result)
                for result in variants:
                    if result.get("scale_warning"):
                        warnings.append(self.ui_text("large_zone_report_warning", language))
                        break
                if any(result.get("lu_approximation_warning") for result in variants):
                    warnings.append(self.ui_text("lu_approximation_report_warning", language))
                html_text = build_report_html(
                    calculation_name or default_base, input_params, calculation_result,
                    language=language, map_data_uri=map_data_uri, warnings=warnings,
                )

                if report_format == "pdf":
                    printer = QPrinter(QPRINTER_HIGH_RESOLUTION)
                    printer.setOutputFormat(QPRINTER_PDF_FORMAT)
                    printer.setOutputFileName(path)
                    document = QTextDocument()
                    document.setHtml(html_text)
                    (getattr(document, "print_", None) or getattr(document, "print"))(printer)
                    if not os.path.exists(path) or os.path.getsize(path) == 0:
                        raise ValueError("PDF output was not created")
                else:
                    with open(path, "w", encoding="utf-8", newline="\n") as handle:
                        handle.write(html_text)
            finally:
                try:
                    os.remove(map_path)
                except OSError:
                    pass

            message = self.ui_text("report_saved", language, path=path)
            if hasattr(self, "dlg") and self.dlg:
                self.dlg.set_status(message, "success")
            self.show_message(self.ui_text("success_title", language, version=PLUGIN_VERSION), message, QGIS_MESSAGE_SUCCESS)
        except Exception as exc:
            message = self.ui_text("report_error", language, error=str(exc))
            self.logger.error(message, exc_info=True)
            self.show_message(self.ui_text("error_bar_title", language, version=PLUGIN_VERSION), message, QGIS_MESSAGE_CRITICAL)

    def _dialog_is_alive(self):
        """Return True when the Python wrapper still owns a valid Qt dialog."""
        dialog = getattr(self, "dlg", None)
        if dialog is None:
            return False
        try:
            # Calling a harmless QObject/QWidget method detects a wrapper whose
            # underlying C++ object has already been deleted.
            dialog.isVisible()
            return True
        except (RuntimeError, AttributeError):
            self.dlg = None
            return False

    def _on_dialog_destroyed(self, destroyed_dialog=None):
        """Forget only the dialog instance which Qt has actually destroyed."""
        current_dialog = getattr(self, "dlg", None)
        if current_dialog is None:
            return
        # A stale dialog may emit destroyed after a replacement has already
        # been created.  Do not clear the reference to the new window.
        if destroyed_dialog is None or current_dialog is destroyed_dialog:
            self.dlg = None

    def _initialize_dialog(self):
        """Create the reusable modeless dialog and connect its signals once."""
        self.dlg = CaptureZoneDialog(self.iface.mainWindow())
        self.dlg.setModal(False)
        self.dlg.setWindowModality(QT_NON_MODAL)
        self.dlg.previewRequested.connect(self.show_preview)
        self.dlg.clearPreviewRequested.connect(self.clear_preview)
        self.dlg.reportRequested.connect(self.generate_report)
        self.dlg.accepted.connect(self._on_dialog_accepted)
        self.dlg.rejected.connect(self._on_dialog_rejected)
        self.dlg.destroyed.connect(self._on_dialog_destroyed)

    def _on_dialog_rejected(self):
        """Clear only canvas preview items after closing the modeless dialog."""
        self.clear_preview()

    def _on_dialog_accepted(self):
        """Create the final capture-zone layer after the modeless dialog is accepted."""
        language = self.dlg.get_language()
        try:
            calculation_result = self.dlg.get_calculation_result()
            if not calculation_result:
                self.show_message(
                    self.ui_text("no_result_title", language),
                    self.ui_text("no_result_message", language),
                    QGIS_MESSAGE_WARNING,
                )
                return

            well_layer = self.dlg.get_cached_layer()
            if not well_layer:
                self.show_message(
                    self.ui_text("no_layer_title", language),
                    self.ui_text("no_layer_message", language),
                    QGIS_MESSAGE_WARNING,
                )
                return

            input_params = self.dlg.get_cached_parameters()
            if not input_params:
                self.show_message(
                    self.ui_text("no_parameters_title", language),
                    self.ui_text("no_parameters_message", language),
                    QGIS_MESSAGE_WARNING,
                )
                return

            success, layer, message = self.process_capture_zone_calculation(
                calculation_result,
                well_layer,
                input_params,
            )

            if success:
                self.show_message(
                    self.ui_text("success_title", language, version=PLUGIN_VERSION),
                    message,
                    QGIS_MESSAGE_SUCCESS,
                )
                self.logger.info(f"Capture-zone layer created: {layer.name()}")
            else:
                self.show_message(
                    self.ui_text("error_bar_title", language, version=PLUGIN_VERSION),
                    message,
                    QGIS_MESSAGE_CRITICAL,
                )
                self.logger.error(f"Capture-zone creation failed: {message}")

        except Exception as e:
            error_msg = self.ui_text("processing_error", language, error=str(e))
            self.logger.error(error_msg, exc_info=True)
            self.show_message(
                self.ui_text("error_title", language),
                error_msg,
                QGIS_MESSAGE_CRITICAL,
            )
        finally:
            self.clear_preview()

    def run(self):
        """Show the reusable modeless dialog without blocking the QGIS map."""

        # Do not rely solely on first_start.  During plugin reloads or after Qt
        # destroys a window, first_start can be False while no valid dialog
        # exists.  Recreate it whenever the wrapper is missing or stale.
        if not self._dialog_is_alive():
            self._initialize_dialog()
        self.first_start = False

        try:
            if self.dlg.isVisible():
                self.dlg.raise_()
                self.dlg.activateWindow()
                return

            self.dlg.prepare_for_run()
            self.dlg.setModal(False)
            self.dlg.setWindowModality(QT_NON_MODAL)
            self.dlg.show()
            self.dlg.raise_()
            self.dlg.activateWindow()
        except RuntimeError:
            # One last recovery path for a dialog deleted between the validity
            # check and use (possible during rapid plugin reloads).
            self.dlg = None
            self._initialize_dialog()
            self.dlg.prepare_for_run()
            self.dlg.show()
            self.dlg.raise_()
            self.dlg.activateWindow()

    def show_message(self, title: str, message: str, level=None):
        """
        Show a message to the user in the QGIS message bar.

        Args:
            title: Message title
            message: Message content
            level: QGIS message level.
        """
        if level is None:
            level = QGIS_MESSAGE_INFO
        self.iface.messageBar().pushMessage(title, message, level=level, duration=5)
