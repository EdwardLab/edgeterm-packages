from pathlib import Path
import sys


path = Path(sys.argv[1]) / "include/urcu/arch.h"
content = path.read_text()
old = """#elif defined(__loongarch__)

#define URCU_ARCH_LOONGARCH 1
#include <urcu/arch/loongarch.h>

#else"""
new = """#elif defined(__loongarch__)

#define URCU_ARCH_LOONGARCH 1
#include <urcu/arch/loongarch.h>

#elif defined(__wasm32__)

#define URCU_ARCH_WASM32 1
#include <urcu/arch/gcc.h>

#else"""
if old not in content:
    raise RuntimeError("liburcu architecture selection block was not found")
path.write_text(content.replace(old, new, 1))

syscall_path = Path(sys.argv[1]) / "include/urcu/syscall-compat.h"
content = syscall_path.read_text()
old = "defined(__OpenBSD__)"
new = "defined(__OpenBSD__) || defined(__wasi__)"
if old not in content:
    raise RuntimeError("liburcu syscall platform selection block was not found")
syscall_path.write_text(content.replace(old, new, 1))
