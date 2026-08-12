"""Xuất BẢNG TỦ ĐIỆN (panel schedule) và SƠ ĐỒ NGUYÊN LÝ một sợi (single-line diagram).

Đây là hai đầu ra hồ sơ mà kỹ sư điện luôn phải nộp, nhưng trước đây hệ thống chỉ tính
được từng thông số rời rạc (cáp, aptomat) chứ không tổng hợp thành bảng nộp được. Tool
này nhận danh sách lộ ra của một tủ, tự tính dòng - aptomat - cáp cho từng lộ (dùng lại
đúng các hàm trong `src/elec_tools.py`, không tính trùng logic), rồi:

- ghi bảng tủ điện ra Excel;
- vẽ sơ đồ nguyên lý một sợi ra file DXF mở được bằng AutoCAD.

Cả hai bước đều là code xác định, LLM chỉ cần cung cấp danh sách lộ.
"""
import json
import logging
import math
import os

import ezdxf
import pandas as pd
from langchain_core.tools import tool

from src.elec_tools import (
    STANDARD_CABLE_SIZES, _select_by_current, _voltage_drop_percent,
    VOLTAGE_DROP_LIMIT_LIGHTING, VOLTAGE_DROP_LIMIT_POWER,
)
from src.workspace import resolve_safe_path

logger = logging.getLogger(__name__)

STANDARD_BREAKERS = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160,
                     200, 250, 320, 400, 500, 630, 800, 1000, 1250, 1600]


def _select_breaker(design_current: float) -> int:
    return next((b for b in STANDARD_BREAKERS if b >= design_current), STANDARD_BREAKERS[-1])


def _circuit_current(power_kw: float, phase: int, voltage: float, cos_phi: float) -> float:
    if phase == 3:
        return power_kw * 1000 / (math.sqrt(3) * voltage * cos_phi)
    return power_kw * 1000 / (220 * cos_phi)


def build_panel_rows(circuits, cos_phi=0.85, voltage=380):
    """Tính dòng, aptomat, cáp và sụt áp cho từng lộ ra của tủ."""
    rows = []
    for index, circuit in enumerate(circuits, start=1):
        name = circuit.get("ten", f"Lộ {index}")
        power = float(circuit.get("cong_suat_kw", 0))
        phase = int(circuit.get("so_pha", 3))
        length = float(circuit.get("chieu_dai_m", 0))
        kind = str(circuit.get("loai", "power")).lower()

        current = _circuit_current(power, phase, voltage, cos_phi)
        breaker = _select_breaker(current * 1.25)
        u = voltage if phase == 3 else 220
        cable = _select_by_current(current)

        limit = VOLTAGE_DROP_LIMIT_LIGHTING if kind.startswith(("light", "chieu")) else VOLTAGE_DROP_LIMIT_POWER
        drop = _voltage_drop_percent(current, length, cable, u, phase, cos_phi) if length > 0 else 0.0
        if length > 0:
            # Tăng tiết diện tới khi đạt giới hạn sụt áp, giống calc_cable_size.
            for section in STANDARD_CABLE_SIZES:
                if section < cable:
                    continue
                if _voltage_drop_percent(current, length, section, u, phase, cos_phi) <= limit:
                    cable = section
                    break
            drop = _voltage_drop_percent(current, length, cable, u, phase, cos_phi)

        rows.append({
            "STT": index,
            "Tên lộ": name,
            "Công suất (kW)": power,
            "Số pha": phase,
            "Dòng tính toán (A)": round(current, 1),
            "Aptomat (A)": breaker,
            "Tiết diện cáp (mm2)": cable,
            "Chiều dài (m)": length,
            "Sụt áp (%)": round(drop, 2) if length > 0 else None,
            "Ghi chú": "" if length > 0 else "Chưa có chiều dài - chưa kiểm tra sụt áp",
        })
    return rows


