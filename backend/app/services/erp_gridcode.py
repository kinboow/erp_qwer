"""
ERP GridCode — 自定义二维方块码

将条形码内容（如 "20260506-033|8d9a3a83cc034f"）直接编码为一个 18×18 的
黑白方格图案，打印在发货单上。摄像头拍照后通过轮廓检测 → 透视矫正 → 读取
方格 → 解码，还原出原始文本。

特性：
- 数据自包含：无需数据库查找，永不过期
- 鲁棒检测：厚边框 + 定位角标，透视/模糊/JPEG压缩均可识别
- 内容校验：CRC-8 防止误读

网格结构 (18×18):
┌── 黑色边框 (1格) ─────────────────────┐
│ ┌── 白色间隔 (1格) ─────────────────┐ │
│ │ ■■          定位角标(2×2)      ■■ │ │
│ │ ■■          top-left/right     ■■ │ │
│ │                                   │ │
│ │     14×14 内部区域 = 数据格子      │ │
│ │     (跳过4个角的2×2 = 180bit)     │ │
│ │                                   │ │
│ │ ■■          bottom-left        □□ │ │ ← 右下角白色(定向标记)
│ │ ■■                             □□ │ │
│ └───────────────────────────────────┘ │
└───────────────────────────────────────┘

定向：3个角为黑色2×2，右下角为白色2×2，用于检测旋转。
"""

from __future__ import annotations

import io
import logging
import time
from base64 import b64encode
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 编码参数
# ---------------------------------------------------------------------------
CHARSET = "0123456789abcdef-|ABCDEFGHIJKLMNOPQRSTUVWXYZ_. "
_CHAR_TO_IDX = {c: i for i, c in enumerate(CHARSET)}
_IDX_TO_CHAR = {i: c for i, c in enumerate(CHARSET)}
BITS_PER_CHAR = 6  # 2^6 = 64，覆盖 CHARSET（当前 50 字符）

GRID_INNER = 14   # 14×14 内部数据区
GRID_BORDER = 2   # 外框 = 1格黑 + 1格白
GRID_TOTAL = GRID_INNER + GRID_BORDER * 2  # 18×18

# 定位角标占用的 2×2 区域坐标 (相对于内部 14×14，row, col)
_FINDER_TL = [(0, 0), (0, 1), (1, 0), (1, 1)]
_FINDER_TR = [(0, 12), (0, 13), (1, 12), (1, 13)]
_FINDER_BL = [(12, 0), (12, 1), (13, 0), (13, 1)]
_FINDER_BR = [(12, 12), (12, 13), (13, 12), (13, 13)]
_ALL_FINDERS = set(_FINDER_TL + _FINDER_TR + _FINDER_BL + _FINDER_BR)

# 数据格子数量 = 14×14 - 16 = 180
DATA_BITS = GRID_INNER * GRID_INNER - len(_ALL_FINDERS)  # 180
MAX_CONTENT_LEN = (DATA_BITS - 6 - 8) // BITS_PER_CHAR   # (180-6-8)/6 = 27

# 如果内容可能超过 27 字符，用更紧凑的编码
# 实际条码内容约 30 字符，改用 5bit（支持 18 种字符 0-9a-f-|）
# 重新定义
_COMPACT_CHARSET = "0123456789abcdef-|"
_COMPACT_CHAR_TO_IDX = {c: i for i, c in enumerate(_COMPACT_CHARSET)}
_COMPACT_IDX_TO_CHAR = {i: c for i, c in enumerate(_COMPACT_CHARSET)}
COMPACT_BITS = 5  # 2^5 = 32 >= 18
MAX_CONTENT_LEN_COMPACT = (DATA_BITS - 6 - 8) // COMPACT_BITS  # (180-6-8)/5 = 33


# ---------------------------------------------------------------------------
# CRC-8 校验
# ---------------------------------------------------------------------------
def _crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07
            else:
                crc <<= 1
            crc &= 0xFF
    return crc


