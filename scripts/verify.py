"""CareerAgent 标准验证脚本。

用法：python scripts/verify.py

打包了 AGENTS.md 中要求的最低验证门槛：语法检查、模块 import 检查、
config.yaml 格式检查、依赖一致性检查。任何一步失败都会在最后汇总里
标红，不会中途退出，方便一次性看到所有问题。

模块 import 检查是动态的：只检查 agent/ 目录下当前实际存在的 .py
文件，而不是写死的模块名单。这意味着在整合过程的不同阶段（比如
Phase 3 之前 agent/extractor.py 还不存在），这一项都能给出真实、
不会因为"文件还没整合进来"而误报的结果。

如果 tests/ 目录下已经有测试文件，会自动追加一项 pytest 检查。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results: list[tuple[str, bool, str]] = []


def run(name: str, cmd: list[str]) -> None:
    """执行一条检查命令，记录结果。"""
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=60
        )
        ok = proc.returncode == 0
        detail = proc.stdout.strip() if ok else (proc.stderr.strip() or proc.stdout.strip())
        results.append((name, ok, detail[:500]))
    except Exception as exc:  # noqa: BLE001
        results.append((name, False, str(exc)))


def main() -> int:
    agent_dir = ROOT / "agent"
    agent_module_files = sorted(
        p for p in agent_dir.glob("*.py") if p.stem not in {"__init__", "init"}
    )
    agent_module_names = [p.stem for p in agent_module_files]

    py_files = ["main.py"] + [str(p) for p in agent_dir.glob("*.py")]
    run("语法检查 (py_compile)", [sys.executable, "-m", "py_compile", *py_files])

    if agent_module_names:
        import_stmt = (
            "import " + ", ".join(f"agent.{name}" for name in agent_module_names)
            + "; print('all imports ok')"
        )
        check_name = f"模块 import 检查 ({', '.join(agent_module_names)})"
        run(check_name, [sys.executable, "-c", import_stmt])
    else:
        results.append(("模块 import 检查", True, "agent/ 下暂无可检查模块"))

    run(
        "config.yaml 格式检查",
        [
            sys.executable,
            "-c",
            "import yaml; yaml.safe_load(open('config.yaml', encoding='utf-8')); print('config ok')",
        ],
    )

    run("依赖一致性检查 (pip check)", [sys.executable, "-m", "pip", "check"])

    tests_dir = ROOT / "tests"
    if tests_dir.exists() and any(tests_dir.glob("test_*.py")):
        run("单元测试 (pytest)", [sys.executable, "-m", "pytest", "tests/", "-q"])

    print("\n" + "=" * 60)
    print("CareerAgent 验证结果")
    print("=" * 60)
    all_ok = True
    for name, ok, detail in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status}  {name}")
        if not ok:
            all_ok = False
            print(f"        {detail}")
    print("=" * 60)

    if not all_ok:
        print("存在未通过项，请先修复再继续下一步整合。")
        return 1

    print("全部通过。如需真实运行冒烟测试，且本地 Ollama 已启动，执行：")
    print('  echo q | python main.py')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())