@tool
def generate_panel_schedule(circuits_json: str, panel_name: str = "Tủ điện phân phối DB",
                            output_excel_path: str = "bang_tu_dien.xlsx",
                            output_dxf_path: str = "so_do_nguyen_ly.dxf",
                            cos_phi: float = 0.85, voltage: float = 380,
                            diversity_factor: float = 0.8) -> str:
    """Lập BẢNG TỦ ĐIỆN (panel schedule) + SƠ ĐỒ NGUYÊN LÝ một sợi từ danh sách lộ ra.

    circuits_json: [{"ten": "Chiếu sáng tầng 1", "cong_suat_kw": 8, "so_pha": 3,
                     "chieu_dai_m": 45, "loai": "lighting"}, ...]
    Tool tự tính dòng làm việc, chọn aptomat, chọn tiết diện cáp (đã kiểm tra sụt áp) cho
    từng lộ, tính aptomat tổng theo hệ số đồng thời, ghi file Excel bảng tủ và file DXF sơ
    đồ nguyên lý mở được bằng AutoCAD.
    """
    logger.info("Generating panel schedule: %s", panel_name)
    try:
        circuits = json.loads(circuits_json)
        if not isinstance(circuits, list) or not circuits:
            return ("Lỗi: `circuits_json` phải là danh sách JSON các lộ ra, không được rỗng. "
                    "Ví dụ: [{\"ten\":\"Chiếu sáng T1\",\"cong_suat_kw\":8,\"so_pha\":3,\"chieu_dai_m\":45}]")

        rows = build_panel_rows(circuits, cos_phi=cos_phi, voltage=voltage)
        total_power = sum(r["Công suất (kW)"] for r in rows)
        calculated_power = total_power * diversity_factor
        main_current = _circuit_current(calculated_power, 3, voltage, cos_phi)
        main_breaker = _select_breaker(main_current * 1.25)
        main_cable = _select_by_current(main_current)

        excel_path = output_excel_path if output_excel_path.endswith(".xlsx") else output_excel_path + ".xlsx"
        excel_safe = resolve_safe_path(excel_path)
        parent = os.path.dirname(excel_safe)
        if parent:
            os.makedirs(parent, exist_ok=True)

        summary = pd.DataFrame([
            {"Thông số": "Tên tủ", "Giá trị": panel_name},
            {"Thông số": "Tổng công suất đặt (kW)", "Giá trị": round(total_power, 1)},
            {"Thông số": f"Công suất tính toán (Kđt {diversity_factor})", "Giá trị": round(calculated_power, 1)},
            {"Thông số": "Dòng tổng (A)", "Giá trị": round(main_current, 1)},
            {"Thông số": "Aptomat tổng (A)", "Giá trị": main_breaker},
            {"Thông số": "Cáp nguồn vào (mm2)", "Giá trị": main_cable},
            {"Thông số": "Số lộ ra", "Giá trị": len(rows)},
        ])
        with pd.ExcelWriter(excel_safe, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name="Bảng tủ điện", index=False)
            summary.to_excel(writer, sheet_name="Tổng hợp", index=False)

        dxf_path = output_dxf_path if output_dxf_path.endswith(".dxf") else output_dxf_path + ".dxf"
        dxf_safe = resolve_safe_path(dxf_path)
        _draw_single_line(dxf_safe, panel_name, rows, main_breaker, main_cable)

        report = [
            f"LẬP BẢNG TỦ ĐIỆN THÀNH CÔNG: {panel_name}",
            f"- Bảng tủ điện (Excel): {excel_path}",
            f"- Sơ đồ nguyên lý một sợi (DXF): {dxf_path}",
            "",
            f"- Tổng công suất đặt: {total_power:.1f} kW",
            f"- Công suất tính toán (Kđt {diversity_factor}): {calculated_power:.1f} kW",
            f"- Dòng tổng: {main_current:.1f} A => APTOMAT TỔNG {main_breaker} A, "
            f"cáp nguồn vào {main_cable} mm2",
            "",
            "CÁC LỘ RA:",
        ]
        for r in rows:
            drop_text = f", sụt áp {r['Sụt áp (%)']}%" if r["Sụt áp (%)"] is not None else ""
            report.append(f"  {r['STT']}. {r['Tên lộ']}: {r['Công suất (kW)']} kW / {r['Số pha']}P "
                          f"=> MCB {r['Aptomat (A)']}A, cáp {r['Tiết diện cáp (mm2)']} mm2{drop_text}")

        no_length = [r["Tên lộ"] for r in rows if r["Sụt áp (%)"] is None]
        if no_length:
            report.append("")
            report.append(f"- CẢNH BÁO: {len(no_length)} lộ chưa có chiều dài tuyến nên CHƯA kiểm tra "
                          f"sụt áp: {', '.join(no_length[:5])}. Tiết diện cáp của các lộ này có thể chưa đủ.")
        report.append("- Kiểm tra thêm dòng ngắn mạch bằng `calc_short_circuit` để chọn đúng khả năng "
                      "cắt Icu cho aptomat.")
        return "\n".join(report)
    except json.JSONDecodeError as e:
        return f"Lỗi đọc JSON lộ ra: {e}"
    except Exception as e:
        return f"Lỗi lập bảng tủ điện: {e}"


