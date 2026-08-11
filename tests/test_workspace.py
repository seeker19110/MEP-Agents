import os
import pytest

from src.workspace import set_workspace_dir, get_workspace_dir, resolve_safe_path


@pytest.fixture
def workspace(tmp_path):
    root = set_workspace_dir(str(tmp_path / "session_abc"))
    yield root


def test_set_and_get_workspace_dir(workspace):
    assert get_workspace_dir() == workspace
    assert os.path.isdir(workspace)


def test_relative_path_resolves_inside_workspace(workspace):
    resolved = resolve_safe_path("report.xlsx")
    assert resolved == os.path.join(workspace, "report.xlsx")


def test_nested_relative_path_resolves_inside_workspace(workspace):
    resolved = resolve_safe_path("data/blocks/lib.dxf")
    assert resolved.startswith(workspace)


@pytest.mark.parametrize("malicious_path", [
    "../../etc/passwd",
    "../outside.txt",
    "../../../root/.ssh/id_rsa",
])
def test_path_traversal_is_rejected(workspace, malicious_path):
    with pytest.raises(ValueError):
        resolve_safe_path(malicious_path)


def test_absolute_path_outside_workspace_is_rejected(workspace, tmp_path):
    outside = str(tmp_path / "other_session" / "secret.xlsx")
    with pytest.raises(ValueError):
        resolve_safe_path(outside)
