#include <errno.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysinfo.h>
#include <sys/types.h>
#include <unistd.h>
#include <wchar.h>

/*
 * Some WASIX hosts currently start a spawned module at the virtual root even
 * though the parent exports the correct working directory. Restore the
 * inherited POSIX working directory before program startup so relative paths
 * used by shells, build tools, and their children resolve consistently.
 */
__attribute__((constructor)) static void edgeterm_restore_working_directory(void) {
    const char *pwd = getenv("PWD");
    char current[4096];

    if (pwd == NULL || pwd[0] != '/' || strstr(pwd, "/../") != NULL) {
        return;
    }
    if (getcwd(current, sizeof(current)) != NULL && strcmp(current, pwd) == 0) {
        return;
    }
    (void)chdir(pwd);
}

__attribute__((weak)) wchar_t *wmempcpy(wchar_t *destination, const wchar_t *source, size_t count) {
    return wmemcpy(destination, source, count) + count;
}

__attribute__((weak)) void flockfile(FILE *stream) {
    (void)stream;
}

__attribute__((weak)) void funlockfile(FILE *stream) {
    (void)stream;
}

__attribute__((weak)) int ftrylockfile(FILE *stream) {
    (void)stream;
    return 0;
}

__attribute__((weak)) int strerror_r(
    int error_number,
    char *buffer,
    size_t buffer_size
) {
    const char *message = strerror(error_number);
    size_t length;

    if (buffer == NULL || buffer_size == 0) {
        return EINVAL;
    }
    if (message == NULL) {
        message = "Unknown error";
    }
    length = strlen(message);
    if (length >= buffer_size) {
        memcpy(buffer, message, buffer_size - 1);
        buffer[buffer_size - 1] = '\0';
        return ERANGE;
    }
    memcpy(buffer, message, length + 1);
    return 0;
}

__attribute__((weak)) int memfd_create(const char *name, unsigned int flags) {
    (void)name;
    (void)flags;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int madvise(void *address, size_t length, int advice) {
    (void)address;
    (void)length;
    (void)advice;
    return 0;
}

__attribute__((weak)) int getifaddrs(struct ifaddrs **addresses) {
    if (addresses != NULL) {
        *addresses = NULL;
    }
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) void freeifaddrs(struct ifaddrs *addresses) {
    (void)addresses;
}

__attribute__((weak)) unsigned int if_nametoindex(const char *interface_name) {
    (void)interface_name;
    errno = ENODEV;
    return 0;
}

__attribute__((weak)) char *getlogin(void) {
    return NULL;
}

__attribute__((weak)) int getgroups(int size, gid_t list[]) {
    (void)size;
    (void)list;
    return 0;
}

__attribute__((weak)) int setgroups(size_t size, const gid_t *list) {
    (void)size;
    (void)list;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int chroot(const char *path) {
    (void)path;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int fchdir(int file_descriptor) {
    (void)file_descriptor;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int mknod(const char *path, mode_t mode, dev_t device) {
    (void)path;
    (void)mode;
    (void)device;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int flock(int file_descriptor, int operation) {
    (void)file_descriptor;
    (void)operation;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int sync_file_range(
    int file_descriptor,
    off_t offset,
    off_t byte_count,
    unsigned int flags
) {
    (void)offset;
    (void)byte_count;
    (void)flags;
    return fsync(file_descriptor);
}

__attribute__((weak)) uint32_t arc4random(void) {
    uint32_t value = 0;
    if (getentropy(&value, sizeof(value)) != 0) {
        abort();
    }
    return value;
}

__attribute__((weak)) int sysinfo(struct sysinfo *information) {
    if (information != NULL) {
        memset(information, 0, sizeof(*information));
    }
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) void *__cxa_allocate_exception(size_t size) {
    return malloc(size);
}

__attribute__((weak)) void __cxa_free_exception(void *exception) {
    free(exception);
}

#if !defined(EDGETERM_THREADS)
__attribute__((weak)) void __wasm_init_tls(void *tls_base) {
    (void)tls_base;
}
#endif

__attribute__((weak, noreturn)) void __cxa_throw(
    void *exception,
    void *type_info,
    void (*destructor)(void *)
) {
    (void)type_info;
    if (destructor != NULL) {
        destructor(exception);
    }
    free(exception);
    abort();
}
