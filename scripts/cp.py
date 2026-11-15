"""Competitive programming helper: compile, test against samples, scaffold problems, log stats.

Usage (from the workspace root, or via the VS Code tasks):
    python scripts/cp.py test  <file.cpp> [--fast] [--eps 1e-6] [--timeout 5]
    python scripts/cp.py run   <file.cpp> [--fast]        # type input yourself / paste it
    python scripts/cp.py new   <path/without/.cpp>        # e.g. atcoder/abc420/c
    python scripts/cp.py listen                            # receive samples from Competitive Companion
    python scripts/cp.py stats                             # summary of notes/log.csv

Tests for  atcoder/abc420/c.cpp  live in  atcoder/abc420/tests/c/  as 1.in / 1.out, 2.in / 2.out, ...
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
TEMPLATE = ROOT / "template.cpp"
LOG = ROOT / "notes" / "log.csv"

COMPILER = "g++"
BASE_FLAGS = [
    "-std=c++20", "-DLOCAL", f"-I{ROOT / 'lib'}",
    "-Wall", "-Wextra", "-Wshadow", "-Wno-unused-const-variable",
    # Windows gives programs a 1 MB stack; judges give ~256 MB. Without this, a recursive
    # DFS on 2e5 nodes crashes locally but passes on the judge (or the other way round confuses you).
    "-Wl,--stack,268435456",
]
# Debug build (default): bounds-checked STL. v[i] out of range -> clear error instead of silent garbage.
DEBUG_FLAGS = ["-O1", "-g", "-D_GLIBCXX_DEBUG", "-D_GLIBCXX_DEBUG_PEDANTIC"]
# Fast build: what the judge roughly does. Use to sanity-check speed on big inputs.
FAST_FLAGS = ["-O2"]

GREEN, RED, YELLOW, CYAN, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"


# ---------------------------------------------------------------- build

def exe_path(src: Path, fast: bool) -> Path:
    rel = src.resolve().relative_to(ROOT) if src.resolve().is_relative_to(ROOT) else Path(src.name)
    name = "__".join(rel.with_suffix("").parts) + ("_fast" if fast else "") + ".exe"
    return BUILD / name


def compile_src(src: Path, fast: bool) -> Path | None:
    exe = exe_path(src, fast)
    deps = [src, ROOT / "lib" / "debug.h"]
    if exe.exists() and all(exe.stat().st_mtime >= d.stat().st_mtime for d in deps if d.exists()):
        return exe  # up to date
    BUILD.mkdir(exist_ok=True)
    flags = BASE_FLAGS + (FAST_FLAGS if fast else DEBUG_FLAGS)
    print(f"{DIM}compiling {src.name} ({'fast -O2' if fast else 'debug'})...{RESET}", flush=True)
    t0 = time.perf_counter()
    r = subprocess.run([COMPILER, *flags, str(src.resolve()), "-o", str(exe)])
    if r.returncode != 0:
        print(f"{RED}COMPILATION FAILED{RESET}")
        return None
    print(f"{DIM}compiled in {time.perf_counter() - t0:.1f}s{RESET}")
    return exe


# ---------------------------------------------------------------- compare

def same_output(got: str, expected: str, eps: float | None) -> bool:
    """Token-wise compare, ignoring whitespace differences (like most judges)."""
    a, b = got.split(), expected.split()
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if eps is None:
            return False
        try:
            fx, fy = float(x), float(y)
        except ValueError:
            return False
        if abs(fx - fy) > eps * max(1.0, abs(fy)):  # absolute or relative error
            return False
    return True


def first_diff(got: str, expected: str) -> str:
    gl, el = got.strip().splitlines(), expected.strip().splitlines()
    for i in range(max(len(gl), len(el))):
        g = gl[i].strip() if i < len(gl) else "<missing>"
        e = el[i].strip() if i < len(el) else "<missing>"
        if g.split() != e.split():
            return f"first difference at line {i + 1}: expected {e!r}, got {g!r}"
    return "token count differs"


def show_block(title: str, text: str, limit: int = 30) -> None:
    lines = text.rstrip("\n").splitlines()
    print(f"  {DIM}{title}:{RESET}")
    for line in lines[:limit]:
        print(f"    {line}")
    if len(lines) > limit:
        print(f"    {DIM}... ({len(lines) - limit} more lines){RESET}")
    if not lines:
        print(f"    {DIM}<empty>{RESET}")


# ---------------------------------------------------------------- commands

def tests_dir(src: Path) -> Path:
    return src.parent / "tests" / src.stem


def cmd_test(args) -> int:
    src = Path(args.file)
    if src.suffix != ".cpp" or not src.exists():
        print(f"{RED}not a .cpp file: {src}{RESET}")
        return 2
    exe = compile_src(src, args.fast)
    if exe is None:
        return 1

    tdir = tests_dir(src)
    inputs = sorted(tdir.glob("*.in"), key=lambda p: (len(p.stem), p.stem)) if tdir.exists() else []
    if not inputs:
        print(f"{YELLOW}no tests found in {tdir.relative_to(ROOT) if tdir.is_relative_to(ROOT) else tdir}{RESET}")
        print("add 1.in / 1.out there (or run: python scripts/cp.py new <path>)")
        return 1

    passed = 0
    for inp in inputs:
        out = inp.with_suffix(".out")
        expected = out.read_text() if out.exists() else None
        t0 = time.perf_counter()
        try:
            with inp.open("rb") as stdin:
                r = subprocess.run([str(exe)], stdin=stdin, capture_output=True, timeout=args.timeout)
            elapsed = time.perf_counter() - t0
            got, err, code = r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace"), r.returncode
        except subprocess.TimeoutExpired:
            print(f"{RED}TLE {RESET} test {inp.stem}  (> {args.timeout}s)")
            continue

        tag = f"test {inp.stem}  {DIM}{elapsed * 1000:.0f} ms{RESET}"
        if code != 0:
            # Windows exit codes: 0xC0000005 = access violation (bad index / null), 0xC00000FD = stack overflow
            hint = {3221225477: "access violation (out-of-bounds / bad pointer)",
                    3221225725: "stack overflow (deep recursion)",
                    3221225620: "integer division by zero",
                    3: "abort() - probably a _GLIBCXX_DEBUG bounds check, see stderr"}.get(code & 0xFFFFFFFF, "")
            print(f"{RED}RE  {RESET} {tag}  exit code {code & 0xFFFFFFFF:#x} {hint}")
            show_block("stderr", err)
        elif expected is None:
            print(f"{YELLOW}??  {RESET} {tag}  (no {out.name} - output shown)")
            show_block("output", got)
        elif same_output(got, expected, args.eps):
            passed += 1
            print(f"{GREEN}PASS{RESET} {tag}")
            if err.strip() and args.verbose:
                show_block("stderr (dbg)", err)
        else:
            print(f"{RED}FAIL{RESET} {tag}  {first_diff(got, expected)}")
            show_block("input", inp.read_text(), 15)
            show_block("expected", expected)
            show_block("got", got)
            if err.strip():
                show_block("stderr (dbg)", err)

    total = len(inputs)
    color = GREEN if passed == total else RED
    print(f"\n{color}{passed}/{total} passed{RESET}")
    return 0 if passed == total else 1


def cmd_run(args) -> int:
    src = Path(args.file)
    exe = compile_src(src, args.fast)
    if exe is None:
        return 1
    print(f"{CYAN}running {src.name} - type input, then Ctrl+Z and Enter to send EOF{RESET}")
    return subprocess.run([str(exe)]).returncode


def create_problem(rel: str, tests: list[tuple[str, str]] | None = None) -> Path:
    src = (ROOT / rel).with_suffix(".cpp")
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        shutil.copy(TEMPLATE, src)
    tdir = tests_dir(src)
    tdir.mkdir(parents=True, exist_ok=True)
    if tests:
        for i, (inp, out) in enumerate(tests, 1):
            (tdir / f"{i}.in").write_text(inp)
            (tdir / f"{i}.out").write_text(out)
    elif not any(tdir.iterdir()):
        (tdir / "1.in").touch()
        (tdir / "1.out").touch()
    return src


def cmd_new(args) -> int:
    rel = args.path.removesuffix(".cpp").replace("\\", "/")
    src = create_problem(rel)
    print(f"created {src.relative_to(ROOT)}  +  {tests_dir(src).relative_to(ROOT)}/")
    return 0


def path_from_url(url: str, name: str) -> str:
    """Map a problem URL to a workspace path."""
    parts = [p for p in url.split("?")[0].split("/") if p]
    try:
        if "atcoder.jp" in url:          # .../contests/abc420/tasks/abc420_c
            contest, task = parts[parts.index("contests") + 1], parts[parts.index("tasks") + 1]
            return f"atcoder/{contest}/{task.split('_')[-1]}"
        if "codeforces.com" in url:      # .../contest/2050/problem/C  or  /problemset/problem/2050/C
            if "contest" in parts or "gym" in parts:
                key = "contest" if "contest" in parts else "gym"
                return f"codeforces/{parts[parts.index(key) + 1]}/{parts[-1].lower()}"
            return f"codeforces/{parts[-2]}/{parts[-1].lower()}"
        if "cses.fi" in url:             # .../problemset/task/1068
            slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
            return f"cses/{parts[-1]}_{slug}"
    except (ValueError, IndexError):
        pass
    slug = "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")
    return f"misc/{slug}"


def cmd_listen(args) -> int:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            rel = path_from_url(data.get("url", ""), data.get("name", "problem"))
            tests = [(t["input"], t["output"]) for t in data.get("tests", [])]
            src = create_problem(rel, tests)
            print(f"{GREEN}+{RESET} {data.get('name')}  ->  {src.relative_to(ROOT)}  ({len(tests)} samples)", flush=True)
            if shutil.which("code"):
                subprocess.run(["code", "-r", str(src)], shell=True)

        def log_message(self, *a):
            pass

    print(f"listening for Competitive Companion on port {args.port} (Ctrl+C to stop)")
    try:
        HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_stats(args) -> int:
    if not LOG.exists():
        print("no log yet")
        return 0
    rows = list(csv.DictReader(LOG.open(encoding="utf-8")))
    if not rows:
        print("log is empty")
        return 0
    by_result = Counter(r["result"] for r in rows)
    by_platform = Counter(r["platform"] for r in rows)
    print(f"problems logged: {len(rows)}")
    print("by result:   " + ", ".join(f"{k} {v}" for k, v in by_result.most_common()))
    print("by platform: " + ", ".join(f"{k} {v}" for k, v in by_platform.most_common()))
    alone = [int(r["rating"]) for r in rows if r["result"] == "alone" and r["rating"].isdigit()]
    if alone:
        alone.sort()
        print(f"solved alone: median rating {alone[len(alone) // 2]}, max {alone[-1]}")
    recent = rows[-20:]
    solo_rate = sum(r["result"] == "alone" for r in recent) / len(recent)
    print(f"last {len(recent)}: {solo_rate:.0%} solved alone  "
          f"{DIM}(40-80% = right difficulty; lower = too hard, higher = too easy){RESET}")
    patterns = Counter(p.strip() for r in rows for p in r["pattern"].split(";") if p.strip())
    if patterns:
        print("top patterns: " + ", ".join(f"{k} ({v})" for k, v in patterns.most_common(8)))
    return 0


def main() -> int:
    if sys.platform == "win32":
        import os
        os.system("")  # enables ANSI colors in the Windows console
    p = argparse.ArgumentParser(description="CP helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("test", help="compile + run all sample tests")
    t.add_argument("file")
    t.add_argument("--fast", action="store_true", help="-O2 build, no STL debug checks")
    t.add_argument("--eps", type=float, default=None, help="float tolerance, e.g. 1e-6")
    t.add_argument("--timeout", type=float, default=5.0)
    t.add_argument("-v", "--verbose", action="store_true", help="show dbg() output on passing tests")
    t.set_defaults(func=cmd_test)

    r = sub.add_parser("run", help="compile + run interactively")
    r.add_argument("file")
    r.add_argument("--fast", action="store_true")
    r.set_defaults(func=cmd_run)

    n = sub.add_parser("new", help="create problem from template")
    n.add_argument("path")
    n.set_defaults(func=cmd_new)

    l = sub.add_parser("listen", help="receive problems from Competitive Companion")
    l.add_argument("--port", type=int, default=10043)
    l.set_defaults(func=cmd_listen)

    s = sub.add_parser("stats", help="summarize notes/log.csv")
    s.set_defaults(func=cmd_stats)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
