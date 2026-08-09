from pathlib import Path
import sys


root = Path(sys.argv[1])

for name in ("netcat.c", "socks.c"):
    path = root / name
    content = path.read_text()
    marker = "#include <unistd.h>"
    include = '#include "netcat_compat.h"'
    if include not in content:
        if marker not in content:
            raise RuntimeError(f"unistd include was not found in {name}")
        content = content.replace(marker, f"{marker}\n{include}", 1)
    content = content.replace("#include <resolv.h>\n", "")
    content = content.replace("#include <bsd/readpassphrase.h>\n", "")
    path.write_text(content)

netcat = root / "netcat.c"
content = netcat.read_text()
start = """void
fdpass(int nfd)
{"""
replacement = """void
fdpass(int nfd)
{
#if defined(__wasi__)
	(void)nfd;
	errx(1, "file descriptor passing is unavailable");
#else"""
if replacement not in content:
    if start not in content:
        raise RuntimeError("fdpass function was not found")
    content = content.replace(start, replacement, 1)
    end = """	exit(0);
}

/* Deal with RFC 854"""
    replacement_end = """	exit(0);
#endif
}

/* Deal with RFC 854"""
    if end not in content:
        raise RuntimeError("fdpass function end was not found")
    content = content.replace(end, replacement_end, 1)
netcat.write_text(content)
