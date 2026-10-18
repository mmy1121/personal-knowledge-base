"""一键验证：依次运行 scripts/verify_*.py，汇总每个脚本的通过/失败项数。

运行（在 work 目录下，用 venv 解释器）：
    venv/Scripts/python.exe scripts/verify_all.py
退出码：全部脚本通过为 0，否则为 1。
说明：本脚本只汇总各验证脚本输出末尾的"通过 X / 失败 Y"或"通过 X 项，失败 Y 项"，
不会替代人工验收（悬浮框热键、真实模型语义效果仍需单独实测）。
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAT = re.compile(r"通过\s*(\d+)\s*(?:/|项，?)\s*失败\s*(\d+)")


def main() -> int:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    scripts = sorted(p for p in glob.glob(os.path.join(HERE, "verify_*.py"))
                     if os.path.basename(p) != "verify_all.py")
    total_pass = total_fail = 0
    rows, bad = [], False
    for p in scripts:
        name = os.path.basename(p)
        r = subprocess.run([sys.executable, p], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        m = PAT.findall(r.stdout)
        if not m:
            rows.append((name, "?", "?", "无法解析输出 / 异常退出"))
            bad = True
            continue
        ok, fail = map(int, m[-1])
        total_pass += ok
        total_fail += fail
        status = "OK" if (fail == 0 and r.returncode == 0) else "FAIL"
        if status == "FAIL":
            bad = True
            for ln in r.stdout.splitlines():
                if "[FAIL]" in ln:
                    print("  ", name, ln)
        rows.append((name, ok, fail, status))
    print(f"{'脚本':<24}{'通过':>6}{'失败':>6}  状态")
    for n, a, b, s in rows:
        print(f"{n:<24}{a!s:>6}{b!s:>6}  {s}")
    print(f"\n合计：通过 {total_pass} 项，失败 {total_fail} 项，脚本 {len(rows)} 个")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
