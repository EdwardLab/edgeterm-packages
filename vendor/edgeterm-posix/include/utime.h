#ifndef EDGETERM_POSIX_UTIME_H
#define EDGETERM_POSIX_UTIME_H

#include_next <utime.h>

#ifdef __cplusplus
extern "C" {
#endif

int edgeterm_posix_utime(const char *path, const struct utimbuf *times);

#ifdef __cplusplus
}
#endif

#if defined(__wasi__) && !defined(EDGETERM_POSIX_INTERNAL)
int utime(const char *path, const struct utimbuf *times) __asm__("edgeterm_posix_utime");
#endif

#endif
