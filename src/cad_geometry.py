"""Hình học CAD dùng chung: chiều dài THẬT của tuyến, cao độ Z, và suy ra phụ kiện ống.

Trước module này, mọi tool đo chiều dài đều cộng khoảng cách thẳng giữa các vertex. Ba
hệ quả sai số trong hồ sơ thật:

1. **Cung cong bị đo hụt.** Đoạn cong trong LWPOLYLINE được mã hóa bằng `bulge` ở vertex
   đầu đoạn; cộng khoảng cách hai đầu là đo DÂY CUNG chứ không phải cung tròn. Với co 90°
   bán kính R, dây cung ngắn hơn cung thật khoảng 10%.
2. **Entity ARC bị bỏ hẳn.** Ống vẽ bằng ARC rời (rất phổ biến khi vẽ tay) không được
   tính một mét nào.
3. **Cao độ bị bỏ qua.** Tuyến đi xiên giữa hai cao độ (ống lên/xuống trục kỹ thuật) bị
   đo bằng hình chiếu bằng, luôn ngắn hơn chiều dài thật.
4. **SPLINE/ELLIPSE bị bỏ hẳn.** Tuyến uốn cong tự do vẽ bằng SPLINE đo ra đúng 0 m.
5. **Lưới 3D bị đếm nhầm thành ống.** POLYLINE dạng polyface/polygon mesh là bề mặt 3D,
   cộng cạnh lưới vào chiều dài ống cho ra một con số vô nghĩa.
6. **Tọa độ OCS bị đọc như WCS.** Đối tượng vẽ trong UCS lật/xoay lưu tọa độ theo hệ
   riêng; đọc thẳng là đặt tuyến sai chỗ trên mặt bằng (chiều dài vẫn đúng, nhưng ghi chú
   bị gán nhầm tuyến và hình học trùng lặp không bị bắt).

Toàn bộ hàm ở đây là hình học thuần, không phụ thuộc LLM.
"""
import math
import re

# Sai số tọa độ coi như trùng điểm (đơn vị bản vẽ). Bản vẽ MEPF thường vẽ theo mm nên
# 1 đơn vị là đủ chặt để nối tuyến mà vẫn bỏ qua lệch do làm tròn khi vẽ.
JOINT_TOLERANCE = 1.0

# Ghi chú kích thước ống tròn: Ø110, DN100, D110, OD110... -> bán kính = số/2.
_DIAMETER_RE = re.compile(r"(?i)\b(?:Ø|DN|OD|D)\s*(\d+(?:\.\d+)?)\b")
# Ghi chú kích thước ống gió chữ nhật: 600x400, 600*400, W600xH400...
_DUCT_RE = re.compile(r"(?i)\b(?:W)?(\d+(?:\.\d+)?)\s*[xX\*]\s*(?:H)?(\d+(?:\.\d+)?)\b")

# Góc đổi hướng tối thiểu để coi là một co (elbow). Dưới ngưỡng này chỉ là tuyến gần
# thẳng bị chia nhỏ vertex, không phải chỗ lắp phụ kiện.
ELBOW_MIN_ANGLE_DEG = 15.0

# Chiều dài một cây ống thương phẩm (đơn vị bản vẽ giống bản vẽ). Dùng để suy số măng
# sông (nối ống): cứ hết một cây là phải có một mối nối.
DEFAULT_PIPE_STOCK_LENGTH = 6000.0  # 6 m theo mm


def bulge_arc_length(x1: float, y1: float, x2: float, y2: float, bulge: float) -> float:
    """Chiều dài CUNG giữa hai vertex của LWPOLYLINE theo hệ số `bulge`.

    Trong DXF, `bulge = tan(θ/4)` với θ là góc ở tâm của cung. Từ đó:
        θ = 4·atan(|bulge|),  R = dây cung / (2·sin(θ/2)),  cung = R·θ
    `bulge = 0` nghĩa là đoạn thẳng, trả về chính chiều dài dây cung.
    """
    chord = math.hypot(x2 - x1, y2 - y1)
    if not bulge or chord == 0:
        return chord
    theta = 4.0 * math.atan(abs(bulge))
    half = math.sin(theta / 2.0)
    if half == 0:
        return chord
    radius = chord / (2.0 * half)
    return radius * theta


def _polyline_vertices(entity):
    """(x, y, z, bulge) của từng vertex, thống nhất cho LWPOLYLINE và POLYLINE."""
    dxftype = entity.dxftype()
    if dxftype == "LWPOLYLINE":
        elevation = getattr(entity.dxf, "elevation", 0.0) or 0.0
        return [(p[0], p[1], elevation, p[4]) for p in entity.get_points(format="xyseb")]
    if dxftype == "POLYLINE":
        result = []
        for v in entity.vertices:
            loc = v.dxf.location
            result.append((loc.x, loc.y, getattr(loc, "z", 0.0) or 0.0,
                           getattr(v.dxf, "bulge", 0.0) or 0.0))
        return result
    return []