# ---------------------------------------------------------------------------
# 编码：文本 → bit 列表
# ---------------------------------------------------------------------------
def _encode_bits(content: str) -> list[int]:
    """将内容编码为 DATA_BITS 长度的 bit 列表。"""
    content = content.lower().strip()
    n = len(content)
    if n > MAX_CONTENT_LEN_COMPACT:
        raise ValueError(f"内容过长: {n} > {MAX_CONTENT_LEN_COMPACT}")

    bits: list[int] = []

    # 6 bit 长度
    for i in range(5, -1, -1):
        bits.append((n >> i) & 1)

    # 每字符 5 bit
    raw_bytes = bytearray()
    for ch in content:
        idx = _COMPACT_CHAR_TO_IDX.get(ch)
        if idx is None:
            raise ValueError(f"不支持的字符: '{ch}' (支持: {_COMPACT_CHARSET})")
        for i in range(COMPACT_BITS - 1, -1, -1):
            bits.append((idx >> i) & 1)
        raw_bytes.append(idx)

    # CRC-8 校验 (对长度+内容字节)
    crc_input = bytes([n]) + bytes(raw_bytes)
    crc = _crc8(crc_input)
    for i in range(7, -1, -1):
        bits.append((crc >> i) & 1)

    # 补零到 DATA_BITS
    while len(bits) < DATA_BITS:
        bits.append(0)

    return bits[:DATA_BITS]


def _decode_bits(bits: list[int]) -> Optional[str]:
    """从 DATA_BITS 长度的 bit 列表解码内容，校验失败返回 None。"""
    if len(bits) < DATA_BITS:
        return None

    pos = 0

    # 6 bit 长度
    n = 0
    for i in range(6):
        n = (n << 1) | bits[pos + i]
    pos += 6
    if n == 0 or n > MAX_CONTENT_LEN_COMPACT:
        return None

    # 每字符 5 bit
    chars = []
    raw_bytes = bytearray()
    for _ in range(n):
        idx = 0
        for i in range(COMPACT_BITS):
            idx = (idx << 1) | bits[pos + i]
        pos += COMPACT_BITS
        ch = _COMPACT_IDX_TO_CHAR.get(idx)
        if ch is None:
            return None
        chars.append(ch)
        raw_bytes.append(idx)

    # CRC-8 校验
    crc_stored = 0
    for i in range(8):
        crc_stored = (crc_stored << 1) | bits[pos + i]
    pos += 8

    crc_input = bytes([n]) + bytes(raw_bytes)
    crc_calc = _crc8(crc_input)
    if crc_calc != crc_stored:
        return None

    return "".join(chars)


# ---------------------------------------------------------------------------
# 网格操作
# ---------------------------------------------------------------------------
def _data_cell_order() -> list[tuple[int, int]]:
    """返回内部 14×14 中数据格子的 (row, col) 坐标列表（按读取顺序）。"""
    cells = []
    for r in range(GRID_INNER):
        for c in range(GRID_INNER):
            if (r, c) not in _ALL_FINDERS:
                cells.append((r, c))
    return cells


_DATA_CELLS = _data_cell_order()
assert len(_DATA_CELLS) == DATA_BITS


def _bits_to_grid(bits: list[int]) -> np.ndarray:
    """将 bit 列表写入 18×18 网格（0=黑, 255=白）。"""
    grid = np.zeros((GRID_TOTAL, GRID_TOTAL), dtype=np.uint8)

    # 外框：第0行/列 和 第17行/列 = 黑 (已经是0)
    # 内框：第1行/列 和 第16行/列 = 白
    grid[1, 1:GRID_TOTAL - 1] = 255
    grid[GRID_TOTAL - 2, 1:GRID_TOTAL - 1] = 255
    grid[1:GRID_TOTAL - 1, 1] = 255
    grid[1:GRID_TOTAL - 1, GRID_TOTAL - 2] = 255

    # 内部区域先填白
    grid[2:2 + GRID_INNER, 2:2 + GRID_INNER] = 255

    # 定位角标：TL, TR, BL = 黑色 2×2; BR = 白色 2×2 (已经是白)
    for r, c in _FINDER_TL + _FINDER_TR + _FINDER_BL:
        grid[2 + r, 2 + c] = 0  # 黑

    # BR 保持白色（255），已设置

    # 写入数据 bit
    for i, (r, c) in enumerate(_DATA_CELLS):
        grid[2 + r, 2 + c] = 0 if bits[i] else 255

    return grid


def _grid_to_bits(grid: np.ndarray) -> Optional[list[int]]:
    """从 18×18 网格读取数据 bit 列表。grid 应已二值化（0=黑, 255=白）。
    
    返回 (bits, rotation) 或 None（检测失败）。
    """
    # 提取内部 14×14
    inner = grid[2:2 + GRID_INNER, 2:2 + GRID_INNER]

    # 检测 4 个角标确定旋转
    def _corner_is_black(arr: np.ndarray, positions):
        return all(arr[r, c] < 128 for r, c in positions)

    def _corner_is_white(arr: np.ndarray, positions):
        return all(arr[r, c] >= 128 for r, c in positions)

    # 尝试 4 种旋转
    for rot in range(4):
        rotated = np.rot90(inner, rot)
        # TL, TR, BL 应为黑; BR 应为白
        tl = [(0, 0), (0, 1), (1, 0), (1, 1)]
        tr = [(0, 12), (0, 13), (1, 12), (1, 13)]
        bl = [(12, 0), (12, 1), (13, 0), (13, 1)]
        br = [(12, 12), (12, 13), (13, 12), (13, 13)]
        if (_corner_is_black(rotated, tl) and _corner_is_black(rotated, tr) and
                _corner_is_black(rotated, bl) and _corner_is_white(rotated, br)):
            # 读取数据
            bits = []
            for r, c in _DATA_CELLS:
                bits.append(1 if rotated[r, c] < 128 else 0)
            return bits

    return None


