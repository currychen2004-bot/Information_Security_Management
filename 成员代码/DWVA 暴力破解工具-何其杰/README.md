### DVWA Brute Force多线程暴力破解
何其杰 2022212887
### 1. 工具定位

这是一个针对 DVWA Brute Force模块开发的自动化暴力破解脚本，目标是：

- 通过多线程提高爆破效率
- 支持单用户名定向爆破或用户名字典组合爆破
- 自动识别并保存破解成功的账号密码

### 2. 文件说明

- `dvwa_brute.py`：主程序脚本
- `username.txt`：可选，用于多用户爆破模式的用户名列表
- `password.txt`：必需，密码字典文件
- `result.txt`：输出文件，自动记录破解成功获取到的用户名和密码

### 3. 爆破逻辑

脚本采用多线程并发模式，核心流程如下：

- 连接预检机制：
在正式爆破前，脚本会先发送一个探测请求。如果发现被重定向到登录页或 Cookie 无效，将直接报错停止，避免无效操作。
- 任务组合逻辑：
  - 若通过参数传入单个用户名，则进行“1对多”爆破。
  - 若未传入用户名，脚本自动读取 `username.txt`，进行“多对多”组合爆破。
- 特征匹配：
实时监控响应正文。若命中成功标志 `Welcome to the password protected area`，则判定破解成功。
- 异常处理：
精准捕获 `queue.Empty` 异常，确保在高并发竞争下，不产生堆栈报错。

### 4. 使用前准备

1. 启动 DVWA 环境
2. 登录账户，将 Security Level设置为 Low
3. 点击左侧菜单进入 Brute Force页面
4. 复制浏览器中的 Cookie

### 5. 运行示例

在当前目录下执行命令：

模式 A：单用户爆破

```sh
python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" -c "Cookie" -user "admin" -w "password.txt"
```

模式 B：多用户爆破

```sh
python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" -c "Cookie" -user "username.txt" -w "password.txt"
```

可选参数：

- `-t`：设置并发线程数，默认5

### 6. 输出结果说明

- 控制台输出：
  - `破解成功！`：并在屏幕上直接显示用户名和密码。
  - `破解失败！`：字典尝试完毕仍未命中。
<img width="1875" height="303" alt="image" src="https://github.com/user-attachments/assets/5d5794ea-a8e9-44a0-922d-122ad30e2194" />
<img width="1856" height="405" alt="image" src="https://github.com/user-attachments/assets/b81acd9d-653d-42cf-84c5-11efa3370fa5" />

- 文件记录：
破解成功后，结果会将用户名和密码追加写入 `result.txt`。
<img width="512" height="157" alt="image" src="https://github.com/user-attachments/assets/80a6799f-0c90-49e1-bace-03f3fa3a3f71" />

### 7. 局限性

- 难度限制：仅支持 Low 级别（Low 级别使用 GET 请求且无 CSRF Token 保护）。
- 网络依赖：若线程数设置过高且靶场响应慢，可能导致请求丢包，建议根据实际响应速度调整 `-t` 参数。
