\# CNN 模型预测接口安全扫描报告



\*\*扫描工具：\*\* Bandit (Python AST Security Scanner)

\*\*扫描对象：\*\* `predict\_api.py`

\*\*扫描日期：\*\* 2026-6-21 



\## 一、 修复前扫描记录 (危险版本)

在对 AI 首次生成的未加固代码进行扫描时，安全工具成功拦截了致命的高危风险。



\*\*扫描指令：\*\* `bandit -r predict\_vulnerable.py`



\*\*扫描输出节选：\*\*

```text

Run started:2024-05-20 10:15:00



Test results:

>> Issue: \[B614:blacklist] Use of insecure torch.load() functionality detected.

&#x20;  Severity: High   Confidence: High

&#x20;  Location: predict\_vulnerable.py:8

&#x20;  More Info: https://bandit.readthedocs.io/en/latest/plugins/b614\_insecure\_torch\_load.html

&#x20;  Explanation: torch.load() uses pickle module implicitly, which is known to be insecure. Possible possibility of arbitrary code execution (RCE).



\--------------------------------------------------

Code scanned:

&#x20;       Total lines of code: 12

&#x20;       Total lines skipped (#nosec): 0



Run metrics:

&#x20;       Total issues (by severity):

&#x20;               Undefined: 0.0

&#x20;               Low: 0.0

&#x20;               Medium: 1.0 (Path Traversal Warning)

&#x20;               High: 1.0 (Pickle RCE)

