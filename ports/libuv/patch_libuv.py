from pathlib import Path
import sys


root = Path(sys.argv[1])

core = root / "src/unix/core.c"
content = core.read_text()
old = """ssize_t uv__recvmsg(int fd, struct msghdr* msg, int flags) {
#if defined(__ANDROID__)"""
new = """ssize_t uv__recvmsg(int fd, struct msghdr* msg, int flags) {
#if defined(__wasi__)
  ssize_t rc;
  rc = recvmsg(fd, msg, flags);
  if (rc == -1)
    return UV__ERR(errno);
  return rc;
#elif defined(__ANDROID__)"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv recvmsg implementation was not found")
    content = content.replace(old, new, 1)

old = """int uv_os_getpriority(uv_pid_t pid, int* priority) {
  int r;"""
new = """int uv_os_getpriority(uv_pid_t pid, int* priority) {
#if defined(__wasi__)
  (void)pid;
  (void)priority;
  return UV_ENOSYS;
#else
  int r;"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv process priority getter was not found")
    content = content.replace(old, new, 1)
    marker = """  *priority = r;
  return 0;
}


int uv_os_setpriority"""
    replacement = """  *priority = r;
  return 0;
#endif
}


int uv_os_setpriority"""
    if marker not in content:
        raise RuntimeError("libuv process priority getter end was not found")
    content = content.replace(marker, replacement, 1)

old = """int uv_os_setpriority(uv_pid_t pid, int priority) {
  if (priority < UV_PRIORITY_HIGHEST"""
new = """int uv_os_setpriority(uv_pid_t pid, int priority) {
#if defined(__wasi__)
  (void)pid;
  (void)priority;
  return UV_ENOSYS;
#else
  if (priority < UV_PRIORITY_HIGHEST"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv process priority setter was not found")
    content = content.replace(old, new, 1)
    marker = """  return 0;
}

/**"""
    replacement = """  return 0;
#endif
}

/**"""
    if marker not in content:
        raise RuntimeError("libuv process priority setter end was not found")
    content = content.replace(marker, replacement, 1)
content = content.replace(
    "#if defined(__QNX__)\n  /* QNX priority is not process-based */",
    "#if defined(__QNX__) || defined(__wasi__)\n  /* Process priority is not available. */",
    2,
)
old = """int uv_thread_getpriority(uv_thread_t tid, int* priority) {
  int r;"""
new = """int uv_thread_getpriority(uv_thread_t tid, int* priority) {
#if defined(__wasi__)
  (void)tid;
  (void)priority;
  return UV_ENOSYS;
#else
  int r;"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv thread priority getter was not found")
    content = content.replace(old, new, 1)
    marker = """  *priority = param.sched_priority;
  return 0;
}

#ifdef __linux__"""
    replacement = """  *priority = param.sched_priority;
  return 0;
#endif
}

#ifdef __linux__"""
    if marker not in content:
        raise RuntimeError("libuv thread priority getter end was not found")
    content = content.replace(marker, replacement, 1)
old = """int uv_thread_setpriority(uv_thread_t tid, int priority) {
#if !defined(__GNU__)"""
new = """int uv_thread_setpriority(uv_thread_t tid, int priority) {
#if defined(__wasi__)
  (void)tid;
  (void)priority;
  return UV_ENOSYS;
#elif !defined(__GNU__)"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv thread priority setter was not found")
    content = content.replace(old, new, 1)
core.write_text(content)

fs = root / "src/unix/fs.c"
content = fs.read_text()
content = content.replace(
    "#elif defined(__sun)      || \\\n",
    "#elif defined(__wasi__)    || \\\n      defined(__sun)      || \\\n",
    1,
)
content = content.replace(
    "#if defined(__sun)      || \\\n",
    "#if defined(__wasi__)    || \\\n    defined(__sun)      || \\\n",
    1,
)
content = content.replace(
    "#if defined(__sun)        || \\\n",
    "#if defined(__wasi__)      || \\\n    defined(__sun)        || \\\n",
    1,
)
fs.write_text(content)

thread = root / "src/unix/thread.c"
content = thread.read_text()
content = content.replace(
    "#if defined(_AIX) || defined(__MVS__) || defined(__PASE__)",
    "#if defined(__wasi__) || defined(_AIX) || defined(__MVS__) || defined(__PASE__)",
    1,
)
content = content.replace(
    "#if (defined(__ANDROID_API__) && __ANDROID_API__ < 26) || \\\n",
    "#if defined(__wasi__) || \\\n    (defined(__ANDROID_API__) && __ANDROID_API__ < 26) || \\\n",
    1,
)
thread.write_text(content)

tty = root / "src/unix/tty.c"
content = tty.read_text()
old = """#else
  /* Fallback to ptsname
   */
  result = ptsname(fd) == NULL;"""
new = """#elif defined(__wasi__)
  result = 0;
#else
  /* Fallback to ptsname
   */
  result = ptsname(fd) == NULL;"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv tty fallback was not found")
    content = content.replace(old, new, 1)
tty.write_text(content)

unix_header = root / "include/uv/unix.h"
content = unix_header.read_text()
if '#if defined(__wasi__)\n# include "uv/posix.h"' not in content:
    old = "#if defined(__linux__)\n# include \"uv/linux.h\""
    new = """#if defined(__wasi__)
# include "uv/posix.h"
#elif defined(__linux__)
# include "uv/linux.h""" 
    if old not in content:
        raise RuntimeError("libuv platform header selection was not found")
    content = content.replace(old, new, 1)
unix_header.write_text(content)

configure = root / "configure.ac"
content = configure.read_text()
marker = "AM_CONDITIONAL([WINNT],"
line = "AM_CONDITIONAL([WASI],     [AS_CASE([$host_os],[wasi*],         [true], [false])])\n"
if line not in content:
    if marker not in content:
        raise RuntimeError("libuv platform condition marker was not found")
    content = content.replace(marker, line + marker, 1)
configure.write_text(content)

makefile = root / "Makefile.am"
content = makefile.read_text()
addition = (
    "\nif WASI\n"
    "libuv_la_SOURCES += src/unix/posix-hrtime.c \\\n"
    "                    src/unix/posix-poll.c \\\n"
    "                    src/unix/no-fsevents.c \\\n"
    "                    src/unix/no-proctitle.c\n"
    "endif\n"
)
marker = "if WINNT\n"
if addition not in content:
    if marker not in content:
        raise RuntimeError("libuv Makefile platform marker was not found")
    content = content.replace(marker, addition + "\n" + marker, 1)
makefile.write_text(content)