def polyline_segments(entity):
    """Các đoạn của một polyline: tọa độ hai đầu, bulge, chiều dài thật, có cong hay không.

    Polyline đóng (`closed`) được nối thêm đoạn từ vertex cuối về vertex đầu — bỏ sót
    đoạn này là đo hụt đúng một cạnh của mọi tuyến ống chạy vòng khép kín.
    """
    verts = _polyline_vertices(entity)
    if len(verts) < 2:
        return []

    pairs = list(zip(verts[:-1], verts[1:]))
    if getattr(entity, "closed", False) or getattr(entity.dxf, "flags", 0) & 1:
        pairs.append((verts[-1], verts[0]))

    segments = []
    for (x1, y1, z1, bulge), (x2, y2, z2, _) in pairs:
        planar = bulge_arc_length(x1, y1, x2, y2, bulge)
        dz = z2 - z1
        # Cung cong nằm trong mặt phẳng polyline nên chỉ đoạn thẳng mới cộng thêm dz.
        length = math.hypot(planar, dz) if (not bulge and dz) else planar
        segments.append({
            "start": (x1, y1, z1),
            "end": (x2, y2, z2),
            "bulge": bulge,
            "length": length,
            "is_arc": bool(bulge),
        })
    return segments


def arc_entity_length(entity) -> float:
    """Chiều dài của entity ARC rời (trước đây bị bỏ qua hoàn toàn khi đo khối lượng)."""
    radius = float(entity.dxf.radius)
    start = float(entity.dxf.start_angle)
    end = float(entity.dxf.end_angle)
    sweep = (end - start) % 360.0
    if sweep == 0:
        sweep = 360.0
    return radius * math.radians(sweep)


# Độ mịn khi bẻ SPLINE/ELLIPSE thành đường gấp khúc: sai số phình (sagitta) tối đa bằng
# 1/1000 kích thước bao của chính đường cong. Dùng tỷ lệ thay vì một con số mm cố định để
# không phụ thuộc đơn vị bản vẽ; 0.1% là mịn hơn nhiều so với sai số thi công thực tế.
_CURVE_FLATTENING_RATIO = 0.001


def _flattened_points(entity):
    """Điểm xấp xỉ của một đường cong tự do (SPLINE/ELLIPSE) theo độ mịn tương đối."""
    try:
        points = [(p[0], p[1], p[2] if len(p) > 2 else 0.0)
                  for p in entity.control_points] if entity.dxftype() == "SPLINE" else []
    except Exception:
        points = []
    if points:
        span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in (0, 1))
    else:
        span = float(getattr(entity.dxf, "major_axis", (1.0, 0.0, 0.0))[0] or 1.0) * 2
    distance = abs(span) * _CURVE_FLATTENING_RATIO
    if distance <= 0:
        distance = 1e-6
    return [(p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in entity.flattening(distance)]


def _curve_segments(entity):
    """Các đoạn xấp xỉ của SPLINE/ELLIPSE.

    Ống/ống gió vẽ bằng SPLINE (tuyến uốn cong tự do) hoặc ELLIPSE trước đây được đo là
    **0 m** — bỏ sót trọn vẹn, không một dòng cảnh báo.
    """
    points = _flattened_points(entity)
    if len(points) < 2:
        return []
    segments = []
    for index, (p1, p2) in enumerate(zip(points[:-1], points[1:])):
        length = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2)
        segments.append({
            "start": p1, "end": p2, "bulge": None, "length": length,
            # CHỈ mắt đầu tiên mang `is_arc` — cả đường cong là MỘT chỗ đổi hướng, đúng như
            # một entity ARC. Đánh dấu mọi mắt là cung sẽ đếm mỗi mắt xấp xỉ thành một co:
            # một spline duy nhất từng ra 1654 cái co.
            "is_arc": index == 0,
            # Cờ này để phần suy phụ kiện bỏ qua các khớp nối giữa những mắt xấp xỉ — chúng
            # là sản phẩm của phép chia nhỏ, không phải chỗ lắp phụ kiện trên công trường.
            "flattened": True,
        })
    return segments


def _to_wcs(entity, segments):
    """Đưa tọa độ đoạn từ OCS về WCS khi entity có vector đùn (extrusion) khác mặc định.

    Đối tượng vẽ trong UCS lật hoặc xoay được lưu với `extrusion` khác (0,0,1) và tọa độ
    tính trong hệ riêng của nó. Đọc thẳng tọa độ đó là **đặt tuyến sai chỗ trên mặt bằng**
    (VD extrusion (0,0,-1) lật dấu trục X): chiều dài vẫn đúng vì phép biến đổi là trực
    giao, nhưng ghi chú kích thước bị gán nhầm tuyến, hình học trùng lặp không bị bắt, và
    kiểm tra va chạm so sai vị trí.
    """
    try:
        extrusion = tuple(getattr(entity.dxf, "extrusion", (0.0, 0.0, 1.0)) or (0.0, 0.0, 1.0))
    except Exception:
        return segments
    if not segments or all(abs(a - b) < 1e-9 for a, b in zip(extrusion, (0.0, 0.0, 1.0))):
        return segments

    ocs = entity.ocs()
    for seg in segments:
        for key in ("start", "end"):
            point = ocs.to_wcs(seg[key])
            seg[key] = (point[0], point[1], point[2])
    return segments


