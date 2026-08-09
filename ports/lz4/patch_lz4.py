#!/usr/bin/env python3
from pathlib import Path
import sys


path = Path(sys.argv[1]) / "programs/lz4io.c"
text = path.read_text()
old = '''    if (UTIL_isDirectory(srcFileName)) {
        DISPLAYLEVEL(1, "lz4: %s is a directory -- ignored \\n", srcFileName);
        return NULL;
    }
'''
new = '''#if !defined(__wasi__)
    if (UTIL_isDirectory(srcFileName)) {
        DISPLAYLEVEL(1, "lz4: %s is a directory -- ignored \\n", srcFileName);
        return NULL;
    }
#endif
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("LZ4 source-file directory check was not found")
path.write_text(text.replace(old, new, 1))
