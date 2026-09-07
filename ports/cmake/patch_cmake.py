from pathlib import Path
import sys


path = Path(sys.argv[1]) / "Utilities/cmlibuv/src/unix/core.c"
content = path.read_text()

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

content = content.replace("#if defined(__QNX__)\n  /* QNX priority is not process-based */", "#if defined(__QNX__) || defined(__wasi__)\n  /* Process priority is not available. */", 2)

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
#endif"""
    replacement = """  *priority = param.sched_priority;
  return 0;
#endif
}
#endif"""
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

path.write_text(content)

path = Path(sys.argv[1]) / "Source/cmSystemTools.cxx"
content = path.read_text()
old = """#else
  std::string exe = cmsys::SystemTools::FindProgram(argv0);
#endif"""
new = """#elif defined(__wasi__)
  char const* executable_path = std::getenv("EDGETERM_EXECUTABLE_PATH");
  std::string exe = executable_path != nullptr ? executable_path : argv0;
#else
  std::string exe = cmsys::SystemTools::FindProgram(argv0);
#endif"""
if new not in content:
    if old not in content:
        raise RuntimeError("CMake executable discovery was not found")
    content = content.replace(old, new, 1)
path.write_text(content)

path = Path(sys.argv[1]) / "Utilities/cmlibuv/include/uv/unix.h"
content = path.read_text()
old = """#ifdef CMAKE_BOOTSTRAP
# include "posix.h"
# if defined(__APPLE__)"""
new = """#if defined(__wasi__)
# include "posix.h"
#elif defined(CMAKE_BOOTSTRAP)
# include "posix.h"
# if defined(__APPLE__)"""
if new not in content:
    if old not in content:
        raise RuntimeError("libuv platform header selection was not found")
    content = content.replace(old, new, 1)
path.write_text(content)

path = Path(sys.argv[1]) / "Utilities/cmlibuv/CMakeLists.txt"
content = path.read_text()
marker = """include_directories(
  ${uv_includes}"""
addition = """if(CMAKE_SYSTEM_NAME STREQUAL "WASI")
  list(APPEND uv_sources
    src/unix/posix-hrtime.c
    src/unix/posix-poll.c
    src/unix/no-fsevents.c
    src/unix/no-proctitle.c
    )
endif()

include_directories(
  ${uv_includes}"""
if addition not in content:
    if marker not in content:
        raise RuntimeError("libuv include_directories marker was not found")
    content = content.replace(marker, addition, 1)
path.write_text(content)

path = Path(sys.argv[1]) / "Utilities/cmlibuv/src/unix/thread.c"
content = path.read_text()
content = content.replace(
    "#if defined(_AIX) || defined(__MVS__) || defined(__PASE__) || \\\n",
    "#if defined(__wasi__) || defined(_AIX) || defined(__MVS__) || defined(__PASE__) || \\\n",
    1,
)
content = content.replace(
    "#if (defined(__ANDROID_API__) && __ANDROID_API__ < 26) || \\\n",
    "#if defined(__wasi__) || \\\n    (defined(__ANDROID_API__) && __ANDROID_API__ < 26) || \\\n",
    1,
)
path.write_text(content)

path = Path(sys.argv[1]) / "Utilities/cmlibuv/src/unix/tty.c"
content = path.read_text()
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
path.write_text(content)

path = Path(sys.argv[1]) / "Utilities/cmlibuv/src/unix/fs.c"
content = path.read_text()
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
path.write_text(content)
