import time
import math
import subprocess
import tkinter as tk
from tkinter import filedialog
from imread_unicode import imread_unicode

import cv2
import numpy as np

import pyautogui
import keyboard
from mouseapi import move_abs, button_down, button_up

def calibrate_canvas_rect():
    """
    通过热键让用户用鼠标指向画布左上、右下
    """
    print("\n== 画布校准 ==")
    print("把鼠标移动到【画布左上角】然后按 F8；再移动到【画布右下角】按 F9。按 ESC 终止。")

    p1 = None
    p2 = None

    while p1 is None:
        if keyboard.is_pressed("esc"):
            raise SystemExit("用户终止")
        if keyboard.is_pressed("f8"):
            p1 = pyautogui.position()
            print(f"已记录左上角: {p1}")
            time.sleep(0.3)

    while p2 is None:
        if keyboard.is_pressed("esc"):
            raise SystemExit("用户终止")
        if keyboard.is_pressed("f9"):
            p2 = pyautogui.position()
            print(f"已记录右下角: {p2}")
            time.sleep(0.3)

    left = min(p1.x, p2.x)
    top = min(p1.y, p2.y)
    right = max(p1.x, p2.x)
    bottom = max(p1.y, p2.y)

    width = right - left
    height = bottom - top

    if width < 50 or height < 50:
        raise ValueError("画布区域太小，可能没选对。请重试。")

    return left, top, width, height

def draw_strokes_in_paint(strokes, img_w, img_h, canvas_rect):
    canvas_left, canvas_top, canvas_w, canvas_h = canvas_rect

    # ✅ 计算等比绘制区域（在用户框选区域内部居中、保持比例）
    draw_left, draw_top, draw_w, draw_h = compute_aspect_fit_rect(
        img_w, img_h, canvas_left, canvas_top, canvas_w, canvas_h, padding=2
    )
    print(f"等比绘制区域：left={draw_left} top={draw_top} w={draw_w} h={draw_h}")

    print("\n== 开始绘画 ==")
    print("请确认：画图窗口已在前台，并选择了【铅笔】工具。")
    print("开始后鼠标会被接管；按 ESC 紧急停止。\n")
    time.sleep(1.0)

    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = True

    total = len(strokes)
    for i, pts in enumerate(strokes, 1):
        if keyboard.is_pressed("esc"):
            raise SystemExit("用户终止")

        # 起点移动（用原生 move）
        x0, y0 = pts[0]
        sx0, sy0 = map_point_aspect(x0, y0, img_w, img_h, draw_left, draw_top, draw_w, draw_h)
        move_abs(sx0, sy0)

        button_down(DRAW_BUTTON)

        for (x, y) in pts[1:]:
            if keyboard.is_pressed("esc"):
                button_up(DRAW_BUTTON)
                raise SystemExit("用户终止")

            sx, sy = map_point_aspect(x, y, img_w, img_h, draw_left, draw_top, draw_w, draw_h)
            move_abs(sx, sy)

            time.sleep(DRAW_SPEED_SEC)

        button_up(DRAW_BUTTON)

        if i % 10 == 0 or i == total:
            print(f"进度：{i}/{total} 笔")

    print("\n完成。")


def reorder_and_merge_paths(paths, join_dist_px=6, allow_bridge_line=True, bridge_max_dist_px=20):
    """
    输入: paths: List[np.ndarray shape=(N,2)]，坐标在“原图像素坐标系”
    输出: strokes: List[List[np.ndarray]] 或更简单：List[np.ndarray]（已合并成更长的点序列）

    这里直接输出 strokes: List[np.ndarray]，每个 stroke 是一笔连续的点序列。
    """
    if not paths:
        return []

    remaining = [p.copy() for p in paths if len(p) >= 2]
    strokes = []

    # 从最长的开始（也可以从任意开始）
    remaining.sort(key=lambda p: -len(p))

    current_stroke = remaining.pop(0)
    strokes.append(current_stroke)

    while remaining:
        cur_end = strokes[-1][-1]  # 当前笔尖（原图坐标）

        # 找到与 cur_end 最近的 path（比较它的起点和终点）
        best_i = None
        best_reverse = False
        best_d2 = None

        for i, p in enumerate(remaining):
            p0 = p[0]
            p1 = p[-1]

            d2_start = _dist2(cur_end, p0)
            d2_end = _dist2(cur_end, p1)

            if best_d2 is None or d2_start < best_d2 or d2_end < best_d2:
                if d2_start <= d2_end:
                    best_d2 = d2_start
                    best_i = i
                    best_reverse = False
                else:
                    best_d2 = d2_end
                    best_i = i
                    best_reverse = True

        next_path = remaining.pop(best_i)
        if best_reverse:
            next_path = next_path[::-1]

        join2 = float(join_dist_px * join_dist_px)
        bridge2 = float(bridge_max_dist_px * bridge_max_dist_px)

        if best_d2 <= join2:
            # 足够近：直接不断笔拼接（避免重复点）
            strokes[-1] = np.vstack([strokes[-1], next_path[1:]])
        elif allow_bridge_line and best_d2 <= bridge2:
            # 不够近但允许桥接：在两端之间插入一个直线连接（会产生额外连线）
            strokes[-1] = np.vstack([strokes[-1], next_path])
        else:
            # 太远：新开一笔
            strokes.append(next_path)

    return strokes
