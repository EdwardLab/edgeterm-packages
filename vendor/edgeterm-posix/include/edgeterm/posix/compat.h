#ifndef EDGETERM_POSIX_COMPAT_H
#define EDGETERM_POSIX_COMPAT_H

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#include <sys/stat.h>
#include <wchar.h>

#include <edgeterm/posix/profile.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef F_RDLCK
#define F_RDLCK 0
#endif
#ifndef F_WRLCK
#define F_WRLCK 1
#endif
#ifndef F_UNLCK
#define F_UNLCK 2
#endif
#ifndef F_SETLK
#define F_SETLK 6
#endif
#ifndef F_SETLKW
#define F_SETLKW 7
#endif

#ifndef SYNC_FILE_RANGE_WAIT_BEFORE
#define SYNC_FILE_RANGE_WAIT_BEFORE 1
#endif
#ifndef SYNC_FILE_RANGE_WRITE
#define SYNC_FILE_RANGE_WRITE 2
#endif
#ifndef SYNC_FILE_RANGE_WAIT_AFTER
#define SYNC_FILE_RANGE_WAIT_AFTER 4
#endif

#ifndef major
#define major(device) ((unsigned int)(((uint64_t)(device) >> 32) & UINT32_MAX))
#endif
#ifndef minor
#define minor(device) ((unsigned int)((uint64_t)(device) & UINT32_MAX))
#endif
#ifndef makedev
#define makedev(major_value, minor_value) \
    ((dev_t)((((uint64_t)(major_value)) << 32) | (uint32_t)(minor_value)))
#endif

#ifndef CMSG_FIRSTHDR
struct cmsghdr {
    size_t cmsg_len;
    int cmsg_level;
    int cmsg_type;
};
#define EDGETERM_CMSG_ALIGN(length) \
    (((length) + sizeof(size_t) - 1) & ~(sizeof(size_t) - 1))
#define CMSG_DATA(header) \
    ((unsigned char *)(header) + EDGETERM_CMSG_ALIGN(sizeof(struct cmsghdr)))
#define CMSG_LEN(length) \
    (EDGETERM_CMSG_ALIGN(sizeof(struct cmsghdr)) + (length))
#define CMSG_SPACE(length) \
    (EDGETERM_CMSG_ALIGN(sizeof(struct cmsghdr)) + EDGETERM_CMSG_ALIGN(length))
#define CMSG_FIRSTHDR(message) \
    ((message)->msg_controllen >= sizeof(struct cmsghdr) \
        ? (struct cmsghdr *)(message)->msg_control : NULL)
#define CMSG_NXTHDR(message, header) \
    (((unsigned char *)(header) + EDGETERM_CMSG_ALIGN((header)->cmsg_len) + \
        sizeof(struct cmsghdr) <= \
        (unsigned char *)(message)->msg_control + (message)->msg_controllen) \
        ? (struct cmsghdr *)((unsigned char *)(header) + \
            EDGETERM_CMSG_ALIGN((header)->cmsg_len)) : NULL)
#endif

#ifndef SCM_RIGHTS
#define SCM_RIGHTS 1
#endif

void flockfile(FILE *stream);
void funlockfile(FILE *stream);
int ftrylockfile(FILE *stream);
int fileno(FILE *stream);
#if defined(__wasi__)
FILE *edgeterm_posix_fdopen(int file_descriptor, const char *mode);
#endif
int strerror_r(int error_number, char *buffer, size_t buffer_size);
wchar_t *wmempcpy(wchar_t *destination, const wchar_t *source, size_t count);
char *getlogin(void);
int getgroups(int size, gid_t list[]);
#if defined(__wasi__)
int setgroups(size_t size, const gid_t *list);
#else
int setgroups(int size, const gid_t *list);
#endif
int fchdir(int file_descriptor);
int chroot(const char *path);
int memfd_create(const char *name, unsigned int flags);
int madvise(void *address, size_t length, int advice);
struct ifaddrs;
int getifaddrs(struct ifaddrs **addresses);
void freeifaddrs(struct ifaddrs *addresses);
unsigned int if_nametoindex(const char *interface_name);
int mknod(const char *path, mode_t mode, dev_t device);
int flock(int file_descriptor, int operation);
int sync_file_range(int file_descriptor, off_t offset, off_t byte_count, unsigned int flags);
uint32_t arc4random(void);
int getentropy(void *buffer, size_t length);

#ifdef __cplusplus
}
#endif

#endif
