"""A program planted where a PATH entry reaches a working folder never runs.

safe_spawn 1.0.0 skipped only relative PATH entries. An absolute entry could
still reach the folder a child works in: an entry naming that folder or a folder
below it, a junction or symlink to it, or on Windows a quoted entry that cmd.exe
reads as that folder. A drive-relative name such as ``C:claude`` named a file in
the current folder of drive C:. Each test goes through one of relay's own call
sites: a CLI tier (``endpoints``), the doctor's CLI rows (``cli_tiers``), the
``git`` that ``--auto-commit`` runs (``local_git``), and the environment every
shell child gets (``child_env``). On 0.4.0 each one fails because the planted
program ran or won the lookup. Real processes run against local stand-ins; no
model is reached.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest
from cli_stand_in import SYSTEM32, WINDOWS, plant_binary, plant_script, stand_in

import relay.local_mcp as m
from relay._vendor import safe_spawn
from relay.bisect import _default_runner
from relay.child_env import shell_env
from relay.endpoints import BackendError, CliBackend, build_endpoints
from relay.local_git import GitRepo
from relay.local_loop import _run_acceptance
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate
from relay.mcp_grants import StartGrants

GIT = shutil.which("git")
SYSTEM_PATH = [SYSTEM32] if WINDOWS else ["/usr/bin", "/bin"]
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows path semantics")
_MSG = [{"role": "user", "content": "hi"}]


def _path(monkeypatch, *entries):
    monkeypatch.setenv("PATH", os.pathsep.join([*entries, *SYSTEM_PATH]))


def _link(target, link):
    """A junction on Windows, which needs no privilege; a symlink elsewhere."""
    if WINDOWS:
        cmd = os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe")
        subprocess.run([cmd, "/c", "mklink", "/J", link, target], check=True,
                       capture_output=True, timeout=30)
    else:
        os.symlink(target, link, target_is_directory=True)
    assert os.path.samefile(link, target), "the link must lead to the working folder"
    return link


# --- endpoints: the claude and codex CLI tiers ---

def test_a_cli_on_a_path_entry_naming_the_server_folder_never_runs(world, monkeypatch):
    stand_in(str(world["bin"]), "claude", str(world["tmp"] / "claude.json"))
    planted = world["tmp"] / "PLANTED-RAN"
    plant_script(str(world["project"]), "claude", str(planted))
    _path(monkeypatch, str(world["project"]), str(world["bin"]))
    (tier,) = build_endpoints(providers=["claude"], modes=("plan",), only_configured=False)
    out = tier.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)
    assert out["text"] == "STUB-ANSWER" and not planted.exists(), out["text"]


@windows_only
def test_a_drive_relative_cli_name_is_refused_before_anything_starts(world, monkeypatch):
    # "C:claude" names a file in the current folder of drive C:, here the server's folder.
    drive = os.path.splitdrive(str(world["project"]))[0]
    if len(drive) != 2:
        pytest.skip("the test folder is not on a lettered drive")
    plant_binary(str(world["project"]), "claude", str(world["tmp"] / "PLANTED-RAN"))
    other = next(d + ":\\" for d in "QRSTUVWXYZ"
                 if d + ":" != drive.upper() and not os.path.exists(d + ":\\"))
    monkeypatch.setenv("PATH", other + "nowhere")
    control = subprocess.run([drive + "claude.exe"], capture_output=True, text=True, timeout=30)
    assert control.returncode == 0 and control.stdout.strip(), "the plant must be reachable"
    backend = CliBackend("claude-plan", [drive + "claude", "-p"], profile="claude")
    assert backend.health() is False, "the drive-relative name resolved to the plant"
    with pytest.raises(BackendError, match="BAD_PATH"):
        backend.chat(_MSG, system="", max_tokens=8, temperature=0, seed=0)


# --- cli_tiers: the doctor starts --version under exec ---

def test_the_doctor_never_starts_a_cli_behind_a_link_to_the_server_folder(world, monkeypatch):
    tested = safe_spawn.PROFILES["claude"].tested
    stand_in(str(world["bin"]), "claude", str(world["tmp"] / "claude.json"),
             version=f"claude {tested} (stand-in)")
    planted = world["tmp"] / "PLANTED-RAN"
    plant_script(str(world["project"]), "claude", str(planted))
    _path(monkeypatch, _link(str(world["project"]), str(world["tmp"] / "linkbin")),
          str(world["bin"]))
    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=m._GRANTS.root, allow_exec=True))
    resp = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": "relay.doctor"}})
    rows = {r["tier"]: r for r in json.loads(resp["result"]["content"][0]["text"])["cli_tiers"]}
    assert not planted.exists(), "the doctor started the planted CLI"
    assert rows["claude"]["status"] == "PASS" and rows["claude"]["version"] == tested


# --- local_git: the git that --auto-commit runs ---

@pytest.mark.skipif(GIT is None, reason="needs git")
@pytest.mark.parametrize("where", ["server-folder", "repo"])
def test_auto_commit_never_runs_a_git_on_a_path_entry_naming_a_working_folder(
        tmp_path, monkeypatch, where):
    repo, server = tmp_path / "repo", tmp_path / "server"
    server.mkdir()
    subprocess.run([GIT, "init", "-q", str(repo)], check=True, capture_output=True, timeout=60)
    folder = server if where == "server-folder" else repo
    planted = tmp_path / "PLANTED-RAN"
    plant_binary(str(folder), "git", str(planted))  # a copy of hostname.exe on Windows
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.chdir(server)
    monkeypatch.setenv("PATH", os.pathsep.join([str(folder), os.path.dirname(GIT)]))
    assert GitRepo(str(repo)).is_repo() is True, "a planted git answered"
    assert not planted.exists()


# --- child_env: run, test_cmd, check and bisect shells ---

SPELLINGS = {
    "naming-it": lambda root, tmp: (str(root), root),
    "below-it": lambda root, tmp: (str(root / "bin"), root / "bin"),
    "link-to-it": lambda root, tmp: (_link(str(root), str(tmp / "linkbin")), root),
}
if WINDOWS:  # cmd.exe drops every quote: "<root>" is <root>, "<root>"\bin is <root>\bin
    SPELLINGS.update({
        "quoted": lambda root, tmp: (f'"{root}"', root),
        "inner-quotes": lambda root, tmp: (f'"{root}"\\bin', root / "bin"),
    })


def _shell_world(tmp_path, monkeypatch, spelling):
    """The run root holds a planted `helper`; the real one sits in another folder.
    The server runs in a third folder, so only the run root can guard the child."""
    root, server, helpers = tmp_path / "root", tmp_path / "server", tmp_path / "helpers"
    for folder in (root, server, helpers):
        folder.mkdir()
    if WINDOWS:
        (helpers / "helper.cmd").write_text("@echo off\r\necho REAL-HELPER\r\n",
                                            encoding="utf-8", newline="")
    else:
        (helpers / "helper").write_text("#!/bin/sh\necho REAL-HELPER\n", encoding="utf-8")
        (helpers / "helper").chmod(0o755)
    entry, folder = SPELLINGS[spelling](root, tmp_path)
    marker = tmp_path / "PLANTED-RAN"
    plant_script(str(folder), "helper", str(marker))
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.delenv("RELAY_CHILD_ENV", raising=False)
    monkeypatch.chdir(server)
    _path(monkeypatch, entry, str(helpers))
    return root, marker


@pytest.mark.parametrize("spelling", sorted(SPELLINGS))
def test_a_run_never_reaches_a_helper_planted_in_its_root(tmp_path, monkeypatch, spelling):
    root, marker = _shell_world(tmp_path, monkeypatch, spelling)
    ex = ToolExecutor(root=str(root), gate=ToolGate(allow_write=True, allow_exec=True))
    out = ex.execute("run", {"cmd": "helper"}).output
    assert "REAL-HELPER" in out and "PLANTED" not in out and not marker.exists(), out


@pytest.mark.parametrize("caller", ["check", "bisect"])
def test_check_and_bisect_never_reach_a_helper_planted_in_their_root(tmp_path, monkeypatch,
                                                                    caller):
    root, marker = _shell_world(tmp_path, monkeypatch, "naming-it")
    if caller == "check":
        ledger = SessionLedger()
        ex = ToolExecutor(root=str(root), gate=ToolGate(allow_write=True, allow_exec=True))
        _run_acceptance("helper", ex, ledger)
        out = ledger.to_jsonl()
    else:
        _, out = _default_runner("helper", str(root))
    assert "REAL-HELPER" in out and "PLANTED" not in out and not marker.exists(), out


def test_the_interpreters_own_folder_stays_on_a_shell_childs_path(monkeypatch):
    # A control: a virtual environment relay itself runs from keeps its folder on
    # PATH, even when the server runs in the folder above it. It passes on 0.4.0.
    here = os.path.dirname(sys.executable)
    monkeypatch.chdir(os.path.dirname(here))
    kept = shell_env({"PATH": here})["PATH"]
    assert kept and os.path.samefile(kept, here), kept