def entity_segments(entity):
    """Chuẩn hóa mọi entity đo được về cùng một danh sách đoạn, tọa độ theo WCS.

    Hỗ trợ LINE (kể cả xiên theo Z), LWPOLYLINE/POLYLINE (kể cả cung bulge và polyline
    đóng), ARC, CIRCLE, SPLINE và ELLIPSE. Entity không đo được trả về danh sách rỗng.

    POLYLINE dạng LƯỚI (polyface mesh / polygon mesh) bị loại: đó là bề mặt 3D, không phải
    tuyến ống — cộng cạnh lưới vào sẽ thổi phồng chiều dài ống bằng một con số vô nghĩa.
    """
    dxftype = entity.dxftype()
    try:
        if dxftype in ("SPLINE", "ELLIPSE"):
            return _curve_segments(entity)

        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            z1 = getattr(s, "z", 0.0) or 0.0
            z2 = getattr(e, "z", 0.0) or 0.0
            length = math.sqrt((e.x - s.x) ** 2 + (e.y - s.y) ** 2 + (z2 - z1) ** 2)
            return [{"start": (s.x, s.y, z1), "end": (e.x, e.y, z2),
                     "bulge": 0.0, "length": length, "is_arc": False}]

        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            if getattr(entity, "is_poly_face_mesh", False) or getattr(entity, "is_polygon_mesh", False):
                return []
            return _to_wcs(entity, polyline_segments(entity))

        if dxftype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            a1 = math.radians(float(entity.dxf.start_angle))
            a2 = math.radians(float(entity.dxf.end_angle))
            start = (center.x + radius * math.cos(a1), center.y + radius * math.sin(a1), z)
            end = (center.x + radius * math.cos(a2), center.y + radius * math.sin(a2), z)
            return _to_wcs(entity, [{"start": start, "end": end, "bulge": None,
                                     "length": arc_entity_length(entity), "is_arc": True}])

        if dxftype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            point = (center.x + radius, center.y, z)
            return _to_wcs(entity, [{"start": point, "end": point, "bulge": None,
                                     "length": 2 * math.pi * radius, "is_arc": True}])
    except Exception:  # pragma: no cover - entity dị dạng trong file thực tế
        return []
    return []


def entity_length(entity) -> float:
    """Tổng chiều dài THẬT của một entity (đã tính cung cong và chênh cao độ)."""
    return sum(seg["length"] for seg in entity_segments(entity))


def collect_segments(entities):
    """Gom toàn bộ đoạn đo được của một tập entity, kèm layer của mỗi đoạn."""
    collected = []
    for entity in entities:
        layer = getattr(entity.dxf, "layer", "0")
        for seg in entity_segments(entity):
            item = dict(seg)
            item["layer"] = layer
            collected.append(item)
    return collected


try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        def wrapper(func): return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return wrapper

@njit(fastmath=True, cache=True)
def _angle(p1, p2) -> float:
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])


@njit(fastmath=True, cache=True)
def _same_point(p1, p2, tol: float) -> bool:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) <= tol


def _segment_bbox(seg, tol: float = 0.0):
    ax, ay, _ = seg["start"]
    bx, by, _ = seg["end"]
    return (min(ax, bx) - tol, min(ay, by) - tol, max(ax, bx) + tol, max(ay, by) + tol)


@njit(fastmath=True, cache=True)
def _point_on_segment_interior(point, s_start, s_end, tol: float) -> bool:
    """Điểm có nằm trên THÂN đoạn (không phải hai đầu) hay không — dấu hiệu của chỗ rẽ tê."""
    ax, ay = s_start[0], s_start[1]
    bx, by = s_end[0], s_end[1]
    px, py = point[0], point[1]
    if _same_point(point, s_start, tol) or _same_point(point, s_end, tol):
        return False
    l2 = (bx - ax) ** 2 + (by - ay) ** 2
    if l2 == 0:
        return False
    t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2
    if not (0.0 < t < 1.0):
        return False
    dist = math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
    return dist <= tol


def _connected_run_lengths(segs, tolerance: float):
    """Tổng chiều dài của TỪNG tuyến liên tục trong một tập đoạn (union-find theo đầu mút).

    Hai đoạn chung đầu mút thuộc cùng một tuyến; tuyến là đơn vị đúng để suy số mối nối
    ống, vì ống được cắt từ cây thương phẩm dọc theo tuyến chứ không theo từng đoạn vẽ.
    """
    if not segs:
        return []
    step = tolerance if tolerance > 0 else 1.0
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    def key(point):
        return (round(point[0] / step), round(point[1] / step))

    for seg in segs:
        union(key(seg["start"]), key(seg["end"]))

    totals = {}
    for seg in segs:
        root = find(key(seg["start"]))
        totals[root] = totals.get(root, 0.0) + seg["length"]
    return list(totals.values())


