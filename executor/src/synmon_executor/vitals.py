"""Web Vitals capture helpers: JS injection script + snapshot normalization."""

from __future__ import annotations

from pathlib import Path

from synmon_contract.models import Vitals

# Vendored inside the package so it ships with the installed wheel (hatchling includes data
# files under the package dir). Resolve relative to this module, NOT the source tree.
_VENDOR = Path(__file__).resolve().parent / "vendor" / "web-vitals.iife.js"

# Registers the latest value of each metric into window.__synmon_vitals (reportAllChanges).
# The vendored IIFE declares `var webVitals = ...`; under Playwright's add_init_script that
# top-level `var` is NOT exposed on `window`, so we reference the in-scope `webVitals` (same
# concatenated script) and fall back to `window.webVitals` if a runtime exposes it globally.
_BOOTSTRAP = """
(() => {
  window.__synmon_vitals = window.__synmon_vitals || {};
  const wv = (typeof webVitals !== "undefined" && webVitals)
    || (typeof window !== "undefined" && window.webVitals);
  if (!wv) return;
  const put = (m) => { window.__synmon_vitals[m.name] = m.value; };
  const opt = { reportAllChanges: true };
  wv.onLCP(put, opt); wv.onCLS(put, opt); wv.onINP(put, opt);
  wv.onFCP(put, opt); wv.onTTFB(put, opt);
})();
"""

_KEY_MAP = {"LCP": "lcp_ms", "FCP": "fcp_ms", "TTFB": "ttfb_ms", "INP": "inp_ms", "CLS": "cls"}


def load_vendored_lib() -> str:
    return _VENDOR.read_text()


def build_init_script(lib_js: str) -> str:
    return f"{lib_js}\n{_BOOTSTRAP}"


def to_vitals(snapshot: dict | None) -> Vitals | None:
    if not snapshot:
        return None
    fields = {
        dest: snapshot[src] for src, dest in _KEY_MAP.items() if snapshot.get(src) is not None
    }
    if not fields:
        return None
    return Vitals(**fields)
