from pathlib import Path
import sys


root = Path(sys.argv[1])
changes = {
    "lib/sh/getenv.c": (
        "#if defined (CAN_REDEFINE_GETENV)",
        "#if defined (CAN_REDEFINE_GETENV) && !defined (__wasi__)",
    ),
    "lib/sh/getcwd.c": (
        "#if !defined (HAVE_GETCWD)",
        "#if !defined (HAVE_GETCWD) && !defined (__wasi__)",
    ),
    "shell.c": (
        "#if defined (__OPENNT) || defined (__MVS__)\n  char **env;\n\n  env = environ;\n#endif /* __OPENNT || __MVS__ */",
        "#if defined (__OPENNT) || defined (__MVS__) || defined (NO_MAIN_ENV_ARG)\n  char **env;\n\n  env = environ;\n#endif /* __OPENNT || __MVS__ || NO_MAIN_ENV_ARG */",
    ),
    "lib/termcap/termcap.c": (
        "__private_extern__ char PC = '\\0';",
        "extern char PC;",
    ),
    "lib/termcap/tparam.c": (
        "__private_extern__ char *BC;\n__private_extern__ char *UP;",
        "extern char *BC;\nextern char *UP;",
    ),
}
for relative_path, (old, new) in changes.items():
    path = root / relative_path
    content = path.read_text()
    if old not in content:
        raise RuntimeError(f"Expected source fragment not found in {relative_path}")
    path.write_text(content.replace(old, new, 1))

common = root / "builtins/common.c"
content = common.read_text()
old = """      if (the_current_working_directory == 0)
\t{
\t  fprintf (stderr, \"%s: %s: %s: %s\\n\",
"""
new = """#if defined (__wasi__)
      if (the_current_working_directory == 0)
        {
          const char *environment_pwd = getenv (\"PWD\");
          if (environment_pwd && environment_pwd[0] == '/')
            the_current_working_directory = savestring (environment_pwd);
        }
#endif
      if (the_current_working_directory == 0)
\t{
\t  fprintf (stderr, \"%s: %s: %s: %s\\n\",
"""
if old not in content:
    raise RuntimeError("Expected getcwd error path not found in builtins/common.c")
common.write_text(content.replace(old, new, 1))
