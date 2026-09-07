#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <sys/statvfs.h>

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#if defined(__wasi__)

#define EDGETERM_POSIX_BLOCK_SIZE 4096UL
#define EDGETERM_POSIX_DEFAULT_CAPACITY (1024ULL * 1024ULL * 1024ULL)
#define EDGETERM_POSIX_DEFAULT_FREE (768ULL * 1024ULL * 1024ULL)

static uint64_t configured_bytes(const char *name, uint64_t fallback) {
    const char *value = getenv(name);
    char *end = NULL;
    unsigned long long parsed;

    if (value == NULL || value[0] == '\0') {
        return fallback;
    }
    errno = 0;
    parsed = strtoull(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') {
        return fallback;
    }
    return (uint64_t)parsed;
}

static int fill_statvfs(const struct stat *status, struct statvfs *information) {
    uint64_t capacity;
    uint64_t free_bytes;

    if (status == NULL || information == NULL) {
        errno = EFAULT;
        return -1;
    }
    capacity = configured_bytes(
        "EDGETERM_STORAGE_CAPACITY_BYTES",
        EDGETERM_POSIX_DEFAULT_CAPACITY
    );
    free_bytes = configured_bytes(
        "EDGETERM_STORAGE_FREE_BYTES",
        EDGETERM_POSIX_DEFAULT_FREE
    );
    if (free_bytes > capacity) {
        free_bytes = capacity;
    }

    memset(information, 0, sizeof(*information));
    information->f_bsize = EDGETERM_POSIX_BLOCK_SIZE;
    information->f_frsize = EDGETERM_POSIX_BLOCK_SIZE;
    information->f_blocks = (fsblkcnt_t)(capacity / EDGETERM_POSIX_BLOCK_SIZE);
    information->f_bfree = (fsblkcnt_t)(free_bytes / EDGETERM_POSIX_BLOCK_SIZE);
    information->f_bavail = information->f_bfree;
    information->f_files = (fsfilcnt_t)(capacity / 4096ULL);
    information->f_ffree = (fsfilcnt_t)(free_bytes / 4096ULL);
    information->f_favail = information->f_ffree;
    information->f_fsid = (unsigned long)status->st_dev;
    information->f_namemax = 255;
    memcpy(information->f_fstypename, "posixfs", sizeof("posixfs"));
    return 0;
}

__attribute__((weak)) int statvfs(
    const char *path,
    struct statvfs *information
) {
    struct stat status;

    if (path == NULL || information == NULL) {
        errno = EFAULT;
        return -1;
    }
    if (stat(path, &status) != 0) {
        return -1;
    }
    return fill_statvfs(&status, information);
}

__attribute__((weak)) int fstatvfs(
    int file_descriptor,
    struct statvfs *information
) {
    struct stat status;

    if (information == NULL) {
        errno = EFAULT;
        return -1;
    }
    if (fstat(file_descriptor, &status) != 0) {
        return -1;
    }
    return fill_statvfs(&status, information);
}

#endif
