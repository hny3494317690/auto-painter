import time
import math
import subprocess
import tkinter as tk
from tkinter import filedialog
import cv2
import numpy as np
from core.utils import imread_unicode, resize_to_max_side
import os
import pyautogui


# DRAW_BUTTON = "left"
DRAW_BUTTON = "right"

# ----------------------------
# Config
# ----------------------------
STYLE = "edges"   # 可选: "edges" | "sketch_mono" | "flat_poster"

# sketch_mono 参数（单色素描）
SKETCH_MORPH = 0.5        # 线条加粗/连贯：0=不做，1=轻微，2=明显
SKETCH_CONTRAST = 1.2   # 对比度(>1 更黑白分明)
SKETCH_BRIGHTNESS = 0   # 亮度偏移（可正可负）
SKETCH_INVERT = False   # 是否反相（让线为白）

# flat_poster 参数（平涂分块）
FLAT_COLORS = 8         # kmeans 聚类色数（越小越“平涂”）
FLAT_BLUR = 7           # bilateral 滤波直径（越大越保边平滑）
FLAT_EDGE_THICKEN = 1   



DRAW_SPEED_SEC = 0.0025          # 每次 move 的间隔(秒)，太快不稳定可设 0.001~0.01
POINT_STRIDE = 1              # 路径点抽样：每隔 N 个点取 1 个（越大越快但更粗糙）
MIN_CONTOUR_LEN = 2          # 过滤很短的轮廓（噪声）
CANNY1, CANNY2 = 50, 150      # Canny 阈值，可调
BLUR_KSIZE = 5                # 高斯模糊核大小，可调
SIMPLIFY_EPS = 0.5            # 轮廓简化强度（越大点越少，线越“直”）
INVERT_FOR_DRAW = True        # True: 让线为白(255)背景黑(0) 便于提取，最终画的是线

JOIN_DIST_PX = 5          # 在“原图坐标系”里，两段之间小于这个距离就不断笔连接
ALLOW_BRIDGE_LINE = True  # 距离略大也不断笔，用直线桥接（可能产生不想要的连线）
BRIDGE_MAX_DIST_PX = 15   # 允许桥接的最大距离（原图坐标）


def to_sketch_mono(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 轻微去噪，保留边缘
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)

    # 调整对比度/亮度（让线更“干净”）
    gray = cv2.convertScaleAbs(gray, alpha=SKETCH_CONTRAST, beta=SKETCH_BRIGHTNESS)

    # 自适应阈值：更像铅笔素描的黑白线
    bw = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,  # blockSize，越大越平滑
        2    # C，越大越“白”
    )

    # 让线条为白色前景（你的 sketch_to_contours 需要白为前景）
    # adaptiveThreshold 输出默认是黑线白底，所以要反相成“白线黑底”
    sketch = 255 - bw

    if SKETCH_MORPH > 0:
        k = 2 if SKETCH_MORPH == 1 else 3
        kernel = np.ones((k, k), np.uint8)
        sketch = cv2.dilate(sketch, kernel, iterations=1)  # 加粗一点更好画

    if SKETCH_INVERT:
        sketch = 255 - sketch

    return sketch

def to_pencil(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (BLUR_KSIZE, BLUR_KSIZE), 0)
    edges = cv2.Canny(gray, CANNY1, CANNY2)
    sketch = edges if INVERT_FOR_DRAW else 255 - edges
    return sketch
    
def to_flat_poster_edges(img_bgr):
    # 保边平滑，减少纹理噪声，让分块更稳定
    smooth = cv2.bilateralFilter(img_bgr, d=FLAT_BLUR, sigmaColor=80, sigmaSpace=80)

    # k-means 量化颜色（平涂风格关键）
    Z = smooth.reshape((-1, 3)).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    K = int(FLAT_COLORS)
    _ret, labels, centers = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    centers = centers.astype(np.uint8)
    quant = centers[labels.flatten()].reshape(smooth.shape)

    # 对量化后的图取边缘（色块边界）
    gray = cv2.cvtColor(quant, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    edges = cv2.Canny(gray, 40, 120)

    # 边界线加粗一点
    if FLAT_EDGE_THICKEN > 0:
        k = 2 if FLAT_EDGE_THICKEN == 1 else 3
        kernel = np.ones((k, k), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

    # edges 本身就是白线黑底
    return edges


def apply_style_defaults():
    global SIMPLIFY_EPS, MIN_CONTOUR_LEN

    if STYLE == "flat_poster":
        SIMPLIFY_EPS = max(SIMPLIFY_EPS, 2.0)
        MIN_CONTOUR_LEN = max(MIN_CONTOUR_LEN, 10)

    if STYLE == "sketch_mono":
        SIMPLIFY_EPS = min(SIMPLIFY_EPS, 1.0)
        MIN_CONTOUR_LEN = min(MIN_CONTOUR_LEN, 10)

# ----------------------------
# Image -> line sketch
# ----------------------------
def generate_sketch(img_path, style, params):
    img_bgr = imread_unicode(img_path)
    if img_bgr is None:
        raise RuntimeError("图片读取失败，请换一张或检查路径。")
    
    img_bgr, scale = resize_to_max_side(img_bgr, target_max_side=900, min_side=400)
    print(f"图片已缩放，scale={scale:.3f}，新尺寸={img_bgr.shape[1]}x{img_bgr.shape[0]}")

    apply_style_defaults()
    
    if style == "pencil":        
        sketch = to_pencil(img_bgr)

    elif style == "sketch_mono":
        sketch = to_sketch_mono(img_bgr)

    elif style == "flat_poster":
        sketch =  to_flat_poster_edges(img_bgr)
    else :
        raise ValueError(f"Unknown STYLE: {style}")
    
    h, w = sketch.shape[:2]

    # 保存预览
    out_dir = os.path.join(os.path.dirname(img_path), "out_sketch")
    os.makedirs(out_dir, exist_ok=True)
    preview_path = os.path.join(out_dir, "sketch.png")
    cv2.imwrite(preview_path, sketch)
    print(f"线稿预览已保存：{preview_path}")
    
    return preview_path