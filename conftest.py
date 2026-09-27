import os

# The live browser test needs Playwright + a running mock site; only collect it when the
# integration job explicitly opts in. The dedicated CI job sets SYNMON_INTEGRATION=1.
collect_ignore_glob: list[str] = []
if not os.environ.get("SYNMON_INTEGRATION"):
    collect_ignore_glob.append("tests/integration/test_journeys_live.py")

# Plug-in loading tests need the Checkmk libraries; tests/checkmk/run-pytest.sh sets this inside
# a Checkmk image.
if not os.environ.get("SYNMON_CHECKMK"):
    collect_ignore_glob.append("tests/checkmk/*")
