#!/usr/bin/env python
"""Đối chiếu kết quả suy hình học với hồ sơ đã bóc tay, và dò ngưỡng phù hợp.

## Vì sao cần script này

Hai sửa đổi ở `src/cad_geometry.py` (cảnh báo tuyến vẽ 2 nét, đếm co/tê theo bậc nút)
**làm đổi con số đi vào hồ sơ thầu**. Chúng đã được kiểm bằng dữ liệu dựng tay — chữ L,
chữ T, ngã tư, các cặp đoạn ở góc cụ thể — và dữ liệu đó chứng minh logic đúng. Nhưng nó
KHÔNG thay được việc chạy trên bản vẽ thật rồi so với bảng bóc tay đã duyệt, vì bốn ngưỡng
dưới đây phụ thuộc quy ước vẽ của từng văn phòng:

| Ngưỡng | Mặc định | Quyết định điều gì |
|---|---:|---|
| `PARALLEL_ANGLE_TOLERANCE_DEG` | 2° | Hai nét có được coi là song song (→ cảnh báo tính đôi) |
| `DOUBLE_LINE_MAX_WIDTH_MM` | 2000 | Khoảng cách tối đa giữa hai mép một ống |
| `ELBOW_MIN_ANGLE_DEG` | 15° | Chỗ gãy nào là một cái co |
| `PIPE_STOCK_LENGTH_MM` | 6000 | Bao nhiêu mét ống thì cần một măng sông |

Script này chạy bộ suy hình học trên bản vẽ THẬT của bạn và in ra con số, để bạn so từng
dòng với hồ sơ đã duyệt. Nó **không sửa gì** — chỉ đọc.

## Dùng thế nào

    # Một bản vẽ hoặc cả thư mục
    uv run python scripts/kiem_chung_hinh_hoc.py ho_so/tang_3.dxf
    uv run python scripts/kiem_chung_hinh_hoc.py ho_so/

    # Dò độ nhạy: chạy lại với nhiều ngưỡng để xem con số lung lay đến đâu
    uv run python scripts/kiem_chung_hinh_hoc.py ho_so/ --do-nhay

**Đọc kết quả thế nào.** Nếu cột "tê" và "co" khớp hồ sơ đã duyệt thì ngưỡng đang đúng với
quy ước vẽ của bạn. Lệch nhiều mà `--do-nhay` cho thấy con số đổi mạnh theo ngưỡng thì
chỉnh ngưỡng trong `.env` rồi chạy lại. Lệch mà con số KHÔNG lung lay theo ngưỡng thì
nguyên nhân nằm ở chỗ khác — hãy báo lại kèm bản vẽ.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _drawings(target: str) -> list[str]:
    if os.path.isfile(target):
        return [target]
    found = []
    for root, _dirs, files in os.walk(target):
        for name in sorted(files):
            if name.lower().endswith(".dxf"):
                found.append(os.path.join(root, name))
    return found


def _analyse(path: str, *, angle_tol=None, max_width=None, elbow=None, stock=None) -> dict:
    """Đọc một bản vẽ và trả về các con số suy từ hình học."""
    import ezdxf

    from src import cad_geometry as g

    doc = ezdxf.readfile(path)
    segments = g.collect_segments(list(doc.modelspace()))

    if elbow is not None:
        g.ELBOW_MIN_ANGLE_DEG = elbow
    if angle_tol is not None:
        g._PARALLEL_ANGLE_TOLERANCE_DEG = angle_tol

    fittings = g.detect_fittings(
        segments,
        stock_length=stock if stock is not None else g.DEFAULT_PIPE_STOCK_LENGTH,
    )
    doubled = g.detect_double_line_runs(
        segments,
        max_width=max_width if max_width is not None else g.DEFAULT_DOUBLE_LINE_MAX_WIDTH,
    )
    total_length = sum(s["length"] for s in segments)
    return {
        "so_doan": len(segments),
        "tong_dai": total_length,
        "phu_kien": fittings,
        "tinh_doi": doubled,
    }


def _print_report(path: str, result: dict) -> None:
    print(f"\n=== {os.path.basename(path)} ===")
    print(f"  Số đoạn hình học : {result['so_doan']}")
    print(f"  Tổng chiều dài   : {result['tong_dai']:,.0f} (đơn vị bản vẽ)")

    if result["phu_kien"]:
        print("  Phụ kiện suy ra theo layer:")
        print(f"    {'Layer':<28} {'co':>6} {'tê':>6} {'măng sông':>11}")
        for layer in sorted(result["phu_kien"]):
            f = result["phu_kien"][layer]
            print(f"    {layer[:28]:<28} {f['co']:>6} {f['te']:>6} {f['mang_song']:>11}")
    else:
        print("  Phụ kiện: không suy được (không có tuyến LINE/POLYLINE nào)")

    if result["tinh_doi"]:
        total = sum(result["tinh_doi"].values())
        print(f"  ⚠ NGHI TÍNH ĐÔI  : ~{total:,.0f} (đơn vị bản vẽ) tại "
              f"{', '.join(sorted(result['tinh_doi']))}")
        print("    → Đối chiếu: các tuyến này có đang được vẽ bằng 2 nét song song không?")
    else:
        print("  Nghi tính đôi    : không phát hiện")


def _sensitivity(path: str) -> None:
    """Chạy lại với nhiều ngưỡng để thấy con số nhạy đến đâu.

    Con số ổn định qua nhiều ngưỡng là con số đáng tin. Con số nhảy mạnh nghĩa là bản vẽ
    nằm ngay ranh giới quy ước — chỗ đó phải do kỹ sư quyết, không phải do mặc định.
    """
    print(f"\n--- Độ nhạy theo ngưỡng: {os.path.basename(path)} ---")
    print(f"  {'góc ss':>7} {'bề rộng':>9} {'góc co':>7} | {'tổng tê':>8} {'tổng co':>8} {'nghi tính đôi':>15}")
    for angle_tol in (1.0, 2.0, 4.0):
        for max_width in (1000.0, 2000.0, 3000.0):
            for elbow in (10.0, 15.0, 30.0):
                r = _analyse(path, angle_tol=angle_tol, max_width=max_width, elbow=elbow)
                tees = sum(f["te"] for f in r["phu_kien"].values())
                elbows = sum(f["co"] for f in r["phu_kien"].values())
                doubled = sum(r["tinh_doi"].values())
                print(f"  {angle_tol:>7.1f} {max_width:>9.0f} {elbow:>7.1f} |"
                      f" {tees:>8} {elbows:>8} {doubled:>15,.0f}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đối chiếu kết quả suy hình học với hồ sơ đã bóc tay. CHỈ ĐỌC, không sửa bản vẽ.")
    parser.add_argument("duong_dan", help="File .dxf hoặc thư mục chứa .dxf")
    parser.add_argument("--do-nhay", action="store_true",
                        help="Chạy lại với nhiều ngưỡng để xem con số lung lay đến đâu")
    args = parser.parse_args()

    drawings = _drawings(args.duong_dan)
    if not drawings:
        print(f"Không tìm thấy file .dxf nào trong: {args.duong_dan}", file=sys.stderr)
        print("Lưu ý: script này chỉ đọc .dxf. File .dwg cần chuyển đổi trước "
              "(tool `convert_dwg_to_dxf`).", file=sys.stderr)
        return 1

    print(f"Đọc {len(drawings)} bản vẽ. Ngưỡng đang dùng:")
    from src import cad_geometry as g
    print(f"  góc song song {g._PARALLEL_ANGLE_TOLERANCE_DEG}°, "
          f"bề rộng tối đa {g.DEFAULT_DOUBLE_LINE_MAX_WIDTH:.0f} mm, "
          f"góc co {g.ELBOW_MIN_ANGLE_DEG}°, "
          f"cây ống {g.DEFAULT_PIPE_STOCK_LENGTH:.0f} mm")

    failures = 0
    for path in drawings:
        try:
            _print_report(path, _analyse(path))
            if args.do_nhay:
                _sensitivity(path)
        except Exception as e:
            failures += 1
            print(f"\n=== {os.path.basename(path)} ===\n  LỖI ĐỌC: {e}", file=sys.stderr)

    print("\n" + "-" * 70)
    print("So từng dòng với hồ sơ đã bóc tay. Lệch nhiều thì chỉnh ngưỡng trong .env:")
    print("  PARALLEL_ANGLE_TOLERANCE_DEG, DOUBLE_LINE_MAX_WIDTH_MM,")
    print("  ELBOW_MIN_ANGLE_DEG, PIPE_STOCK_LENGTH_MM")
    print("Lệch mà --do-nhay cho thấy con số KHÔNG đổi theo ngưỡng thì nguyên nhân ở chỗ")
    print("khác — hãy báo lại kèm bản vẽ.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
