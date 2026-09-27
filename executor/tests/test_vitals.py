from pathlib import Path

from synmon_contract.models import Vitals
from synmon_executor import vitals


def test_to_vitals_maps_js_keys():
    v = vitals.to_vitals({"LCP": 1234.5, "CLS": 0.05, "INP": 180.0, "FCP": 900.0, "TTFB": 200.0})
    assert isinstance(v, Vitals)
    assert v.lcp_ms == 1234.5 and v.cls == 0.05 and v.inp_ms == 180.0
    assert v.fcp_ms == 900.0 and v.ttfb_ms == 200.0


def test_to_vitals_handles_empty_and_none():
    assert vitals.to_vitals(None) is None
    assert vitals.to_vitals({}) is None
    # partial snapshot is fine
    v = vitals.to_vitals({"LCP": 1.0})
    assert v is not None and v.lcp_ms == 1.0 and v.inp_ms is None


def test_build_init_script_embeds_lib_and_bootstrap():
    script = vitals.build_init_script("/*LIBJS*/")
    assert "/*LIBJS*/" in script
    assert "__synmon_vitals" in script
    assert "onLCP" in script and "onCLS" in script and "onINP" in script


def test_vendored_lib_is_inside_the_package_so_it_ships_when_installed():
    # Regression: the asset must live UNDER the package dir (next to vitals.py), not in the source
    # tree's executor/vendor/, or it is missing from the pip-installed wheel and injection fails.
    asset = Path(vitals.__file__).resolve().parent / "vendor" / "web-vitals.iife.js"
    assert asset.is_file(), f"vendored web-vitals must be packaged at {asset}"
    text = vitals.load_vendored_lib()
    assert "onLCP" in text and "onCLS" in text


def test_bootstrap_uses_in_scope_webvitals_not_only_window():
    # Under add_init_script the IIFE's `var webVitals` is not exposed on window; the bootstrap must
    # reference the in-scope `webVitals` (with a window fallback), or it bails and captures nothing.
    script = vitals.build_init_script("/*LIBJS*/")
    assert "typeof webVitals" in script
