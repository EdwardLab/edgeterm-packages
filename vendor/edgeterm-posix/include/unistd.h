#ifndef EDGETERM_POSIX_OVERLAY_UNISTD_H
#define EDGETERM_POSIX_OVERLAY_UNISTD_H

#include_next <unistd.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

char *getlogin(void);
int getgroups(int size, gid_t list[]);
#if defined(__wasi__)
int setgroups(size_t size, const gid_t list[]);
#endif
int fchdir(int file_descriptor);
int chroot(const char *path);
int sync_file_range(int file_descriptor, off_t offset, off_t byte_count, unsigned int flags);

#ifndef SYNC_FILE_RANGE_WAIT_BEFORE
#define SYNC_FILE_RANGE_WAIT_BEFORE 1
#endif
#ifndef SYNC_FILE_RANGE_WRITE
#define SYNC_FILE_RANGE_WRITE 2
#endif
#ifndef SYNC_FILE_RANGE_WAIT_AFTER
#define SYNC_FILE_RANGE_WAIT_AFTER 4
#endif
int edgeterm_posix_isatty(int file_descriptor);

#if defined(__wasi__)
ssize_t edgeterm_posix_read(int file_descriptor, void *buffer, size_t size);
ssize_t edgeterm_posix_readlink(const char *path, char *buffer, size_t size);
int edgeterm_posix_rmdir(const char *path);
int edgeterm_posix_close(int file_descriptor);
int edgeterm_posix_chdir(const char *path);
int edgeterm_posix_dup(int file_descriptor);
int edgeterm_posix_dup2(int file_descriptor, int duplicate);
int edgeterm_posix_fchdir(int file_descriptor);
char *edgeterm_posix_getcwd(char *buffer, size_t size);
#if !defined(EDGETERM_POSIX_INTERNAL)
int close(int file_descriptor) __asm__("edgeterm_posix_close");
int chdir(const char *path) __asm__("edgeterm_posix_chdir");
int dup(int file_descriptor) __asm__("edgeterm_posix_dup");
int dup2(int file_descriptor, int duplicate) __asm__("edgeterm_posix_dup2");
int fchdir(int file_descriptor) __asm__("edgeterm_posix_fchdir");
char *getcwd(char *buffer, size_t size) __asm__("edgeterm_posix_getcwd");
ssize_t read(int file_descriptor, void *buffer, size_t size) __asm__("edgeterm_posix_read");
ssize_t readlink(const char *path, char *buffer, size_t size) __asm__("edgeterm_posix_readlink");
int rmdir(const char *path) __asm__("edgeterm_posix_rmdir");
int isatty(int file_descriptor) __asm__("edgeterm_posix_isatty");
#endif
#endif

#ifdef __cplusplus
}
#endif

#endif
