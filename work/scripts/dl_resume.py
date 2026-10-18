"""带 Range 续传与重试的下载器（仅标准库）。用法: dl_resume.py URL OUT EXPECTED_SIZE"""
import os
import sys
import time
import urllib.request

url, out, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
deadline = time.time() + 100  # 单次调用上限，避免再被工具超时截断
attempt = 0
while time.time() < deadline:
    have = os.path.getsize(out) if os.path.exists(out) else 0
    if have >= expected:
        break
    attempt += 1
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-", "User-Agent": "probe"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status == 200 and have:  # 服务器不支持续传，重头开始
                have = 0
                open(out, "wb").close()
            with open(out, "ab") as f:
                while True:
                    chunk = r.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    if time.time() > deadline:
                        break
    except Exception as e:
        print(f"attempt {attempt} error: {type(e).__name__}: {e}")
        time.sleep(2)
size = os.path.getsize(out) if os.path.exists(out) else 0
print(f"size={size} expected={expected} complete={size == expected}")