def _process_fittings_for_layer(args):
    layer, segs, tolerance, stock_length = args
    elbows = sum(1 for s in segs if s["is_arc"])
    tees = 0

    try:
        from rtree import index
        has_rtree = True
    except ImportError:
        has_rtree = False

    if has_rtree:
        idx = index.Index()
        for i, seg in enumerate(segs):
            idx.insert(i, _segment_bbox(seg, tolerance))

        # Co tại chỗ hai đoạn thẳng nối nhau và đổi hướng đáng kể.
        for i, a in enumerate(segs):
            if a["is_arc"] or a.get("flattened"):
                continue
            px, py, _ = a["end"]
            candidates = idx.intersection((px - tolerance, py - tolerance, px + tolerance, py + tolerance))
            for j in candidates:
                if j <= i:
                    continue
                b = segs[j]
                if b["is_arc"] or b.get("flattened") or not _same_point(a["end"], b["start"], tolerance):
                    continue
                turn = abs(math.degrees(_angle(b["start"], b["end"]) - _angle(a["start"], a["end"])))
                turn = min(turn % 360, 360 - (turn % 360))
                if turn >= ELBOW_MIN_ANGLE_DEG:
                    elbows += 1

        # Tê: đầu mút tuyến này chạm thân tuyến kia.
        for i, a in enumerate(segs):
            px, py, _ = a["start"]
            for j in idx.intersection((px - tolerance, py - tolerance, px + tolerance, py + tolerance)):
                if i == j:
                    continue
                if _point_on_segment_interior(a["start"], segs[j]["start"], segs[j]["end"], tolerance):
                    tees += 1
                    break
            else: # if no tee at start, check end
                px, py, _ = a["end"]
                for j in idx.intersection((px - tolerance, py - tolerance, px + tolerance, py + tolerance)):
                    if i == j:
                        continue
                    if _point_on_segment_interior(a["end"], segs[j]["start"], segs[j]["end"], tolerance):
                        tees += 1
                        break
    else:
        # Fallback O(N^2) nếu không có rtree
        for i, a in enumerate(segs):
            if a["is_arc"] or a.get("flattened"):
                continue
            for b in segs[i + 1:]:
                if b["is_arc"] or b.get("flattened") or not _same_point(a["end"], b["start"], tolerance):
                    continue
                turn = abs(math.degrees(_angle(b["start"], b["end"]) - _angle(a["start"], a["end"])))
                turn = min(turn % 360, 360 - (turn % 360))
                if turn >= ELBOW_MIN_ANGLE_DEG:
                    elbows += 1

        for i, a in enumerate(segs):
            for j, b in enumerate(segs):
                if i == j:
                    continue
                if _point_on_segment_interior(a["start"], b["start"], b["end"], tolerance) or \
                        _point_on_segment_interior(a["end"], b["start"], b["end"], tolerance):
                    tees += 1
                    break

    # Măng sông tính theo TỪNG TUYẾN LIÊN TỤC, không theo từng đoạn rời.
    #
    # Đếm theo đoạn (chỉ đoạn nào dài hơn một cây ống mới có mối nối) bỏ sót gần như toàn
    # bộ hồ sơ thật: một tuyến ống 100 m luôn được vẽ thành một polyline nhiều vertex, mỗi
    # đoạn chỉ vài mét nên KHÔNG đoạn nào vượt 6 m — ra 0 măng sông trong khi thực tế cần
    # 16 cái. Cộng dồn cả layer thì lại thổi phồng khi bản vẽ có nhiều mẩu ống rời rạc.
    # Gom theo tuyến liên tục xử lý đúng cả hai: mẩu 2 m đứng một mình vẫn ra 0 mối nối.
    couplings = 0
    if stock_length > 0:
        for run_length in _connected_run_lengths(segs, tolerance):
            couplings += max(0, math.ceil(run_length / stock_length) - 1)

    return layer, {"co": elbows, "te": tees, "mang_song": couplings}


def detect_fittings(segments, stock_length: float = DEFAULT_PIPE_STOCK_LENGTH,
                    tolerance: float = JOINT_TOLERANCE) -> dict:
    """Suy ra số phụ kiện ống (co / tê / măng sông) từ hình học tuyến, theo từng layer.

    Với bản vẽ chỉ có LINE/POLYLINE thuần (không chèn Block phụ kiện), cách duy nhất để
    không bóc thiếu phụ kiện là suy từ chính hình học:

    - **Co (elbow)**: mỗi chỗ tuyến đổi hướng quá `ELBOW_MIN_ANGLE_DEG`, gồm cả khúc nối
      giữa hai đoạn thẳng lẫn mỗi đoạn cung (bulge/ARC — bản thân cung chính là một co).
    - **Tê (tee)**: đầu mút của một tuyến chạm vào THÂN của tuyến khác cùng layer.
    - **Măng sông (coupling)**: ống bán theo cây `stock_length`, cứ hết một cây phải có
      một mối nối, nên số măng sông ≈ ceil(tổng chiều dài / cây) - số tuyến.

    Trả về `{layer: {"co": n, "te": n, "mang_song": n}}`. Đây là ƯỚC TÍNH hình học, kỹ sư
    vẫn phải đối chiếu bản vẽ chi tiết — nhưng ước tính có căn cứ vẫn tốt hơn bỏ trắng.
    """
    by_layer = {}
    for seg in segments:
        by_layer.setdefault(seg["layer"], []).append(seg)

    if not by_layer:
        return {}

    result = {}
    
    # Nếu chỉ có 1 layer hoặc không có multiprocessing, tính trực tiếp
    if len(by_layer) == 1:
        layer, segs = next(iter(by_layer.items()))
        _, res = _process_fittings_for_layer((layer, segs, tolerance, stock_length))
        result[layer] = res
        return result

    import concurrent.futures
    import os
    
    tasks = [(layer, segs, tolerance, stock_length) for layer, segs in by_layer.items()]
    max_workers = min(len(tasks), os.cpu_count() or 4)
    
    # Sử dụng ProcessPoolExecutor để tính song song từng layer, vượt rào GIL
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        for layer, res in executor.map(_process_fittings_for_layer, tasks):
            result[layer] = res

    return result


