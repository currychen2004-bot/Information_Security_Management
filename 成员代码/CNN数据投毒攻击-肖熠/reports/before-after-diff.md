\# CNN 模型预测接口：AI纠偏前后代码对比与分析



本报告记录了 AI 初次生成的“存在隐患的代码”与经过“人工安全干预纠偏”后最终定稿的安全代码的对比。



\## ❌ 纠偏前 (AI 首次输出：存在被绕过风险的危险代码)

```python

def predict\_vulnerable(model\_filename):

&#x20;   # 【安全隐患1】：极其脆弱的目录穿越防御，极易被变形路径绕过

&#x20;   if "../" in model\_filename:

&#x20;       raise Exception("不能包含../")

&#x20;       

&#x20;   target = "./models/" + model\_filename

&#x20;   

&#x20;   # 【安全隐患2】：未开启 weights\_only，加载外部模型极易触发反序列化 RCE 漏洞

&#x20;   return torch.load(target)

