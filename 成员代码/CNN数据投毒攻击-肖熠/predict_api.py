import os
import torch

# ==========================================
# 新增模块：安全模型预测接口 (AI 辅助开发)
# 功能：对外提供安全的模型加载与推理功能
# ==========================================

def secure_predict(model_filename, image_tensor):
    """
    安全的模型加载与预测接口
    """
    # 1. 强制设定安全的沙箱目录 (只允许在这个目录里读模型)
    safe_model_dir = os.path.abspath("./models")
    
    # 2. 拼接并解析出真实的绝对路径
    # 注意：防止黑客传入类似 "../../etc/passwd" 的目录穿越攻击
    target_path = os.path.abspath(os.path.join(safe_model_dir, model_filename))
    
    # 3. 安全约束一：路径前缀强制校验
    if not target_path.startswith(safe_model_dir):
        raise PermissionError("安全拦截：检测到非法的目录穿越尝试！")
        
    # 4. 安全约束二：白名单校验后缀
    if not target_path.endswith(".pth"):
        raise ValueError("安全拦截：只允许加载 .pth 格式的模型文件！")
        
    # 5. 安全约束三：切断 Pickle 反序列化 RCE 攻击链
    # 强制设置 weights_only=True，即使模型被投毒篡改，也不会执行恶意代码
    print(f"安全检查通过，正在安全加载模型: {target_path}")
    try:
        model_weights = torch.load(target_path, map_location='cpu', weights_only=True)
        return "预测成功 (模拟返回)"
    except Exception as e:
        return f"加载失败: {str(e)}"

if __name__ == "__main__":
    # 模拟黑客攻击测试
    try:
        # 黑客尝试路径穿越，意图读取上一级目录的敏感文件
        secure_predict("../../../etc/shadow", None)
    except Exception as e:
        print(f"黑客攻击被拦截：{e}")