def block_scale(entity):
    """Tỷ lệ (xscale, yscale, zscale) của một INSERT, mặc định 1.0 khi không khai báo."""
    return (
        float(getattr(entity.dxf, "xscale", 1.0) or 1.0),
        float(getattr(entity.dxf, "yscale", 1.0) or 1.0),
        float(getattr(entity.dxf, "zscale", 1.0) or 1.0),
    )


def insert_repeat_count(entity) -> int:
    """Số bản sao THẬT mà một INSERT tạo ra trên bản vẽ (MINSERT = lưới hàng x cột).

    DXF cho phép một entity INSERT duy nhất nhân bản thành lưới `row_count x column_count`
    (lệnh MINSERT của AutoCAD, hay dùng cho dàn đèn trần, dàn đầu phun sprinkler). Đếm mỗi
    INSERT là 1 thiết bị sẽ bóc thiếu cả một dàn — 1 thay vì 40 bộ đèn.
    """
    rows = int(getattr(entity.dxf, "row_count", 1) or 1)
    cols = int(getattr(entity.dxf, "column_count", 1) or 1)
    return max(1, rows) * max(1, cols)


# Khoảng cách tối đa giữa hai nét của cùng một tuyến vẽ kiểu 2 nét song song (đơn vị bản
# vẽ, theo mm). 2000 mm phủ hết cỡ ống gió/ống nước thường gặp; xa hơn nữa thì hai nét
# nhiều khả năng là hai tuyến riêng biệt chứ không phải hai mép của một tuyến.
DEFAULT_DOUBLE_LINE_MAX_WIDTH = 2000.0

# Hai đoạn phải chồng nhau ít nhất bằng tỷ lệ này (trên đoạn ngắn hơn) mới coi là hai mép
# của cùng một tuyến, tránh bắt nhầm hai tuyến chỉ tình cờ chạm nhau một khúc ngắn.
_DOUBLE_LINE_MIN_OVERLAP_RATIO = 0.6

# Sai lệch góc tối đa (độ) để coi hai đoạn là song song.
_PARALLEL_ANGLE_TOLERANCE_DEG = 2.0


def detect_double_line_runs(segments, max_width: float = DEFAULT_DOUBLE_LINE_MAX_WIDTH,
                            min_separation: float = JOINT_TOLERANCE) -> dict:
    """Ước tính chiều dài bị TÍNH ĐÔI do tuyến vẽ bằng 2 nét song song, theo từng layer.

    Ống gió và ống nước cỡ lớn hầu như luôn được thể hiện bằng HAI nét song song (hai mép
    ống) chứ không phải một đường tâm. Cộng dồn chiều dài hình học sẽ ra **gấp đôi** chiều
    dài tuyến thật, và bảng dự toán không có bất kỳ dấu hiệu nào để nhận ra.

    Đây chỉ là CẢNH BÁO, không tự trừ: hai tuyến MEPF riêng biệt chạy song song sát nhau
    (rất phổ biến — cấp và hồi đi cùng trục) trông y hệt hai mép của một ống. Máy không
    phân biệt được hai trường hợp này, nên quyết định cuối cùng phải thuộc về kỹ sư; sai
    lầm ở đây mà tự trừ thì lại thành bóc THIẾU đúng một nửa.

    Trả về `{layer: chiều dài nghi tính đôi}`. Thuật toán gom đoạn theo (layer, hướng) rồi
    chỉ so các đoạn có khoảng lệch vuông góc đủ nhỏ, nên không phải so từng cặp toàn bản vẽ.
    """
    buckets = {}
    for seg in segments:
        (x1, y1, _), (x2, y2, _) = seg["start"], seg["end"]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        # Góc không hướng (0..180): hai nét của một ống có thể được vẽ ngược chiều nhau.
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        key = (seg["layer"], round(angle / _PARALLEL_ANGLE_TOLERANCE_DEG))
        ux, uy = dx / length, dy / length
        # Pháp tuyến: khoảng lệch của hai đường song song chính là hiệu `offset`.
        offset = -uy * x1 + ux * y1
        t1, t2 = ux * x1 + uy * y1, ux * x2 + uy * y2
        buckets.setdefault(key, []).append(
            {"offset": offset, "lo": min(t1, t2), "hi": max(t1, t2), "length": length}
        )

    doubled = {}
    for (layer, _), items in buckets.items():
        items.sort(key=lambda it: it["offset"])
        used = [False] * len(items)
        for i, first in enumerate(items):
            if used[i]:
                continue
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                second = items[j]
                gap = second["offset"] - first["offset"]
                if gap > max_width:
                    break  # đã sắp xếp theo offset nên các đoạn sau còn xa hơn
                if gap < min_separation:
                    continue  # trùng khít nhau là hình học overkill, đã có cảnh báo riêng
                overlap = min(first["hi"], second["hi"]) - max(first["lo"], second["lo"])
                if overlap <= 0:
                    continue
                if overlap < _DOUBLE_LINE_MIN_OVERLAP_RATIO * min(first["length"], second["length"]):
                    continue
                used[i] = used[j] = True
                doubled[layer] = doubled.get(layer, 0.0) + overlap
                break

    return doubled


