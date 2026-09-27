import sys
from pathlib import Path

# Put the MKP staging root on sys.path so `import cmk_addons.plugins.synmon.lib.*`
# resolves via PEP-420 namespace packages, exactly as it does inside a Checkmk site.
MKP_ROOT = Path(__file__).resolve().parents[2] / "checkmk_mkp"
if str(MKP_ROOT) not in sys.path:
    sys.path.insert(0, str(MKP_ROOT))