# ---------------------------------------------------------------------------
# 图片生成
# ---------------------------------------------------------------------------
def generate_gridcode_image(content: str, cell_px: int = 20) -> io.BytesIO:
    """生成 GridCode PNG 图片（含白色边距），返回 BytesIO。"""
    bits = _encode_bits(content)
    grid = _bits_to_grid(bits)

    # 缩放到实际像素
    img_size = GRID_TOTAL * cell_px
    padding = cell_px * 2  # 白色边距（2格宽）
    total_size = img_size + padding * 2
    img = np.ones((total_size, total_size), dtype=np.uint8) * 255  # 白色背景

    for r in range(GRID_TOTAL):
        for c in range(GRID_TOTAL):
            y1, y2 = padding + r * cell_px, padding + (r + 1) * cell_px
            x1, x2 = padding + c * cell_px, padding + (c + 1) * cell_px
            img[y1:y2, x1:x2] = grid[r, c]

    _, png_buf = cv2.imencode(".png", img)
    buf = io.BytesIO(png_buf.tobytes())
    buf.seek(0)
    return buf


def gridcode_to_data_url(content: str, cell_px: int = 20) -> str:
    """生成 GridCode 的 data:image/png;base64,... URL。"""
    buf = generate_gridcode_image(content, cell_px)
    return f"data:image/png;base64,{b64encode(buf.getvalue()).decode('ascii')}"


# ---------------------------------------------------------------------------
# 图片检测 & 解码
# ---------------------------------------------------------------------------
def _order_corners(pts: np.ndarray) -> np.ndarray:
    """将 4 个角点排序为 [TL, TR, BR, BL]。"""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _extract_grid(cv_img, corners: np.ndarray) -> Optional[np.ndarray]:
    """从图像中提取并矫正 18×18 网格。"""
    size = GRID_TOTAL * 10  # 矫正后每格 10px
    dst = np.array([
        [0, 0], [size, 0], [size, size], [0, size]
    ], dtype=np.float32)
    M = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(cv_img, M, (size, size))
    if len(warped.shape) == 3:
        warped = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # 二值化
    _, bw = cv2.threshold(warped, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 采样每格中心像素，生成 18×18 矩阵
    grid = np.zeros((GRID_TOTAL, GRID_TOTAL), dtype=np.uint8)
    for r in range(GRID_TOTAL):
        for c in range(GRID_TOTAL):
            cy = r * 10 + 5
            cx = c * 10 + 5
            # 取 5×5 区域中值
            region = bw[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
            grid[r, c] = 255 if np.mean(region) > 128 else 0
    return grid


def _verify_border(grid: np.ndarray, threshold: float = 0.65) -> bool:
    """验证外框格式：第0/17行列大部分黑，第1/16行列大部分白。
    
    threshold: 允许的最低匹配比例 (0.65 = 65%)
    """
    # 外框黑 (行0/17, 列0/17)
    outer_cells = np.concatenate([
        grid[0, :], grid[-1, :], grid[1:-1, 0], grid[1:-1, -1]
    ])
    outer_black_ratio = np.sum(outer_cells < 128) / len(outer_cells)

    # 内框白 (行1/16, 列1/16)
    inner_cells = np.concatenate([
        grid[1, 1:-1], grid[-2, 1:-1], grid[2:-2, 1], grid[2:-2, -2]
    ])
    inner_white_ratio = np.sum(inner_cells >= 128) / len(inner_cells)

    return outer_black_ratio >= threshold and inner_white_ratio >= threshold


def decode_gridcode_from_bytes(image_bytes: bytes) -> list[str]:
    """从图片字节检测并解码 GridCode，返回解码结果列表。"""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    cv_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if cv_img is None:
        return []
    return decode_gridcode_from_image(cv_img)


def decode_gridcode_from_image(cv_img) -> list[str]:
    """从 OpenCV 图像检测并解码 GridCode。

    多层策略：全图 → CLAHE增强 → 四角裁切放大
    """
    started = time.perf_counter()
    results = []

    # 多层尝试
    layers = _build_detection_layers(cv_img)
    for layer_name, layer_img in layers:
        found = _detect_in_layer(layer_img)
        if found:
            for text in found:
                if text not in results:
                    results.append(text)
            logger.info("GridCode: %s 解码成功 → %s (%.3fs)", layer_name, results, time.perf_counter() - started)
            return results

    if not results:
        logger.debug("GridCode: 所有层均未检测到 (%.3fs)", time.perf_counter() - started)
    return results


def _build_detection_layers(cv_img) -> list[tuple[str, any]]:
    """构建多层检测图像。"""
    h, w = cv_img.shape[:2]
    layers = [("全图", cv_img)]

    # CLAHE 增强
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    layers.append(("CLAHE", cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)))

    # 四角裁切放大
    rw, rh = 0.5, 0.5
    cw, ch = max(int(w * rw), 200), max(int(h * rh), 200)
    corners = [
        ("右上", max(0, w - cw), 0, w, min(h, ch)),
        ("右下", max(0, w - cw), max(0, h - ch), w, h),
        ("左上", 0, 0, min(w, cw), min(h, ch)),
        ("左下", 0, max(0, h - ch), min(w, cw), h),
    ]
    for name, x1, y1, x2, y2 in corners:
        crop = cv_img[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        scaled = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2), interpolation=cv2.INTER_LANCZOS4)
        layers.append((f"角落[{name}]", scaled))

    return layers


