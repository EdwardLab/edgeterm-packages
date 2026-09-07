#ifndef EDGETERM_POSIX_OVERLAY_SYS_STAT_H
#define EDGETERM_POSIX_OVERLAY_SYS_STAT_H

#include_next <sys/stat.h>

#ifdef __cplusplus
extern "C" {
#endif

int mknod(const char *path, mode_t mode, dev_t device);
int mkfifo(const char *path, mode_t mode);
int mkfifoat(int directory, const char *path, mode_t mode);

#if defined(__wasi__)
int edgeterm_posix_stat(const char *path, struct stat *information);
int edgeterm_posix_lstat(const char *path, struct stat *information);
#if !defined(EDGETERM_POSIX_INTERNAL)
int stat(const char *path, struct stat *information) __asm__("edgeterm_posix_stat");
int lstat(const char *path, struct stat *information) __asm__("edgeterm_posix_lstat");
#endif
#endif

#ifdef __cplusplus
}
#endif

#endif
