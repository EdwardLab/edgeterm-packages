from pathlib import Path
import sys


root = Path(sys.argv[1])
for relative_path in ("src/core/utils/term.rs", "src/core/init.rs", "src/state.rs"):
    path = root / relative_path
    content = path.read_text()
    content = content.replace(".is_tty()", ".is_terminal()")
    content = content.replace("use std::io::IsTerminal;\n", "")
    first_use = content.find("use ")
    if first_use < 0:
        raise RuntimeError(f"No import anchor found in {relative_path}")
    content = content[:first_use] + "use std::io::IsTerminal;\n" + content[first_use:]
    path.write_text(content)
