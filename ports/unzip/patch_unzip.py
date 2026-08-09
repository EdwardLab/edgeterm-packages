from pathlib import Path
import sys


path = Path(sys.argv[1]) / "unix" / "unix.c"
content = path.read_text()
replacements = {
    "utime(G.filename, &(zt.t2))": "utime(G.filename, (const struct utimbuf *) &(zt.t2))",
    "utime(d->fn, &UxAtt(d)->u.t2)": "utime(d->fn, (const struct utimbuf *) &UxAtt(d)->u.t2)",
    "utime(fname, &tp)": "utime(fname, (const struct utimbuf *) &tp)",
}
for old, new in replacements.items():
    if old not in content:
        raise RuntimeError(f"Expected source fragment not found: {old}")
    content = content.replace(old, new)
path.write_text(content)
