"""scripts/check_commits.py: the Conventional Commits rules releases are derived from."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_commits.py"


def _load():
    spec = importlib.util.spec_from_file_location("synmon_check_commits", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = _load()


@pytest.mark.parametrize(
    "subject",
    [
        "fix(ci): drop the approve step from the Dependabot auto-merge job (#6)",
        "build(deps): Bump the minor-and-patch group with 3 updates (#5)",
        "feat: per-step screenshots",
        "feat(executor)!: drop Python 3.11",
        "chore(release): v1.3.0",
        "docs(deploy/README.md): fix typo",
        "Merge branch 'main' into feature",
        "Merge remote-tracking branch 'origin/main'",
        "Merge pull request #12 from fxkraus/feature",
        'Revert "feat: per-step screenshots"',
    ],
)
def test_accepts_conventional_and_generated_subjects(subject):
    assert cc.problem(subject) is None


@pytest.mark.parametrize(
    "subject",
    [
        "Initial public release",
        "fixed the thing",
        "feature: new",
        "fix:no space",
        "fix: ",
        "fix(): empty scope",
        "Fix: capitalised type",
        "feat: " + "x" * 100,
        "Merge new login flow",
        "Merge stuff",
        "Revert",
    ],
)
def test_rejects_other_subjects(subject):
    assert cc.problem(subject) is not None


def test_message_file_ignores_comments_and_blank_lines(tmp_path):
    msg = tmp_path / "COMMIT_EDITMSG"
    msg.write_text("\n# Please enter the commit message\nfeat: x\n\nbody\n", encoding="utf-8")
    assert cc.main(["--message-file", str(msg)]) == 0
    msg.write_text("# only comments\nwip\n", encoding="utf-8")
    assert cc.main(["--message-file", str(msg)]) == 1


def test_title_and_range(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q"], check=True)
    for subject in ("base", "fix: a", "oops"):
        subprocess.run(["git", *ident, "commit", "-q", "--allow-empty", "-m", subject], check=True)

    assert cc.main(["--title", "fix: ok", "--range", "HEAD~2..HEAD~1"]) == 0
    assert cc.main(["--title", "fix: ok", "--range", "HEAD~2..HEAD"]) == 1
    assert "'oops'" in capsys.readouterr().err
    assert cc.main(["--title", "bad title"]) == 1


def test_generated_forms_are_not_accepted_as_pr_title():
    # A squash merge uses the PR title as subject: it must be a Conventional Commit.
    assert cc.main(["--title", "Merge branch 'main' into feature"]) == 1
    assert cc.main(["--title", 'Revert "feat: x"']) == 1