def _expand_corners(corners: np.ndarray, factor: float) -> np.ndarray:
    """将四边形角点向外扩展 factor 比例（基于中心）。"""
    center = corners.mean(axis=0)
    expanded = center + (corners - center) * (1.0 + factor)
    return expanded.astype(np.float32)


def _try_decode_from_corners(cv_img, corners: np.ndarray) -> Optional[str]:
    """尝试从给定角点透视矫正并解码 GridCode，成功返回文本，失败返回 None。"""
    grid = _extract_grid(cv_img, corners)
    if grid is None:
        return None

    # 宽松边框验证（通过则优先尝试，不通过也尝试解码靠CRC兜底）
    border_ok = _verify_border(grid, threshold=0.55)

    bits = _grid_to_bits(grid)
    if bits is not None:
        text = _decode_bits(bits)
        if text:
            return text

    # 即使角标不匹配，也尝试直接读取（可能边框抽样偏移）
    if not border_ok:
        return None

    return None


def _detect_in_layer(cv_img) -> list[str]:
    """在单张图像中检测所有 GridCode。"""
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY) if len(cv_img.shape) == 3 else cv_img

    # 多种二值化方式，提取轮廓合并
    thresh_images = []
    _, bw1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    thresh_images.append(bw1)
    bw2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 10)
    thresh_images.append(bw2)
    _, bw3 = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    thresh_images.append(bw3)
    # 非反转版本（找白色区域外围的黑色边框）
    _, bw4 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    thresh_images.append(bw4)

    contours = []
    for bw in thresh_images:
        cnts, _ = cv2.findContours(bw, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(cnts)

    results = []
    h, w = gray.shape[:2]
    min_side = min(w, h) * 0.02
    max_side = min(w, h) * 0.8

    for cnt in contours:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue

        area = cv2.contourArea(approx)
        side = area ** 0.5
        if side < min_side or side > max_side:
            continue

        if not cv2.isContourConvex(approx):
            continue

        rect = cv2.minAreaRect(approx)
        rw2, rh2 = rect[1]
        if min(rw2, rh2) == 0:
            continue
        aspect = max(rw2, rh2) / min(rw2, rh2)
        if aspect > 1.6:
            continue

        corners = _order_corners(approx.reshape(4, 2))

        # 尝试多种扩展比例：
        # 0% = 原始轮廓（如果刚好是完整外框）
        # 12-15% = 轮廓是内部白框，需要向外扩展1格到黑框
        for expand in [0.0, 0.06, 0.12, 0.15, 0.20, 0.25]:
            exp_corners = _expand_corners(corners, expand) if expand > 0 else corners
            # 检查扩展后角点不超出图片
            if (exp_corners[:, 0].min() < 0 or exp_corners[:, 1].min() < 0 or
                    exp_corners[:, 0].max() >= w or exp_corners[:, 1].max() >= h):
                continue
            text = _try_decode_from_corners(cv_img, exp_corners)
            if text:
                if text not in results:
                    results.append(text)
                break  # 这个轮廓已解码成功

        if results:
            break  # 找到就停

    return results
