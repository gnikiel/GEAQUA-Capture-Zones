# -*- coding: utf-8 -*-
"""Portable JSON, summaries and HTML reports for capture-zone calculations."""

from __future__ import annotations

import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .plugin_utils import DAYS_PER_YEAR, polygon_area, zone_dimensions
from .translations import zone_display_name
from .version import PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_AUTHORS

SCHEMA_NAME = "geaqua_capture_zones_project"
SCHEMA_VERSION = 1


def result_variants(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return calculation results as a non-empty list of time variants."""
    if not isinstance(bundle, dict):
        return []
    variants = bundle.get("variants")
    if isinstance(variants, list):
        return [item for item in variants if isinstance(item, dict)]
    if bundle.get("geometry"):
        return [bundle]
    return []


def primary_result(bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return the preferred result (25-year variant when present)."""
    variants = result_variants(bundle)
    if not variants:
        return None
    for result in variants:
        if abs(float(result.get("time_years", -999.0)) - 25.0) < 1e-9:
            return result
    return variants[-1]


def _json_safe(value: Any) -> Any:
    """Convert values to strict, portable JSON without NaN or Infinity."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def build_document(
    calculation_name: str,
    input_params: Dict[str, Any],
    calculation_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the stable JSON document stored by the plugin."""
    return {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "plugin": PLUGIN_NAME,
        "plugin_version": PLUGIN_VERSION,
        "plugin_authors": PLUGIN_AUTHORS,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "calculation_name": str(calculation_name or "").strip(),
        "source": {
            "layer_name": input_params.get("source_layer", ""),
            "layer_id": input_params.get("source_layer_id", ""),
            "crs_authid": input_params.get("crs_authid", ""),
            "crs_name": input_params.get("crs_name", ""),
            "well_x": input_params.get("well_x"),
            "well_y": input_params.get("well_y"),
            "well_attributes": _json_safe(input_params.get("well_attributes", {})),
        },
        "input_parameters": _json_safe(input_params),
        "calculation": _json_safe(calculation_bundle),
    }


def save_document(path: str, document: Dict[str, Any]) -> None:
    """Write a calculation JSON file using UTF-8 and deterministic indentation."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def load_document(path: str) -> Dict[str, Any]:
    """Read and validate a capture-zone calculation JSON file."""
    with Path(path).open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict):
        raise ValueError("Project file root must be an object")
    if document.get("schema") != SCHEMA_NAME:
        raise ValueError("The selected file is not a GEAQUA Capture Zones project")
    if int(document.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("Unsupported GEAQUA Capture Zones project schema version")
    if not isinstance(document.get("input_parameters"), dict):
        raise ValueError("The project file does not contain input parameters")
    calculation = document.get("calculation")
    if calculation is not None and not isinstance(calculation, dict):
        raise ValueError("The project calculation section is invalid")
    return document


def _num(value: Any, decimals: int = 2, empty: str = "—") -> str:
    if value is None:
        return empty
    try:
        numeric = float(value)
        if math.isinf(numeric):
            return "∞"
        if math.isnan(numeric):
            return empty
        return f"{numeric:,.{decimals}f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def build_summary_text(
    calculation_name: str,
    input_params: Dict[str, Any],
    calculation_bundle: Dict[str, Any],
    language: str = "pl",
) -> str:
    """Create a readable clipboard/result-panel summary."""
    pl = language != "en"
    variants = result_variants(calculation_bundle)
    heading = "WYNIKI OBLICZEŃ STREFY DOPŁYWU" if pl else "CAPTURE-ZONE CALCULATION RESULTS"
    lines = [heading, "=" * len(heading)]
    lines.append(("Nazwa obliczenia: " if pl else "Calculation name: ") + calculation_name)
    lines.append(("Warstwa studni: " if pl else "Well layer: ") + str(input_params.get("source_layer", "")))
    lines.append(("CRS: " if pl else "CRS: ") + str(input_params.get("crs_authid", "")))
    lines.append(
        ("Współrzędne studni: " if pl else "Well coordinates: ")
        + f"X={_num(input_params.get('well_x'), 2)}, Y={_num(input_params.get('well_y'), 2)}"
    )
    well_attributes = input_params.get("well_attributes") or {}
    if isinstance(well_attributes, dict) and well_attributes:
        lines.append("Dane studni:" if pl else "Well attributes:")
        for key, value in well_attributes.items():
            lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("PARAMETRY" if pl else "PARAMETERS")
    zero_flow = abs(float(input_params.get("I", 0.0) or 0.0)) <= 1e-15
    direction_text = ("nie dotyczy (I = 0)" if pl else "not applicable (I = 0)") if zero_flow else f"{_num(input_params.get('flow_direction'), 2)}°"
    lines.append(
        f"k={_num(input_params.get('k'), 4)} m/d; m={_num(input_params.get('m'), 2)} m; "
        f"n={_num(input_params.get('n'), 4)}; Q={_num(input_params.get('Q'), 2)} m³/d; "
        f"I={_num(input_params.get('I'), 6)}; "
        + ("azymut kierunku przepływu=" if pl else "flow-direction azimuth=")
        + direction_text
    )
    lines.append("")
    lines.append("WARIANTY" if pl else "VARIANTS")
    for result in variants:
        dims = zone_dimensions(result, input_params)
        area_m2 = polygon_area(result.get("geometry") or [])
        time_years = float(result.get("time_years", input_params.get("t", 0.0)))
        zone_name = zone_display_name(result.get("zone_type", ""), language)
        lines.append(
            f"{_num(time_years, 2)} " + ("lat" if pl else "years") + f" — {zone_name}; "
            + (("góra=" if pl else "upstream=") + f"{_num(dims['upstream_m'], 2)} m; ")
            + (("dół=" if pl else "downstream=") + f"{_num(dims['downstream_m'], 2)} m; ")
            + (("szerokość=" if pl else "width=") + f"{_num(dims['width_m'], 2)} m; ")
            + (("powierzchnia=" if pl else "area=") + f"{_num(area_m2 / 10000.0, 4)} ha / {_num(area_m2 / 1_000_000.0, 6)} km²")
        )
    return "\n".join(lines)


def _table_row(label: str, value: str) -> str:
    return f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"


def build_report_html(
    calculation_name: str,
    input_params: Dict[str, Any],
    calculation_bundle: Dict[str, Any],
    language: str = "pl",
    map_data_uri: str = "",
    warnings: Optional[Iterable[str]] = None,
) -> str:
    """Build a self-contained printable HTML report."""
    pl = language != "en"
    variants = result_variants(calculation_bundle)
    title = "Raport z obliczeń strefy dopływu" if pl else "Capture-Zone Calculation Report"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    zero_flow = abs(float(input_params.get("I", 0.0) or 0.0)) <= 1e-15
    direction_value = (
        "nie dotyczy — I = 0" if pl else "not applicable — I = 0"
    ) if zero_flow else _num(input_params.get("flow_direction"), 2) + "°"
    parameter_rows = "".join([
        _table_row("k [m/d]", _num(input_params.get("k"), 4)),
        _table_row("m / H [m]", _num(input_params.get("m"), 2)),
        _table_row("n [-]", _num(input_params.get("n"), 4)),
        _table_row("Q [m³/d]", _num(input_params.get("Q"), 2)),
        _table_row("I / i [-]", _num(input_params.get("I"), 6)),
        _table_row("Azymut kierunku przepływu" if pl else "Flow-direction azimuth", direction_value),
        _table_row("Przelicznik czasu" if pl else "Time conversion", f"1 {'rok' if pl else 'year'} = {DAYS_PER_YEAR:g} d"),
    ])

    well_attributes = input_params.get("well_attributes") or {}
    well_attribute_rows = ""
    if isinstance(well_attributes, dict):
        well_attribute_rows = "".join(
            _table_row(str(key), str(value))
            for key, value in well_attributes.items()
            if value is not None
        )

    variant_rows = []
    intermediate_rows = []
    for result in variants:
        dims = zone_dimensions(result, input_params)
        area_m2 = polygon_area(result.get("geometry") or [])
        time_years = float(result.get("time_years", input_params.get("t", 0.0)))
        variant_rows.append(
            "<tr>"
            f"<td>{_num(time_years, 2)}</td>"
            f"<td>{html.escape(zone_display_name(result.get('zone_type', ''), language))}</td>"
            f"<td>{_num(result.get('T_dimensionless'), 4)}</td>"
            f"<td>{_num(result.get('Qo'), 6)}</td>"
            f"<td>{'∞' if result.get('reference_time_infinite') else _num(result.get('To'), 2)}</td>"
            f"<td>{_num(dims['upstream_m'], 2)}</td>"
            f"<td>{_num(dims['downstream_m'], 2)}</td>"
            f"<td>{_num(dims['width_m'], 2)}</td>"
            f"<td>{_num(area_m2 / 10000.0, 4)}</td>"
            f"<td>{_num(area_m2 / 1_000_000.0, 6)}</td>"
            "</tr>"
        )
        intermediate_rows.append(
            "<tr>"
            f"<td>{_num(time_years, 2)}</td>"
            f"<td>{_num(result.get('Ls'), 2)}</td>"
            f"<td>{_num(result.get('Lu'), 2)}</td>"
            f"<td>{_num(result.get('Ydiv'), 2)}</td>"
            f"<td>{_num(result.get('R'), 2)}</td>"
            f"<td>{_num(result.get('delta'), 2)}</td>"
            "</tr>"
        )

    warning_messages = [str(item) for item in (warnings or [])]
    if any(result.get("lu_approximation_warning") for result in variants):
        warning_messages.append(
            "Dla co najmniej jednego wariantu T̃ > 2,85. Przybliżenie Lu z równania (18) może nieznacznie zaniżać zasięg po stronie dopływu i nie jest w tym zakresie ściśle konserwatywne (Ceric i Haitjema, 2005)."
            if pl else
            "At least one variant has T̃ > 2.85. The Equation (18) approximation for Lu may slightly underestimate the upstream extent and is not strictly conservative in this range (Ceric and Haitjema, 2005)."
        )
    warning_items = "".join(f"<li>{html.escape(item)}</li>" for item in warning_messages)
    if not warning_items:
        warning_items = "<li>Brak ostrzeżeń automatycznych.</li>" if pl else "<li>No automatic warnings.</li>"

    map_block = ""
    if map_data_uri:
        map_block = f'<h2>{"Mapa" if pl else "Map"}</h2><img class="map" src="{map_data_uri}" alt="capture zone map">'

    equations = (
        "<p><b>Q₀ = k · i · H</b> — Ceric i Haitjema (2005), równanie (1).</p>"
        "<p><b>T₀ = n · H · Q / (2π · Q₀²)</b> — równanie (6); dla Q₀ = 0: T₀ → ∞.</p>"
        f"<p><b>T̃ = T / T₀</b> — równanie (5), przy czym 1 rok = {DAYS_PER_YEAR:g} d; dla Q₀ = 0: T̃ = 0.</p>"
        "<p><b>T̃ ≤ 0,1:</b> R = 1,1543 · √[Q · T / (π · H · n)] — równanie (14).</p>"
        "<p><b>0,1 &lt; T̃ ≤ 1:</b> R = Ls · [1,161 + ln(0,39 + T̃)], "
        "Ls = Q/(2πQ₀), δ = Ls · [0,00278 + 0,652T̃] — równania (4), (16) i (17).</p>"
        "<p><b>T̃ &gt; 1:</b> x/Ls = (y/Ls)/tan(y/Ls), "
        "Lu = Ls · [T̃ + ln(T̃ + e)] — równania (7) i (18).</p>"
        "<p><i>Kierunek regionalnego przepływu wód podziemnych podaje się jako azymut liczony zgodnie z ruchem wskazówek zegara od północy: "
        "0° — północ, 90° — wschód, 180° — południe, 270° — zachód.</i></p>"
        if pl else
        "<p><b>Q₀ = k · i · H</b> — Ceric and Haitjema (2005), Equation (1).</p>"
        "<p><b>T₀ = n · H · Q / (2π · Q₀²)</b> — Equation (6); for Q₀ = 0: T₀ → ∞.</p>"
        f"<p><b>T̃ = T / T₀</b> — Equation (5), using 1 year = {DAYS_PER_YEAR:g} d; for Q₀ = 0: T̃ = 0.</p>"
        "<p><b>T̃ ≤ 0.1:</b> R = 1.1543 · √[Q · T / (π · H · n)] — Equation (14).</p>"
        "<p><b>0.1 &lt; T̃ ≤ 1:</b> R = Ls · [1.161 + ln(0.39 + T̃)], "
        "Ls = Q/(2πQ₀), δ = Ls · [0.00278 + 0.652T̃] — Equations (4), (16) and (17).</p>"
        "<p><b>T̃ &gt; 1:</b> x/Ls = (y/Ls)/tan(y/Ls), "
        "Lu = Ls · [T̃ + ln(T̃ + e)] — Equations (7) and (18).</p>"
        "<p><i>Regional groundwater-flow direction is entered as an azimuth measured clockwise from North: "
        "0° — North, 90° — East, 180° — South, 270° — West.</i></p>"
    )

    limitations = (
        "Metoda zakłada pojedynczą studnię w pełni ujmującą warstwę wodonośną i pompującą ze stałą wydajnością, warstwę jednorodną i izotropową, "
        "poziomy przepływ zgodny z założeniem Dupuita oraz brak dyspersji. Przepływ regionalny jest jednorodny albo zerowy. "
        "Nie uwzględnia lokalnego zasilania, przecieków, granic hydrodynamicznych, retencji, sorpcji ani współdziałania wielu studni. "
        "Dla T̃ > 2,85 przybliżenie Lu z równania (18) może nieznacznie zaniżać zasięg po stronie dopływu. "
        "Obliczona strefa dopływu nie jest automatycznie prawną strefą ochronną i wymaga hydrogeologicznej oceny przydatności modelu koncepcyjnego."
        if pl else
        "The method assumes one fully penetrating well pumping at a constant rate, a homogeneous and isotropic aquifer, steady uniform "
        "horizontal flow under the Dupuit assumption, and no hydrodynamic dispersion. Ambient flow is uniform or zero. It does not represent "
        "local recharge, leakage, hydrodynamic boundaries, storage, sorption or interacting wells. "
        "For T̃ > 2.85, the Equation (18) approximation for Lu may slightly underestimate the upstream extent. "
        "A calculated capture zone is not automatically a legally designated protection area and requires hydrogeological review of the conceptual-model applicability."
    )

    sources_html = (
        "<ul>"
        "<li><b>Ceric, A. i Haitjema, H. (2005)</b>, <i>On Using Simple Time-of-Travel Capture Zone Delineation Methods</i>, "
        "Ground Water 43(3), 408–412, DOI: 10.1111/j.1745-6584.2005.0035.x — główne źródło progów klasyfikacji, "
        "współczynników i wzorów aproksymacyjnych.</li>"
        "<li><b>Grubb, S. (1993)</b>, <i>Analytical Model for Estimation of Steady-State Capture Zones of Pumping Wells in Confined and Unconfined Aquifers</i>, "
        "Ground Water 31(1), 27–32 — punkt stagnacji, granica dopływu i linia rozdziału.</li>"
        "<li><b>Bear, J. i Jacobs, M. (1965)</b>, <i>On the movement of water bodies injected into aquifers</i>, "
        "Journal of Hydrology 3, 37–57 — rozwiązanie bazowe dla izochron w jednorodnym przepływie.</li>"
        "</ul>"
        if pl else
        "<ul>"
        "<li><b>Ceric, A. and Haitjema, H. (2005)</b>, <i>On Using Simple Time-of-Travel Capture Zone Delineation Methods</i>, "
        "Ground Water 43(3), 408–412, DOI: 10.1111/j.1745-6584.2005.0035.x — primary source of the classification thresholds, "
        "coefficients and approximation equations.</li>"
        "<li><b>Grubb, S. (1993)</b>, <i>Analytical Model for Estimation of Steady-State Capture Zones of Pumping Wells in Confined and Unconfined Aquifers</i>, "
        "Ground Water 31(1), 27–32 — stagnation point, upgradient divide and dividing streamline.</li>"
        "<li><b>Bear, J. and Jacobs, M. (1965)</b>, <i>On the movement of water bodies injected into aquifers</i>, "
        "Journal of Hydrology 3, 37–57 — underlying uniform-flow isochrone solution.</li>"
        "</ul>"
    )

    return f"""<!DOCTYPE html>
<html lang="{'pl' if pl else 'en'}">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} — {html.escape(calculation_name)}</title>
<style>
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: Arial, sans-serif; color: #222; font-size: 10pt; line-height: 1.35; }}
h1 {{ font-size: 20pt; margin-bottom: 3mm; }}
h2 {{ font-size: 13pt; margin-top: 7mm; border-bottom: 1px solid #777; padding-bottom: 1mm; }}
table {{ border-collapse: collapse; width: 100%; margin: 3mm 0; }}
th, td {{ border: 1px solid #aaa; padding: 1.6mm; vertical-align: top; }}
th {{ background: #eee; text-align: left; }}
.meta th {{ width: 34%; }}
.map {{ display: block; max-width: 100%; max-height: 155mm; margin: 3mm auto; border: 1px solid #888; }}
.note {{ background: #fff7d6; border: 1px solid #d5b54a; padding: 3mm; }}
.footer {{ margin-top: 8mm; color: #666; font-size: 8.5pt; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<table class="meta">
{_table_row('Nazwa obliczenia' if pl else 'Calculation name', calculation_name)}
{_table_row('Warstwa studni' if pl else 'Well layer', str(input_params.get('source_layer', '')))}
{_table_row('CRS', f"{input_params.get('crs_authid', '')} — {input_params.get('crs_name', '')}")}
{_table_row('Współrzędne studni' if pl else 'Well coordinates', f"X={_num(input_params.get('well_x'), 2)}, Y={_num(input_params.get('well_y'), 2)}")}
{_table_row('Data raportu' if pl else 'Report date', generated)}
{_table_row('Wersja programu' if pl else 'Plugin version', f'{PLUGIN_NAME} v{PLUGIN_VERSION}')}
{_table_row('Autorzy' if pl else 'Authors', PLUGIN_AUTHORS)}
</table>
{(('<h2>' + ('Dane studni' if pl else 'Well data') + '</h2><table class="meta">' + well_attribute_rows + '</table>') if well_attribute_rows else '')}
<h2>{'Parametry wejściowe' if pl else 'Input parameters'}</h2>
<table class="meta">{parameter_rows}</table>
<h2>{'Zastosowane równania' if pl else 'Equations'}</h2>
{equations}
<h2>{'Wyniki i wymiary stref' if pl else 'Results and zone dimensions'}</h2>
<table>
<thead><tr>
<th>t [{"lat" if pl else "years"}]</th><th>{'Typ strefy' if pl else 'Zone type'}</th><th>T̃</th><th>Qo [m²/d]</th><th>T₀ [d]</th>
<th>{'W górę [m]' if pl else 'Upstream [m]'}</th><th>{'W dół [m]' if pl else 'Downstream [m]'}</th>
<th>{'Szerokość [m]' if pl else 'Width [m]'}</th><th>ha</th><th>km²</th>
</tr></thead><tbody>{''.join(variant_rows)}</tbody>
</table>
<h2>{'Wyniki pośrednie geometrii' if pl else 'Intermediate geometry results'}</h2>
<table><thead><tr><th>t [{"lat" if pl else "years"}]</th><th>Ls [m]</th><th>Lu [m]</th><th>{'Ydiv — asymptotyczna półszerokość [m]' if pl else 'Ydiv — asymptotic half-width [m]'}</th><th>R [m]</th><th>δ [m]</th></tr></thead>
<tbody>{''.join(intermediate_rows)}</tbody></table>
{map_block}
<h2>{'Podstawy metodyczne i źródła' if pl else 'Methodological basis and sources'}</h2>
{sources_html}
<h2>{'Ostrzeżenia' if pl else 'Warnings'}</h2><div class="note"><ul>{warning_items}</ul></div>
<h2>{'Ograniczenia metody' if pl else 'Method limitations'}</h2><p>{html.escape(limitations)}</p>
<p class="footer">{PLUGIN_NAME} v{PLUGIN_VERSION} — {html.escape(PLUGIN_AUTHORS)} — {generated}</p>
</body></html>"""