def _draw_single_line(path: str, panel_name: str, rows, main_breaker: int, main_cable: float) -> None:
    """Vẽ sơ đồ nguyên lý một sợi: thanh cái ngang, aptomat tổng, các lộ ra rẽ xuống."""
    # units=4: sơ đồ vẽ theo mm; `ezdxf.new()` mặc định khai MÉT nên phải khai lại.
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for layer, color in (("SLD_BUS", 1), ("SLD_DEVICE", 3), ("SLD_TEXT", 7)):
        if layer not in doc.layers:
            doc.layers.add(layer, color=color)

    spacing = 60.0
    bus_y = 0.0
    bus_length = max(spacing * len(rows), spacing)

    # Nguồn vào + aptomat tổng.
    msp.add_line((0, bus_y + 80), (0, bus_y + 30), dxfattribs={"layer": "SLD_BUS"})
    msp.add_lwpolyline([(-10, bus_y + 30), (10, bus_y + 30), (10, bus_y + 10), (-10, bus_y + 10), (-10, bus_y + 30)],
                       dxfattribs={"layer": "SLD_DEVICE"})
    msp.add_text(f"MCCB {main_breaker}A", height=6,
                 dxfattribs={"layer": "SLD_TEXT"}).set_placement((15, bus_y + 18))
    msp.add_text(f"{panel_name} - cáp vào {main_cable} mm2", height=8,
                 dxfattribs={"layer": "SLD_TEXT"}).set_placement((-10, bus_y + 90))
    msp.add_line((0, bus_y + 10), (0, bus_y), dxfattribs={"layer": "SLD_BUS"})

    # Thanh cái.
    msp.add_line((0, bus_y), (bus_length, bus_y), dxfattribs={"layer": "SLD_BUS"})

    # Các lộ ra.
    for i, row in enumerate(rows):
        x = spacing * (i + 1) - spacing / 2
        msp.add_line((x, bus_y), (x, bus_y - 25), dxfattribs={"layer": "SLD_BUS"})
        msp.add_lwpolyline([(x - 8, bus_y - 25), (x + 8, bus_y - 25), (x + 8, bus_y - 40), (x - 8, bus_y - 40),
                            (x - 8, bus_y - 25)], dxfattribs={"layer": "SLD_DEVICE"})
        msp.add_line((x, bus_y - 40), (x, bus_y - 60), dxfattribs={"layer": "SLD_BUS"})
        msp.add_text(f"{row['Aptomat (A)']}A", height=5,
                     dxfattribs={"layer": "SLD_TEXT"}).set_placement((x - 7, bus_y - 36))
        msp.add_text(f"{row['Tên lộ']}", height=5,
                     dxfattribs={"layer": "SLD_TEXT"}).set_placement((x - 25, bus_y - 70))
        msp.add_text(f"{row['Công suất (kW)']}kW / {row['Tiết diện cáp (mm2)']}mm2", height=4,
                     dxfattribs={"layer": "SLD_TEXT"}).set_placement((x - 25, bus_y - 80))

    doc.saveas(path)
