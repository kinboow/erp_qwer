"""
自研二维码定位 + 矫正 + 解码器
专为「拣货单拍照 → 微信群压缩图」场景优化

流程：
1. 轮廓检测找 Finder Pattern（三个大方块）
2. 透视矫正把歪的二维码拉正
3. 多种二值化清洗图像
4. 补白边确保 quiet zone
5. 喂给 ZXing / pyzbar 解码
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Finder Pattern 检测 — 纯 OpenCV 轮廓分析
# ---------------------------------------------------------------------------
def _is_square_like(contour, min_area: int = 80) -> bool:
    """判断轮廓是否近似正方形"""
    area = cv2.contourArea(contour)
    if area < min_area:
        return False
    _, (w, h), _ = cv2.minAreaRect(contour)
    if w == 0 or h == 0:
        return False
    ratio = max(w, h) / min(w, h)
    return ratio < 1.6


def _has_nested_contours(hierarchy, idx: int) -> bool:
    """检查轮廓是否有嵌套子轮廓（Finder Pattern 特征：大方块套小方块）"""
    child = hierarchy[0][idx][2]
    if child == -1:
        return False
    grandchild = hierarchy[0][child][2]
    return grandchild != -1


def _find_finder_patterns(gray: np.ndarray) -> list[np.ndarray]:
    """在灰度图中寻找 QR 码的三个 Finder Pattern 中心点"""
    results = []

    for block_size in (31, 51, 71):
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, block_size, 8,
        )
        binary_inv = cv2.bitwise_not(binary)

        contours, hierarchy = cv2.findContours(
            binary_inv, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE,
        )
        if hierarchy is None:
            continue

        candidates = []
        for i, cnt in enumerate(contours):
            if not _is_square_like(cnt):
                continue
            if not _has_nested_contours(hierarchy, i):
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            area = cv2.contourArea(cnt)
            candidates.append((cx, cy, area, cnt))

        if len(candidates) >= 3:
            # 按面积从大到小，取前 3 个面积相近的
            candidates.sort(key=lambda c: c[2], reverse=True)
            # 筛选面积相近的组合
            for i in range(len(candidates)):
                group = [candidates[i]]
                ref_area = candidates[i][2]
                for j in range(len(candidates)):
                    if i == j:
                        continue
                    ratio = candidates[j][2] / ref_area if ref_area > 0 else 0
                    if 0.3 < ratio < 3.0:
                        group.append(candidates[j])
                if len(group) >= 3:
                    results = group[:3]
                    break

        if results:
            break

    return results


def _order_finder_points(centers: list[tuple[int, int]]) -> Optional[np.ndarray]:
    """将三个 Finder Pattern 中心排列为 [TL, TR, BL] 顺序。

    QR 码的三个 Finder Pattern 形成直角三角形：
    - TL (Top-Left) 是直角顶点 → 到其他两个点的距离之和最小
    - TR 和 BL 通过叉积区分方向
    """
    if len(centers) < 3:
        return None

    pts = np.array(centers[:3], dtype="float32")

    # 计算每个点到其他两个点的距离之和
    dist_sums = []
    for i in range(3):
        d = sum(np.linalg.norm(pts[i] - pts[j]) for j in range(3) if i != j)
        dist_sums.append(d)

    # 三角形中，直角顶点（TL）到其他两点的距离之和 = 两条直角边之和
    # 而对边（TR-BL 连线）上的两个点到对方的距离包含了斜边，距离和更大
    # 所以 TL = 距离和最大的那个点（斜边对面的顶点）
    tl_idx = int(np.argmax(dist_sums))
    others = [i for i in range(3) if i != tl_idx]

    tl = pts[tl_idx]
    a, b = pts[others[0]], pts[others[1]]

    # 叉积区分 TR 和 BL
    cross = (a[0] - tl[0]) * (b[1] - tl[1]) - (a[1] - tl[1]) * (b[0] - tl[0])
    if cross > 0:
        tr, bl = a, b
    else:
        tr, bl = b, a

    return np.array([tl, tr, bl], dtype="float32")


def _estimate_fourth_point(tl, tr, bl) -> np.ndarray:
    """估算第四个点 BR = TR + BL - TL"""
    return tr + bl - tl


def _perspective_warp(gray: np.ndarray, finder_pts: np.ndarray, output_size: int = 400) -> np.ndarray:
    """透视矫正：把检测到的 QR 区域拉正为正方形"""
    tl, tr, bl = finder_pts[0], finder_pts[1], finder_pts[2]
    br = _estimate_fourth_point(tl, tr, bl)

    src = np.array([tl, tr, br, bl], dtype="float32")
    margin = output_size * 0.08  # 留一点边距
    dst = np.array([
        [margin, margin],
        [output_size - margin, margin],
        [output_size - margin, output_size - margin],
        [margin, output_size - margin],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(gray, M, (output_size, output_size),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=255)
    return warped


# ---------------------------------------------------------------------------
# 图像清洗变体
# ---------------------------------------------------------------------------
def _make_clean_variants(gray_img: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """生成多种二值化 / 增强变体"""
    variants = []

    # 原始灰度
    variants.append(("gray", gray_img))

    # CLAHE 增强
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray_img)
    variants.append(("clahe", clahe))

    # 自适应二值化（多种参数）
    for bs in (21, 31, 51):
        for c in (5, 8, 12):
            bw = cv2.adaptiveThreshold(gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, bs, c)
            variants.append((f"adaptive_{bs}_{c}", bw))

    # Otsu
    _, otsu = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    # CLAHE + Otsu
    _, clahe_otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("clahe_otsu", clahe_otsu))

    return variants


def _add_quiet_zone(gray_img: np.ndarray, border: int = 40) -> np.ndarray:
    """给图片加白色 quiet zone 边框"""
    return cv2.copyMakeBorder(gray_img, border, border, border, border,
                              cv2.BORDER_CONSTANT, value=255)


# ---------------------------------------------------------------------------
# 解码尝试
# ---------------------------------------------------------------------------
def _try_zxing_decode(img) -> list[str]:
    """ZXing 解码"""
    try:
        import zxingcpp
        from PIL import Image as PILImage

        if isinstance(img, np.ndarray):
            pil_img = PILImage.fromarray(img)
        else:
            pil_img = img

        results = zxingcpp.read_barcodes(
            pil_img,
            formats=zxingcpp.BarcodeFormat.QRCode,
            try_rotate=True,
            try_downscale=True,
            try_invert=True,
            binarizer=zxingcpp.Binarizer.LocalAverage,
            return_errors=False,
        )
        return [r.text.strip() for r in results if getattr(r, "text", "").strip()]
    except Exception:
        return []


def _try_pyzbar_decode(gray_img: np.ndarray) -> list[str]:
    """pyzbar 解码"""
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        from PIL import Image as PILImage
        pil = PILImage.fromarray(gray_img)
        results = pyzbar_decode(pil)
        return [r.data.decode("utf-8").strip() for r in results if r.data]
    except Exception:
        return []


def _try_opencv_decode(gray_img: np.ndarray) -> list[str]:
    """OpenCV QRCodeDetector 解码"""
    try:
        bgr = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR) if len(gray_img.shape) == 2 else gray_img
        detector = cv2.QRCodeDetector()
        val, _, _ = detector.detectAndDecode(bgr)
        if val and val.strip():
            return [val.strip()]
    except Exception:
        pass
    return []


def _try_all_decoders(img: np.ndarray, label: str) -> list[str]:
    """依次用所有解码器尝试"""
    for decoder_name, decoder_fn in [
        ("zxing", _try_zxing_decode),
        ("pyzbar", _try_pyzbar_decode),
        ("opencv", _try_opencv_decode),
    ]:
        res = decoder_fn(img)
        if res:
            logger.info("qr_decoder: %s → %s 成功: %s", label, decoder_name, res)
            return res
    return []


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def decode_qr_custom(image_bytes: bytes) -> list[str]:
    """
    自研 QR 解码管线。

    1. 转灰度
    2. 轮廓检测找 Finder Pattern
    3. 透视矫正
    4. 多种二值化清洗
    5. 加白边
    6. ZXing / pyzbar / OpenCV 解码

    返回解码文本列表（空列表表示失败）。
    """
    started = time.perf_counter()

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    color_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if color_img is None:
        return []

    gray = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    logger.info("qr_decoder: 开始处理 %dx%d", w, h)

    # --- 阶段 1：找 Finder Pattern ---
    finder_centers = _find_finder_patterns(gray)
    if len(finder_centers) >= 3:
        centers = [(c[0], c[1]) for c in finder_centers[:3]]
        ordered = _order_finder_points(centers)
        if ordered is not None:
            logger.info("qr_decoder: 检测到 Finder Pattern, 执行透视矫正")

            # --- 阶段 2：透视矫正 ---
            for output_size in (400, 500, 600):
                warped = _perspective_warp(gray, ordered, output_size)

                # --- 阶段 3：多种清洗 + 解码 ---
                for var_name, cleaned in _make_clean_variants(warped):
                    bordered = _add_quiet_zone(cleaned, border=40)
                    res = _try_all_decoders(bordered, f"warped_{output_size}_{var_name}")
                    if res:
                        logger.info("qr_decoder: 成功！耗时 %.3fs", time.perf_counter() - started)
                        return res

    # --- 阶段 4：如果 Finder Pattern 检测失败，回退到角落扫描 ---
    logger.info("qr_decoder: Finder Pattern 未找到或矫正后仍失败，尝试角落区域扫描")

    corner_configs = [
        # (x_start_ratio, y_start_ratio, w_ratio, h_ratio)
        (0.60, 0.70, 0.40, 0.30),  # 右下角（最常见位置）
        (0.60, 0.00, 0.40, 0.30),  # 右上角
        (0.00, 0.70, 0.40, 0.30),  # 左下角
        (0.00, 0.00, 0.40, 0.30),  # 左上角
        (0.55, 0.60, 0.45, 0.40),  # 右下角（更大范围）
        (0.55, 0.00, 0.45, 0.40),  # 右上角（更大范围）
    ]

    for ci, (xr, yr, wr, hr) in enumerate(corner_configs):
        x1, y1 = int(w * xr), int(h * yr)
        x2, y2 = min(w, x1 + int(w * wr)), min(h, y1 + int(h * hr))
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        # 在角落子图上重新找 Finder Pattern
        sub_finders = _find_finder_patterns(crop)
        if len(sub_finders) >= 3:
            sub_centers = [(c[0], c[1]) for c in sub_finders[:3]]
            sub_ordered = _order_finder_points(sub_centers)
            if sub_ordered is not None:
                for output_size in (400, 500):
                    warped = _perspective_warp(crop, sub_ordered, output_size)
                    for var_name, cleaned in _make_clean_variants(warped):
                        bordered = _add_quiet_zone(cleaned, border=40)
                        res = _try_all_decoders(bordered, f"corner_{ci}_warped_{output_size}_{var_name}")
                        if res:
                            logger.info("qr_decoder: 角落扫描成功！耗时 %.3fs", time.perf_counter() - started)
                            return res

        # 没找到 Finder Pattern → 直接用角落区域暴力缩放 + 解码
        for scale in (2, 3, 4):
            scaled = cv2.resize(crop, (crop.shape[1] * scale, crop.shape[0] * scale),
                                interpolation=cv2.INTER_LANCZOS4)
            for var_name, cleaned in _make_clean_variants(scaled):
                bordered = _add_quiet_zone(cleaned, border=30)
                res = _try_all_decoders(bordered, f"corner_{ci}_{scale}x_{var_name}")
                if res:
                    logger.info("qr_decoder: 角落暴力扫描成功！耗时 %.3fs", time.perf_counter() - started)
                    return res

    elapsed = time.perf_counter() - started
    logger.warning("qr_decoder: 所有方案均失败，耗时 %.3fs", elapsed)
    return []
