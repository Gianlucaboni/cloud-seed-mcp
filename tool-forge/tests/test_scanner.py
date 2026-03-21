"""Tests for tool_forge.scanner."""

from __future__ import annotations

import pytest

from tool_forge.scanner import Violation, scan


class TestCleanCode:
    """Verify that safe code passes the scanner."""

    def test_clean_tool_passes(self) -> None:
        source = '''\
from core_mcp.tools._subprocess import run_command

async def my_tool():
    result = await run_command("gcloud", "storage", "ls")
    return result.stdout
'''
        violations = scan(source)
        assert violations == []

    def test_empty_source(self) -> None:
        assert scan("") == []

    def test_normal_imports(self) -> None:
        source = "import json\nimport os\n"
        assert scan(source) == []


class TestEvalExec:
    """S001: eval/exec detection."""

    def test_detects_eval(self) -> None:
        violations = scan("x = eval('1+1')")
        assert len(violations) == 1
        assert violations[0].code == "S001"
        assert "eval" in violations[0].description

    def test_detects_exec(self) -> None:
        violations = scan("exec('print(1)')")
        assert len(violations) == 1
        assert violations[0].code == "S001"
        assert "exec" in violations[0].description


class TestSubprocess:
    """S002: direct subprocess usage detection."""

    def test_detects_import_subprocess(self) -> None:
        violations = scan("import subprocess")
        assert any(v.code == "S002" for v in violations)

    def test_detects_from_subprocess_import(self) -> None:
        violations = scan("from subprocess import run")
        assert any(v.code == "S002" for v in violations)

    def test_detects_subprocess_call(self) -> None:
        source = "import subprocess\nsubprocess.run(['ls'])"
        violations = scan(source)
        s002 = [v for v in violations if v.code == "S002"]
        assert len(s002) >= 1

    def test_detects_os_system(self) -> None:
        violations = scan("import os\nos.system('ls')")
        assert any(v.code == "S002" for v in violations)


class TestFilesystem:
    """S003: forbidden filesystem operations."""

    def test_detects_os_remove(self) -> None:
        violations = scan("import os\nos.remove('/tmp/x')")
        assert any(v.code == "S003" for v in violations)

    def test_detects_shutil_rmtree(self) -> None:
        violations = scan("import shutil\nshutil.rmtree('/tmp')")
        assert any(v.code == "S003" for v in violations)

    def test_detects_unlink(self) -> None:
        violations = scan("from pathlib import Path\nPath('x').unlink()")
        assert any(v.code == "S003" for v in violations)


class TestNetwork:
    """S004: forbidden network modules."""

    def test_detects_socket_import(self) -> None:
        violations = scan("import socket")
        assert any(v.code == "S004" for v in violations)

    def test_detects_requests_import(self) -> None:
        violations = scan("import requests")
        assert any(v.code == "S004" for v in violations)

    def test_detects_urllib_import(self) -> None:
        violations = scan("import urllib")
        assert any(v.code == "S004" for v in violations)

    def test_detects_urllib_request_from_import(self) -> None:
        violations = scan("from urllib.request import urlopen")
        assert any(v.code == "S004" for v in violations)

    def test_detects_http_client_import(self) -> None:
        violations = scan("from http.client import HTTPConnection")
        assert any(v.code == "S004" for v in violations)


class TestViolationStr:
    """Verify Violation.__str__ formatting."""

    def test_format(self) -> None:
        v = Violation(line=10, col=4, code="S001", description="bad eval")
        assert str(v) == "L10:4 [S001] bad eval"


class TestMultipleViolations:
    """Verify that the scanner finds all violations, not just the first."""

    def test_finds_all(self) -> None:
        source = "eval('x')\nexec('y')\nimport subprocess\n"
        violations = scan(source)
        codes = {v.code for v in violations}
        assert "S001" in codes
        assert "S002" in codes
        assert len(violations) >= 3  # 2x S001 + 1x S002
