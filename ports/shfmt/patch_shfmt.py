#!/usr/bin/env python3
from pathlib import Path
import sys


source = Path(sys.argv[1]) / "cmd/shfmt/main.go"
text = source.read_text()
text = text.replace('version := "(unknown)"', 'version := "v3.13.1"')
old = "\t\t\tversion = mod.Version\n"
new = '''			if mod.Version != "" && mod.Version != "(devel)" {
				version = mod.Version
			}
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("shfmt version assignment was not found")
source.write_text(text)
