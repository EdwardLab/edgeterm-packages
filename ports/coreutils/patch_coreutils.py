from pathlib import Path
import sys


path = Path(sys.argv[1]) / "src" / "stat.c"
content = path.read_text()
marker = "# define USE_STATVFS 0\n#endif\n"
replacement = "# define USE_STATVFS 0\n#endif\n\n#ifdef __wasi__\n# undef USE_STATVFS\n# define USE_STATVFS 1\n#endif\n"
if marker not in content:
    raise RuntimeError("Expected statvfs selection block was not found")
content = content.replace(marker, replacement, 1)
type_marker = "#ifdef STATXFS_FILE_SYSTEM_TYPE_MEMBER_NAME\n"
type_replacement = (
    "#ifdef __wasi__\n"
    "  return \"unknown\";\n"
    "#elif defined STATXFS_FILE_SYSTEM_TYPE_MEMBER_NAME\n"
)
if type_marker not in content:
    raise RuntimeError("Expected filesystem type branch was not found")
path.write_text(content.replace(type_marker, type_replacement, 1))

chroot_path = Path(sys.argv[1]) / "src" / "chroot.c"
chroot_content = chroot_path.read_text()
chroot_marker = "#include <grp.h>\n"
chroot_replacement = (
    "#include <grp.h>\n\n"
    "#ifdef __wasi__\n"
    "# undef GETGROUPS_T\n"
    "# define GETGROUPS_T gid_t\n"
    "#endif\n"
)
if chroot_marker not in chroot_content:
    raise RuntimeError("Expected group header was not found")
chroot_path.write_text(chroot_content.replace(chroot_marker, chroot_replacement, 1))

getgroups_path = Path(sys.argv[1]) / "lib" / "getgroups.c"
getgroups_content = getgroups_path.read_text()
getgroups_marker = "# undef getgroups\n"
getgroups_replacement = "# undef getgroups\nint getgroups (int, GETGROUPS_T *);\n"
if getgroups_marker not in getgroups_content:
    raise RuntimeError("Expected getgroups declaration anchor was not found")
getgroups_path.write_text(getgroups_content.replace(getgroups_marker, getgroups_replacement, 1))