def effective_block_name(entity, doc) -> tuple:
    """Tên THẬT của block mà một INSERT tham chiếu: `(tên hiển thị, có phải block ẩn danh)`.

    Block động (dynamic block) — cách vẽ phổ biến nhất của hồ sơ hiện đại: một block "VAN"
    duy nhất có tham số chọn cỡ DN50/DN80/DN100 — được AutoCAD lưu mỗi biến thể thành một
    block ẩn danh tên `*U12`, `*U13`... Đếm theo `insert.dxf.name` sẽ:

    - xé một chủng loại thiết bị thành nhiều dòng rời rạc, và
    - đặt tên hạng mục là `*U12` — vô nghĩa với người đọc dự toán.

    Tên gốc nằm ở XDATA `AcDbBlockRepBTag` của INSERT, trỏ bằng handle tới block_record của
    định nghĩa block động. Không tra được thì trả về chính tên ẩn danh kèm cờ để hàm gọi
    CẢNH BÁO — thà nói rõ "có N thiết bị chưa xác định được tên" còn hơn in ra `*U12`.
    """
    name = getattr(entity.dxf, "name", "") or ""
    if not name.startswith("*"):
        return name, False

    try:
        for code, value in entity.get_xdata("AcDbBlockRepBTag"):
            if code != 1005:
                continue
            target = doc.entitydb.get(value) if doc is not None else None
            real_name = getattr(getattr(target, "dxf", None), "name", "") if target else ""
            if real_name and not real_name.startswith("*"):
                return real_name, False
    except Exception:
        pass
    return name, True


def _insert_transform(entity):
    """(gốc chèn, xscale, yscale, rotation độ, hệ số nhân chiều dài) của một INSERT."""
    insert = entity.dxf.insert
    base = (insert.x, insert.y, getattr(insert, "z", 0.0) or 0.0)
    xscale, yscale, _ = block_scale(entity)
    rotation = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
    # Tỷ lệ không đều (xscale != yscale) không có một hệ số chiều dài đúng cho mọi hướng;
    # trung bình hình học là xấp xỉ hợp lý và không thiên lệch theo hướng tuyến.
    length_factor = math.sqrt(abs(xscale * yscale)) or 1.0
    return base, xscale, yscale, rotation, length_factor


