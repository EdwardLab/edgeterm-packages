#ifndef EDGETERM_POSIX_OVERLAY_FCNTL_H
#define EDGETERM_POSIX_OVERLAY_FCNTL_H

#include_next <fcntl.h>
#include <sys/types.h>

#ifndef F_RDLCK
#define F_RDLCK 0
#endif
#ifndef F_WRLCK
#define F_WRLCK 1
#endif
#ifndef F_UNLCK
#define F_UNLCK 2
#endif
#ifndef F_GETLK
#define F_GETLK 5
#endif
#ifndef F_SETLK
#define F_SETLK 6
#endif
#ifndef F_SETLKW
#define F_SETLKW 7
#endif

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__wasi__)
int edgeterm_posix_open(const char *path, int flags, ...);
int edgeterm_posix_openat(int directory, const char *path, int flags, ...);
#if !defined(EDGETERM_POSIX_INTERNAL)
int open(const char *path, int flags, ...) __asm__("edgeterm_posix_open");
int openat(int directory, const char *path, int flags, ...) __asm__("edgeterm_posix_openat");
#endif
#endif

#ifdef __cplusplus
}
#endif

#endif
