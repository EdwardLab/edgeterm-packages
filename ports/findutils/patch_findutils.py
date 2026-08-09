#!/usr/bin/env python3
from pathlib import Path
import sys


source = Path(sys.argv[1])
path = source / "gl/lib/save-cwd.c"
text = path.read_text()

text = text.replace(
    "  cwd->desc = open (\".\", O_SEARCH | O_CLOEXEC);",
    """#if defined __wasi__
  cwd->desc = -1;
  cwd->name = getcwd (NULL, 0);
  return cwd->name ? 0 : -1;
#else
  cwd->desc = open (\".\", O_SEARCH | O_CLOEXEC);""",
)
text = text.replace(
    "\n  return 0;\n}\n\n/* Change to recorded location, CWD, in directory hierarchy.",
    "\n  return 0;\n#endif\n}\n\n/* Change to recorded location, CWD, in directory hierarchy.",
    1,
)
path.write_text(text)