def _transform_point(point, base, xscale, yscale, rotation_deg):
    """Đưa một điểm từ hệ tọa độ nội bộ của block về hệ tọa độ không gian chứa nó."""
    x, y = point[0] * xscale, point[1] * yscale
    if rotation_deg:
        rad = math.radians(rotation_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
    z = point[2] if len(point) > 2 else 0.0
    return (x + base[0], y + base[1], z + base[2])


def _minsert_offsets(entity, rotation_deg):
    """Vị trí gốc của từng bản sao trong lưới MINSERT, tính từ gốc chèn (0,0) là bản đầu."""
    rows = max(1, int(getattr(entity.dxf, "row_count", 1) or 1))
    cols = max(1, int(getattr(entity.dxf, "column_count", 1) or 1))
    if rows == 1 and cols == 1:
        return [(0.0, 0.0)]
    row_gap = float(getattr(entity.dxf, "row_spacing", 0.0) or 0.0)
    col_gap = float(getattr(entity.dxf, "column_spacing", 0.0) or 0.0)
    rad = math.radians(rotation_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    offsets = []
    for r in range(rows):
        for c in range(cols):
            dx, dy = c * col_gap, r * row_gap
            offsets.append((dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a))
    return offsets


def explode_insert(entity, doc, max_depth: int = 8, _depth: int = 0):
    """Nội dung THẬT bên trong một INSERT: `(segments, nested_inserts)`.

    Hồ sơ MEPF thực tế đóng gói rất nhiều thứ thành Block: một cụm WC, một dàn đèn, một
    module ống gió lặp lại. Duyệt modelspace mà chỉ đếm INSERT rồi bỏ qua ruột của nó thì
    **toàn bộ ống/dây vẽ bên trong block bị bóc thiếu 100%** — không có một dòng cảnh báo
    nào, vì bảng khối lượng vẫn ra bình thường với các tuyến vẽ trực tiếp.

    Hàm này bung block về hệ tọa độ bản vẽ chính (tỷ lệ, góc xoay, lưới MINSERT), đệ quy
    qua block lồng nhau (có `max_depth` chặn block tự tham chiếu vòng), và áp quy tắc
    layer của CAD: entity nằm trên layer "0" bên trong block **thừa hưởng layer của
    INSERT** — bỏ qua quy tắc này thì cả tuyến ống bị dồn hết về layer "0" và mất hệ.

    XREF được bỏ qua ở đây vì đã có đường xử lý riêng (`cad_loader.resolve_xref_segments`),
    gộp cả hai sẽ tính đôi.

    `nested_inserts` là danh sách `(tên block, số lượng)` của thiết bị nằm trong block, để
    hàm gọi cộng vào bảng đếm thiết bị.
    """
    segments, nested_inserts = [], []
    if _depth >= max_depth or doc is None:
        return segments, nested_inserts

    name = getattr(entity.dxf, "name", "")
    try:
        block = doc.blocks.get(name)
    except Exception:
        block = None
    if block is None or getattr(block, "is_xref", False):
        return segments, nested_inserts

    base, xscale, yscale, rotation, length_factor = _insert_transform(entity)
    host_layer = getattr(entity.dxf, "layer", "0")
    copies = _minsert_offsets(entity, rotation)

    for child in block:
        child_layer = getattr(child.dxf, "layer", "0")
        # Layer "0" trong block là layer "trong suốt": thực thể hiện lên theo layer của INSERT.
        effective_layer = host_layer if child_layer == "0" else child_layer

        if child.dxftype() == "INSERT":
            sub_segments, sub_inserts = explode_insert(child, doc, max_depth, _depth + 1)
            # Mỗi INSERT lồng bên trong là một thiết bị được chèn thật, đếm nó y như một
            # INSERT ở modelspace (nhân theo lưới MINSERT của chính nó).
            child_name, _ = effective_block_name(child, doc)
            sub_inserts = [(child_name, insert_repeat_count(child))] + list(sub_inserts)
            for dx, dy in copies:
                for seg in sub_segments:
                    item = dict(seg)
                    item["start"] = _transform_point(seg["start"], (base[0] + dx, base[1] + dy, base[2]),
                                                     xscale, yscale, rotation)
                    item["end"] = _transform_point(seg["end"], (base[0] + dx, base[1] + dy, base[2]),
                                                   xscale, yscale, rotation)
                    item["length"] = seg["length"] * length_factor
                    if item.get("layer", "0") == "0":
                        item["layer"] = host_layer
                    segments.append(item)
                nested_inserts.extend(sub_inserts)
            continue

        for seg in entity_segments(child):
            for dx, dy in copies:
                item = dict(seg)
                item["layer"] = effective_layer
                item["start"] = _transform_point(seg["start"], (base[0] + dx, base[1] + dy, base[2]),
                                                 xscale, yscale, rotation)
                item["end"] = _transform_point(seg["end"], (base[0] + dx, base[1] + dy, base[2]),
                                               xscale, yscale, rotation)
                item["length"] = seg["length"] * length_factor
                segments.append(item)

    return segments, nested_inserts


def _subdivide_bulge(x1, y1, x2, y2, bulge, n=8):
    """Rời rạc hóa một cung bulge thành `n` điểm trung gian, để dùng cho giao cắt
    hình học (thẳng-thẳng) mà không phải giải phương trình đường tròn."""
    if not bulge:
        return [(x1, y1), (x2, y2)]
    theta = 4.0 * math.atan(abs(bulge))
    chord = math.hypot(x2 - x1, y2 - y1)
    half = math.sin(theta / 2.0)
    if half == 0 or chord == 0:
        return [(x1, y1), (x2, y2)]
    radius = chord / (2.0 * half)
    # Tâm cung: vuông góc với dây cung, lệch về phía xác định bởi dấu bulge.
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    dx, dy = x2 - x1, y2 - y1
    dist_to_center = math.sqrt(max(radius ** 2 - (chord / 2.0) ** 2, 0.0))
    nx, ny = -dy / chord, dx / chord
    sign = 1.0 if bulge > 0 else -1.0
    cx, cy = mx + sign * nx * dist_to_center, my + sign * ny * dist_to_center

    a1 = math.atan2(y1 - cy, x1 - cx)
    sweep = theta if bulge > 0 else -theta
    points = []
    for i in range(n + 1):
        a = a1 + sweep * (i / n)
        points.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return points


def entity_points_3d(entity, arc_segments: int = 12):
    """Chuỗi điểm (x, y, z) xấp xỉ hình dạng một entity, RỜI RẠC HÓA cung cong.

    Dùng cho các phép toán chỉ cần giao cắt/hình chiếu gần đúng (clash detection) mà
    không cần chiều dài chính xác — ở đó việc quy cung về nhiều đoạn thẳng ngắn là đủ,
    tránh phải giải giao điểm đường tròn-đường tròn.
    """
    dxftype = entity.dxftype()
    try:
        if dxftype == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            z1 = getattr(s, "z", 0.0) or 0.0
            z2 = getattr(e, "z", 0.0) or 0.0
            return [(s.x, s.y, z1), (e.x, e.y, z2)]

        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            verts = _polyline_vertices(entity)
            if len(verts) < 2:
                return []
            pairs = list(zip(verts[:-1], verts[1:]))
            if getattr(entity, "closed", False) or getattr(entity.dxf, "flags", 0) & 1:
                pairs.append((verts[-1], verts[0]))
            points = []
            for (x1, y1, z1, bulge), (x2, y2, z2, _) in pairs:
                sub = _subdivide_bulge(x1, y1, x2, y2, bulge, n=arc_segments) if bulge else [(x1, y1), (x2, y2)]
                for k, (px, py) in enumerate(sub):
                    t = k / max(1, len(sub) - 1)
                    points.append((px, py, z1 + (z2 - z1) * t))
            return points

        if dxftype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            a1 = math.radians(float(entity.dxf.start_angle))
            a2 = math.radians(float(entity.dxf.end_angle))
            sweep = (a2 - a1) % (2 * math.pi) or (2 * math.pi)
            return [(center.x + radius * math.cos(a1 + sweep * i / arc_segments),
                    center.y + radius * math.sin(a1 + sweep * i / arc_segments), z)
                   for i in range(arc_segments + 1)]

        if dxftype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            z = getattr(center, "z", 0.0) or 0.0
            return [(center.x + radius * math.cos(2 * math.pi * i / arc_segments),
                    center.y + radius * math.sin(2 * math.pi * i / arc_segments), z)
                   for i in range(arc_segments + 1)]
    except Exception:  # pragma: no cover - entity dị dạng trong file thực tế
        return []
    return []


def is_scaled(entity, tolerance: float = 1e-6) -> bool:
    """Block có bị insert với tỷ lệ khác 1 hay không.

    Đếm đúng số lượng nhưng bỏ qua tỷ lệ là bẫy thật: một đèn 600x600 chèn ở scale 1.5 vẫn
    được đếm là "1 bộ đèn 600x600" trong khi kích thước thực tế trên bản vẽ là 900x900.
    """
    return any(abs(s - 1.0) > tolerance for s in block_scale(entity))


def plain_entity_text(entity) -> str:
    """Nội dung chữ THUẦN của một TEXT/MTEXT, đã bỏ mã định dạng của CAD.

    MTEXT lưu kèm mã điều khiển ngay trong chuỗi (`{\\fArial|b1;Ống uPVC \\pxqc;Ø110}`) và
    TEXT dùng mã thoát riêng (`%%c` cho Ø, `%%d` cho độ). Đọc thẳng chuỗi thô thì tên hạng
    mục trong bảng dự toán ra đúng cả đống ký tự điều khiển — vừa không đọc được, vừa làm
    `calc_boq_cost` không khớp nổi từ khóa đơn giá nên hạng mục bị đánh "CHƯA CÓ ĐƠN GIÁ"
    dù bảng giá có đủ.
    """
    try:
        text = entity.plain_text()
    except Exception:
        try:
            text = entity.dxf.text if entity.dxftype() == "TEXT" else getattr(entity, "text", "")
        except Exception:
            return ""
    return (text or "").strip()


def parse_nominal_half_width(text: str) -> float | None:
    """Suy ra bán kính/nửa bề rộng danh nghĩa (mm) từ ghi chú kích thước gần một tuyến ống/
    gió trên bản vẽ (VD "Ø110", "DN100", "600x400") — dùng để clash detection xét được BỀ
    DÀY thật của tuyến thay vì chỉ coi tuyến là một đường tâm không có kích thước.

    Ống gió chữ nhật lấy cạnh LỚN HƠN chia đôi (giả định xấu nhất khi tuyến quay hướng bất
    kỳ trên mặt bằng — dùng cạnh nhỏ sẽ bỏ sót va chạm thật khi tuyến nằm ngang cạnh lớn).
    Trả về None nếu ghi chú không chứa con số kích thước nào nhận diện được — clash
    detection sẽ KHÔNG suy đoán kích thước trong trường hợp đó, tránh báo động giả.
    """
    if not text:
        return None
    duct = _DUCT_RE.search(text)
    if duct:
        a, b = float(duct.group(1)), float(duct.group(2))
        return max(a, b) / 2.0
    dia = _DIAMETER_RE.search(text)
    if dia:
        return float(dia.group(1)) / 2.0
    return None

def build_topology_graph(segments: list):
    """Chuyển đổi danh sách các đoạn ống thành Đồ thị (Graph).
    Sử dụng NetworkX để mô hình hóa Topology.
    """
    import networkx as nx
    G = nx.Graph()
    for seg in segments:
        if "start" in seg and "end" in seg:
            p1 = (round(seg["start"][0], 1), round(seg["start"][1], 1), round(seg["start"][2], 1))
            p2 = (round(seg["end"][0], 1), round(seg["end"][1], 1), round(seg["end"][2], 1))
            if p1 != p2:
                G.add_edge(p1, p2, weight=seg.get("length", 0.0))
    return G

def detect_disconnected_pipes(segments: list) -> list:
    """Phát hiện các đầu ống bị hở (không kết nối)."""
    G = build_topology_graph(segments)
    open_endpoints = []
    for node, degree in G.degree():
        if degree == 1:
            open_endpoints.append(node)
    return open_endpoints
