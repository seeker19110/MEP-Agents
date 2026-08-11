import os
import ezdxf
from ezdxf.lldxf import const as dxf_const

from src.cad_standards import BLOCK_STANDARD

# ATTDEF ẩn + hằng số (không hỏi lại khi chèn Block) mang mã hiệu/mô tả chuẩn đi
# kèm mọi lần chèn Block, khớp với những gì `standardize_cad_drawing` gắn thêm cho
# các Block không có sẵn trong thư viện này.
_ATTDEF_FLAGS = dxf_const.ATTRIB_INVISIBLE + dxf_const.ATTRIB_CONST


def _tag_with_standard_attributes(block_layout, block_name: str) -> None:
    std = BLOCK_STANDARD.get(block_name)
    if not std:
        return
    block_layout.add_attdef("MA_HIEU", (0, 0), text=std["ma_hieu"],
                             dxfattribs={"height": 30, "flags": _ATTDEF_FLAGS, "layer": "0"})
    block_layout.add_attdef("MO_TA", (0, 0), text=std["description"],
                             dxfattribs={"height": 30, "flags": _ATTDEF_FLAGS, "layer": "0"})


def main():
    print("Khởi tạo Thư viện Block MEPF Trung tâm...")

    blocks_dir = os.path.join("data", "blocks")
    if not os.path.exists(blocks_dir):
        os.makedirs(blocks_dir)

    doc = ezdxf.new('R2010')
    
    # 1. HVAC - DIFFUSER_SUPPLY (600x600 square with X)
    blk_ds = doc.blocks.new(name='DIFFUSER_SUPPLY')
    blk_ds.add_lwpolyline([(0, 0), (600, 0), (600, 600), (0, 600)], close=True)
    blk_ds.add_line((0, 0), (600, 600))
    blk_ds.add_line((0, 600), (600, 0))
    _tag_with_standard_attributes(blk_ds, 'DIFFUSER_SUPPLY')

    # 2. HVAC - DIFFUSER_RETURN (600x600 square with one diagonal)
    blk_dr = doc.blocks.new(name='DIFFUSER_RETURN')
    blk_dr.add_lwpolyline([(0, 0), (600, 0), (600, 600), (0, 600)], close=True)
    blk_dr.add_line((0, 0), (600, 600))
    _tag_with_standard_attributes(blk_dr, 'DIFFUSER_RETURN')

    # 3. HVAC - FCU (Rectangle 1000x500 with text)
    blk_fcu = doc.blocks.new(name='FCU')
    blk_fcu.add_lwpolyline([(0, 0), (1000, 0), (1000, 500), (0, 500)], close=True)
    blk_fcu.add_text("FCU", dxfattribs={'height': 150}).set_placement((350, 175))
    _tag_with_standard_attributes(blk_fcu, 'FCU')

    # 4. ELEC - LIGHT_PANEL (600x600 square with L)
    blk_lp = doc.blocks.new(name='LIGHT_PANEL')
    blk_lp.add_lwpolyline([(0, 0), (600, 0), (600, 600), (0, 600)], close=True)
    blk_lp.add_text("L", dxfattribs={'height': 200}).set_placement((250, 200))
    _tag_with_standard_attributes(blk_lp, 'LIGHT_PANEL')

    # 5. ELEC - LIGHT_DOWNLIGHT (Circle r=100)
    blk_ld = doc.blocks.new(name='LIGHT_DOWNLIGHT')
    blk_ld.add_circle((0, 0), radius=100)
    _tag_with_standard_attributes(blk_ld, 'LIGHT_DOWNLIGHT')

    # 6. ELEC - SOCKET (Half circle with lines)
    blk_soc = doc.blocks.new(name='SOCKET')
    blk_soc.add_arc((0, 0), radius=50, start_angle=0, end_angle=180)
    blk_soc.add_line((0, 50), (0, 100))
    _tag_with_standard_attributes(blk_soc, 'SOCKET')

    # 7. ELEC - SWITCH (Circle with dot)
    blk_sw = doc.blocks.new(name='SWITCH')
    blk_sw.add_circle((0, 0), radius=30)
    blk_sw.add_line((30, 0), (60, 30))
    _tag_with_standard_attributes(blk_sw, 'SWITCH')

    # 8. FIRE - SPRINKLER (Circle r=50 with lines)
    blk_sp = doc.blocks.new(name='SPRINKLER')
    blk_sp.add_circle((0, 0), radius=50)
    blk_sp.add_line((-50, 0), (50, 0))
    blk_sp.add_line((0, -50), (0, 50))
    _tag_with_standard_attributes(blk_sp, 'SPRINKLER')

    # 9. PLUMB - PUMP (Circle inside triangle)
    blk_pmp = doc.blocks.new(name='PUMP')
    blk_pmp.add_circle((150, 100), radius=50)
    blk_pmp.add_lwpolyline([(0, 0), (300, 0), (150, 200)], close=True)
    _tag_with_standard_attributes(blk_pmp, 'PUMP')

    file_path = os.path.join(blocks_dir, "mepf_library.dxf")
    doc.saveas(file_path)
    print(f"Đã tạo thành công thư viện Master CAD tại {file_path}")

if __name__ == "__main__":
    main()
