"""Không còn vòng import giữa các module lõi (TECH_DEBT.md mục 12).

`src/tools.py` và `src/qs_tools.py` từng import ngược nhau ở mức module. Hệ quả:

- `import src.qs_tools` TRỰC TIẾP thì vỡ với `partially initialized module` — chỉ chạy
  được nếu vô tình có ai chạm `src.tools` trước.
- Hai file phải dồn import xuống cuối kèm `# noqa: E402`, kèm cả đoạn giải thích dài —
  người đọc sau dễ tưởng là tùy tiện rồi "dọn" lên đầu và làm vỡ.
- `src/api.py` phải nạp `build_revit_boq_excel` vòng qua `src.tools` thay vì lấy thẳng.

Hàm dùng chung nay nằm ở `src/mepf_spec.py` — module nền không import ngược module nào
của dự án. Test này canh để vòng lặp không lặng lẽ quay lại.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Nạp riêng lẻ từng module này (trong tiến trình sạch) đều phải chạy được.
CORE_MODULES = [
    "src.mepf_spec",
    "src.qs_tools",
    "src.tools",
    "src.bim_tools",
    "src.agents",
    "src.graph",
    "src.api",
    "src.project_kernel",
]


@pytest.mark.parametrize("module", CORE_MODULES)
def test_import_doc_lap_trong_tien_trinh_sach(module):
    """Mỗi module phải tự đứng được, không dựa vào việc module khác đã được nạp trước."""
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"`import {module}` trong tiến trình sạch bị lỗi:\n{proc.stderr[-2000:]}"
    )


def test_mepf_spec_khong_import_module_nao_cua_du_an():
    """Điều kiện để `mepf_spec` làm nền chung: nó không được kéo theo ai cả. Thêm một
    `from src...` vào đây là mở đường cho vòng lặp quay lại."""
    source = (ROOT / "src" / "mepf_spec.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import src", "from src")):
            pytest.fail(f"`src/mepf_spec.py` không được import module của dự án: {stripped}")


def test_qs_tools_khong_import_nguoc_len_tools():
    source = (ROOT / "src" / "qs_tools.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("from src.tools import", "import src.tools")):
            pytest.fail(
                "`src/qs_tools.py` import ngược lên `src.tools` ở mức module — vòng lặp "
                f"quay lại: {stripped}. Hàm dùng chung nên đặt ở `src/mepf_spec.py`."
            )


def test_project_kernel_khong_import_tools_hoac_agents():
    """`src/project_kernel.py` đứng độc lập ở tầng Hạ tầng (đặc tả
    `docs/DAC_TA_PROJECT_KERNEL.md` mục 10): được gọi TỪ tool, không được gọi ngược lên
    `tools.py`/`agents.py`/`graph.py` — nối kiểu đó là mở đường cho đúng lớp lỗi "ghép sai
    khi chạy chung" đã gặp ở PR #32."""
    source = (ROOT / "src" / "project_kernel.py").read_text(encoding="utf-8")
    forbidden = ("tools", "agents", "graph", "supervisor_pipeline")
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("import src.", "from src.")):
            continue
        for name in forbidden:
            if stripped.startswith(f"import src.{name}") or stripped.startswith(f"from src.{name} "):
                pytest.fail(f"`src/project_kernel.py` không được import `src.{name}`: {stripped}")


def test_khong_con_noqa_e402_do_vong_import():
    """`# noqa: E402` trong hai file này trước đây là dấu vết của vòng lặp. Hết vòng thì
    cũng không còn lý do để import nằm giữa file."""
    for name in ("tools.py", "qs_tools.py"):
        source = (ROOT / "src" / name).read_text(encoding="utf-8")
        offenders = [
            line.strip() for line in source.splitlines()
            if "noqa: E402" in line and not line.strip().startswith("#")
        ]
        assert not offenders, f"src/{name} còn import đặt lệch: {offenders}"
