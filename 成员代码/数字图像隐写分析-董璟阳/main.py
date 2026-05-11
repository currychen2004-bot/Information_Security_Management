# encoding=utf-8
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from PIL import Image
import math
import os

# 解决中文显示问题
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ---------- 1. 基础工具函数 ----------
def get_binary_msg(msg):
    """将字符串转换为二进制字符串"""
    return ''.join([bin(ord(i)).replace('0b', '').zfill(8) for i in msg])

def psnr(img1, img2):
    """计算峰值信噪比 (PSNR)"""
    img1 = np.float64(img1)
    img2 = np.float64(img2)
    mse = np.mean((img1 - img2) ** 2)
    if mse < 1.0e-10: return 100
    return 20 * math.log10(255.0 / math.sqrt(mse))

# ---------- 2. 图像预处理 (灰度化与缩放) ----------
def preprocess_image(input_path, output_path):
    print(f"正在处理图像: {input_path}...")
    img = cv2.imread(input_path, cv2.IMREAD_GRAYSCALE)
    # 缩放到 512x512
    img_resized = cv2.resize(img, (512, 512), interpolation=cv2.INTER_LINEAR)
    cv2.imwrite(output_path, img_resized)
    return img_resized

# ---------- 3. LSB 信息隐藏 (嵌入) ----------
def lsb_encode(img_path, msg, output_path):
    print(f"正在嵌入信息: '{msg}'...")
    img = Image.open(img_path).convert('RGB')
    width, height = img.size
    hide_msg = get_binary_msg(msg)
    length = len(hide_msg)
    count = 0
    
    img_data = np.array(img)
    for i in range(width):
        for j in range(height):
            if count >= length: break
            pixel = list(img_data[j, i]) # 注意PIL和numpy坐标对应
            for c in range(3): # R, G, B
                if count < length:
                    pixel[c] = (pixel[c] & ~1) | int(hide_msg[count])
                    count += 1
            img_data[j, i] = tuple(pixel)
        if count >= length: break
    
    stego_img = Image.fromarray(img_data)
    stego_img.save(output_path)
    return output_path

# ---------- 4. LSB 信息提取 ----------
def lsb_decode(stego_path, msg_len):
    print("正在提取秘密信息...")
    img = Image.open(stego_path).convert('RGB')
    width, height = img.size
    bit_len = msg_len * 8
    count = 0
    result_bin = ""
    
    img_data = np.array(img)
    for i in range(width):
        for j in range(height):
            if count >= bit_len: break
            pixel = img_data[j, i]
            for c in range(3):
                if count < bit_len:
                    result_bin += str(pixel[c] & 1)
                    count += 1
        if count >= bit_len: break
    
    decoded_msg = "".join([chr(int(result_bin[i:i+8], 2)) for i in range(0, len(result_bin), 8)])
    return decoded_msg

# ---------- 5. 位平面分析 ----------
def bit_plane_analysis(img_path):
    print("正在生成位平面分析图...")
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    for i in range(8):
        mask = np.uint8(1 << i)
        bit_plane = (np.bitwise_and(img, mask) > 0) * 255
        
        plt.figure(figsize=(6, 3))
        plt.subplot(1, 2, 1)
        plt.imshow(np.bitwise_and(img, np.bitwise_not(mask)), cmap='gray')
        plt.title(f'去掉第{i+1}位平面')
        plt.subplot(1, 2, 2)
        plt.imshow(bit_plane, cmap='gray')
        plt.title(f'仅第{i+1}位平面')
        plt.show()

# ---------- 6. DCT 频域失真模拟 ----------
def dct_distortion_demo(img_path):
    print("正在进行DCT变换与重构...")
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    img_f32 = np.float32(img)
    img_dct = cv2.dct(img_f32)
    
    # 模拟失真：高频系数置零
    # 保留左上角 LOW_FREQUENCY_SIZE × LOW_FREQUENCY_SIZE 的低频区域
    LOW_FREQUENCY_SIZE = 300

    rows, cols = img_dct.shape
    img_dct_copy = img_dct.copy()

    # 去除高频信息，仅保留低频部分
    img_dct_copy[LOW_FREQUENCY_SIZE:, :] = 0
    img_dct_copy[:, LOW_FREQUENCY_SIZE:] = 0
    
    img_r = cv2.idct(img_dct_copy)
    img_r = np.clip(img_r, 0, 255).astype(np.uint8)
    
    plt.figure(figsize=(10, 4))
    plt.subplot(131); plt.imshow(img, 'gray'); plt.title('原始灰度图')
    plt.subplot(132); plt.imshow(np.log(np.abs(img_dct)+1), cmap='hot'); plt.title('DCT系数(对数域)')
    plt.subplot(133); plt.imshow(img_r, 'gray'); plt.title('DCT重构(失真后)')
    plt.show()

# ---------- 执行流程 ----------
if __name__ == "__main__":
    # 定义文件名
    orig_name = 'bupt.bmp'
    gray_name = 'buptgray.bmp'
    stego_name = 'buptgraystego.bmp'
    secret_text = "BUPTshahexiaoqu"

    if os.path.exists(orig_name):
        # 1. 预处理
        preprocess_image(orig_name, gray_name)
        
        # 2. 嵌入与提取
        lsb_encode(gray_name, secret_text, stego_name)
        extracted = lsb_decode(stego_name, len(secret_text))
        print(f"提取出的信息: {extracted}")
        
        # 3. 质量评价
        img_orig = cv2.imread(gray_name)
        img_stego = cv2.imread(stego_name)
        val_psnr = psnr(img_orig, img_stego)
        print(f"嵌入后的峰值信噪比 (PSNR): {val_psnr:.2f} dB")
        
        # 4. 位平面分析 (仅展示前2个示例)
        bit_plane_analysis(gray_name)
        
        # 5. DCT 演示
        dct_distortion_demo(gray_name)
    else:
        print(f"请确保当前目录下有 {orig_name} 文件")
