#!/usr/bin/env python3
from pathlib import Path


source = Path("/build/source-root/file-5.48/src/apprentice.c")
text = source.read_text()
old = """\tif (read(fd, map->p, map->len) != (ssize_t)map->len) {
\t\tfile_badread(ms);
\t\tgoto error;
\t}
"""
new = """\t{
\t\tsize_t offset = 0;
\t\twhile (offset < map->len) {
\t\t\tssize_t count = read(fd, (char *)map->p + offset, map->len - offset);
\t\t\tif (count > 0) {
\t\t\t\toffset += (size_t)count;
\t\t\t\tcontinue;
\t\t\t}
\t\t\tif (count < 0 && errno == EINTR)
\t\t\t\tcontinue;
\t\t\tfile_badread(ms);
\t\t\tgoto error;
\t\t}
\t}
"""
if old not in text:
    raise SystemExit("libmagic read anchor was not found")
source.write_text(text.replace(old, new, 1))
