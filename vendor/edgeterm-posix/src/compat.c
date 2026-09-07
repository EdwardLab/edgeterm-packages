#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <edgeterm/posix/compat.h>

#include <errno.h>
#include <limits.h>
#include <sched.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysinfo.h>
#include <unistd.h>

#if defined(__wasi__)
#include <wasi/api.h>
#include <wasi/libc-nocwd.h>
#endif

#if defined(__wasi__)
#undef chdir
#undef close
#undef dup
#undef dup2
#undef fdopen
#undef fopen
#undef fchdir
#undef isatty
#undef lstat
#undef open
#undef openat
#undef read
#undef readlink
#undef rmdir
#undef stat
#undef tmpnam
#endif

#if defined(__wasi__)
__attribute__((weak)) ssize_t edgeterm_posix_read(
    int file_descriptor,
    void *buffer,
    size_t size
) {
    struct stat information;
    size_t offset = 0;

    if (fstat(file_descriptor, &information) != 0 || !S_ISREG(information.st_mode)) {
        return read(file_descriptor, buffer, size);
    }
    while (offset < size) {
        ssize_t count = read(
            file_descriptor,
            (unsigned char *)buffer + offset,
            size - offset
        );

        if (count > 0) {
            offset += (size_t)count;
            continue;
        }
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0 && offset == 0) {
            return -1;
        }
        break;
    }
    return (ssize_t)offset;
}

__attribute__((weak)) int edgeterm_posix_stat(
    const char *path,
    struct stat *information
) {
    int result;

    errno = 0;
    result = stat(path, information);
    if (result < 0 && errno == 0) {
        errno = ENOENT;
    }
    return result;
}

__attribute__((weak)) int edgeterm_posix_lstat(
    const char *path,
    struct stat *information
) {
    int result;

    errno = 0;
    result = lstat(path, information);
    if (result < 0 && errno == 0) {
        errno = ENOENT;
    }
    return result;
}

__attribute__((weak)) ssize_t edgeterm_posix_readlink(
    const char *path,
    char *buffer,
    size_t size
) {
    ssize_t result;

    errno = 0;
    result = readlink(path, buffer, size);
    if (result < 0 && errno == 0) {
        errno = EINVAL;
    }
    return result;
}

static int remove_directory_beneath(int base_descriptor, const char *path) {
    const int directory_flags = O_SEARCH | O_CLOEXEC | O_DIRECTORY |
        O_NOCTTY | O_NONBLOCK | O_NOFOLLOW;
    char *copy;
    char *cursor;
    char *separator;
    int current_descriptor = base_descriptor;
    int next_descriptor;
    int owns_descriptor = 0;
    int result;
    int saved_errno;

    copy = strdup(path);
    if (copy == NULL) {
        return -1;
    }
    cursor = copy;
    while ((separator = strchr(cursor, '/')) != NULL) {
        *separator = '\0';
        if (cursor[0] != '\0') {
            next_descriptor = openat(
                current_descriptor,
                cursor,
                directory_flags
            );
            if (next_descriptor < 0) {
                saved_errno = errno;
                if (owns_descriptor) {
                    close(current_descriptor);
                }
                free(copy);
                errno = saved_errno;
                return -1;
            }
            if (owns_descriptor) {
                close(current_descriptor);
            }
            current_descriptor = next_descriptor;
            owns_descriptor = 1;
        }
        cursor = separator + 1;
        while (cursor[0] == '/') {
            cursor++;
        }
    }
    if (cursor[0] == '\0') {
        if (owns_descriptor) {
            close(current_descriptor);
        }
        free(copy);
        errno = ENOENT;
        return -1;
    }
    result = __wasilibc_nocwd___wasilibc_rmdirat(
        current_descriptor,
        cursor
    );
    saved_errno = errno;
    if (owns_descriptor) {
        close(current_descriptor);
    }
    free(copy);
    errno = saved_errno;
    return result;
}

static int remove_absolute_preopened_directory(const char *path) {
    char preopen_name[PATH_MAX];
    const char *candidate;
    const char *relative_path;
    int descriptor;
    int first_error = 0;

    for (descriptor = 3; descriptor < 256; descriptor++) {
        __wasi_prestat_t status;
        size_t name_length;
        size_t path_offset;
        int root_preopen;
        int result;

        if (__wasi_fd_prestat_get((__wasi_fd_t)descriptor, &status) != 0 ||
            status.tag != __WASI_PREOPENTYPE_DIR) {
            continue;
        }
        name_length = status.u.dir.pr_name_len;
        if (name_length == 0 || name_length >= sizeof(preopen_name)) {
            continue;
        }
        if (__wasi_fd_prestat_dir_name(
            (__wasi_fd_t)descriptor,
            (uint8_t *)preopen_name,
            (__wasi_size_t)name_length
        ) != 0) {
            continue;
        }
        preopen_name[name_length] = '\0';
        root_preopen = (name_length == 1 && preopen_name[0] == '/') ||
            (name_length == 1 && preopen_name[0] == '.');
        if (root_preopen) {
            relative_path = path;
        } else {
            path_offset = preopen_name[0] == '/' ? 0 : 1;
            candidate = path + path_offset;
            if (strncmp(candidate, preopen_name, name_length) != 0 ||
                (candidate[name_length] != '\0' && candidate[name_length] != '/')) {
                continue;
            }
            relative_path = candidate + name_length;
            while (relative_path[0] == '/') {
                relative_path++;
            }
        }
        if (relative_path[0] == '\0') {
            continue;
        }
        result = root_preopen
            ? __wasilibc_nocwd___wasilibc_rmdirat(descriptor, relative_path)
            : remove_directory_beneath(descriptor, relative_path);
        if (result == 0) {
            return 0;
        }
        if (errno != ENOENT && first_error == 0) {
            first_error = errno;
        }
    }
    errno = first_error == 0 ? ENOENT : first_error;
    return -1;
}

__attribute__((weak)) int edgeterm_posix_rmdir(const char *path) {
    const int directory_flags = O_SEARCH | O_CLOEXEC | O_DIRECTORY |
        O_NOCTTY | O_NONBLOCK | O_NOFOLLOW;
    char *copy;
    char *cursor;
    char *separator;
    int directory;
    int next_directory;
    int result;
    int saved_errno;
    size_t length;
    struct stat information;

    if (path == NULL) {
        errno = EFAULT;
        return -1;
    }
    if (path[0] == '\0') {
        errno = ENOENT;
        return -1;
    }
    if (stat(path, &information) != 0) {
        return -1;
    }
    if (!S_ISDIR(information.st_mode)) {
        errno = ENOTDIR;
        return -1;
    }
    if (path[0] == '/') {
        result = remove_absolute_preopened_directory(path);
        if (result == 0 || errno != ENOENT) {
            return result;
        }
    }
    copy = strdup(path);
    if (copy == NULL) {
        return -1;
    }
    length = strlen(copy);
    while (length > 1 && copy[length - 1] == '/') {
        copy[--length] = '\0';
    }
    cursor = copy;
    if (cursor[0] == '/') {
        while (cursor[0] == '/') {
            cursor++;
        }
        directory = open("/", directory_flags);
    } else {
        directory = open(".", directory_flags);
    }
    if (directory < 0) {
        free(copy);
        return -1;
    }
    while ((separator = strchr(cursor, '/')) != NULL) {
        *separator = '\0';
        if (cursor[0] != '\0') {
            next_directory = openat(directory, cursor, directory_flags);
            if (next_directory < 0) {
                saved_errno = errno;
                close(directory);
                free(copy);
                errno = saved_errno;
                return -1;
            }
            close(directory);
            directory = next_directory;
        }
        cursor = separator + 1;
        while (cursor[0] == '/') {
            cursor++;
        }
    }
    if (cursor[0] == '\0') {
        close(directory);
        free(copy);
        errno = EBUSY;
        return -1;
    }
    result = __wasilibc_nocwd___wasilibc_rmdirat(directory, cursor);
    saved_errno = errno;
    close(directory);
    free(copy);
    errno = saved_errno;
    return result;
}

__attribute__((weak)) int __sched_cpucount(size_t set_size, const cpu_set_t *set) {
    const unsigned char *bytes = (const unsigned char *)set;
    size_t index;
    int count = 0;

    if (set == NULL) {
        errno = EFAULT;
        return -1;
    }
    for (index = 0; index < set_size; index++) {
        unsigned char value = bytes[index];

        while (value != 0) {
            count += value & 1U;
            value >>= 1;
        }
    }
    return count;
}

__attribute__((weak)) int sched_getaffinity(
    pid_t process_id,
    size_t set_size,
    cpu_set_t *set
) {
    (void)process_id;
    if (set == NULL) {
        errno = EFAULT;
        return -1;
    }
    if (set_size < sizeof(*set)) {
        errno = EINVAL;
        return -1;
    }
    memset(set, 0, set_size);
    CPU_SET(0, set);
    return 0;
}

__attribute__((weak)) int sched_getcpu(void) {
    return 0;
}

__attribute__((weak)) int getloadavg(double load_average[], int element_count) {
    int index;

    if (load_average == NULL || element_count < 0) {
        errno = EINVAL;
        return -1;
    }
    if (element_count > 3) {
        element_count = 3;
    }
    for (index = 0; index < element_count; index++) {
        load_average[index] = 0.0;
    }
    return element_count;
}

__attribute__((weak)) size_t malloc_usable_size(void *pointer) {
    (void)pointer;
    return 0;
}

__attribute__((weak)) void *__cxa_allocate_exception(size_t size) {
    return malloc(size);
}

__attribute__((weak)) void __cxa_free_exception(void *exception) {
    free(exception);
}

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
#endif

#if defined(__wasi__)
static int fopen_flags(const char *mode) {
    int flags;

    if (mode == NULL || mode[0] == '\0') {
        errno = EINVAL;
        return -1;
    }
    switch (mode[0]) {
        case 'r': flags = O_RDONLY; break;
        case 'w': flags = O_WRONLY | O_CREAT | O_TRUNC; break;
        case 'a': flags = O_WRONLY | O_CREAT | O_APPEND; break;
        default:
            errno = EINVAL;
            return -1;
    }
    if (strchr(mode, '+') != NULL) {
        flags &= ~(O_RDONLY | O_WRONLY);
        flags |= O_RDWR;
    }
    if (strchr(mode, 'x') != NULL) flags |= O_EXCL;
    if (strchr(mode, 'e') != NULL) flags |= O_CLOEXEC;
    return flags;
}

__attribute__((weak)) FILE *edgeterm_posix_fopen(
    const char *path,
    const char *mode
) {
    int descriptor;
    int flags = fopen_flags(mode);

    if (flags < 0) return NULL;
    descriptor = (flags & O_CREAT) != 0
        ? open(path, flags, 0666)
        : open(path, flags);
    if (descriptor < 0) return NULL;
    FILE *stream = fdopen(descriptor, mode);
    if (stream == NULL) {
        int saved_errno = errno;
        close(descriptor);
        errno = saved_errno == 0 ? EINVAL : saved_errno;
    }
    return stream;
}

__attribute__((weak)) FILE *edgeterm_posix_fdopen(
    int file_descriptor,
    const char *mode
) {
    if (mode == NULL) {
        errno = EINVAL;
        return NULL;
    }
    if (file_descriptor == STDIN_FILENO) {
        return stdin;
    }
    if (file_descriptor == STDOUT_FILENO) {
        return stdout;
    }
    if (file_descriptor == STDERR_FILENO) {
        return stderr;
    }
    return fdopen(file_descriptor, mode);
}
#endif

static gid_t configured_group_id(void) {
    const char *value = getenv("EDGETERM_GID");
    char *end = NULL;
    unsigned long parsed;

    if (value == NULL || value[0] == '\0') {
        return getgid();
    }
    errno = 0;
    parsed = strtoul(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0') {
        return getgid();
    }
    return (gid_t)parsed;
}

__attribute__((weak)) int edgeterm_posix_isatty(int file_descriptor) {
    const char *mode = NULL;

    if (file_descriptor == STDIN_FILENO) {
        mode = getenv("EDGETERM_STDIN_MODE");
    } else if (file_descriptor == STDOUT_FILENO) {
        mode = getenv("EDGETERM_STDOUT_MODE");
    } else if (file_descriptor == STDERR_FILENO) {
        mode = getenv("EDGETERM_STDERR_MODE");
    }
    if (mode != NULL && (strcmp(mode, "pipe") == 0 || strcmp(mode, "file") == 0)) {
        errno = ENOTTY;
        return 0;
    }
    return isatty(file_descriptor);
}

__attribute__((weak)) wchar_t *wmempcpy(
    wchar_t *destination,
    const wchar_t *source,
    size_t count
) {
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

__attribute__((weak)) char *edgeterm_posix_tmpnam(char *buffer) {
    static char internal_buffer[L_tmpnam];
    static unsigned long sequence;
    char *target = buffer == NULL ? internal_buffer : buffer;
    unsigned long attempt;

    for (attempt = 0; attempt < 1024; ++attempt) {
        unsigned long value = ++sequence;
        struct stat information;
        int length = snprintf(
            target,
            L_tmpnam,
            "/tmp/edgeterm-%lu-%lu.tmp",
            (unsigned long)getpid(),
            value
        );

        if (length < 0 || length >= L_tmpnam) {
            errno = ENAMETOOLONG;
            return NULL;
        }
        if (stat(target, &information) != 0) {
            return target;
        }
    }
    errno = EEXIST;
    return NULL;
}

__attribute__((weak)) int strerror_r(int error_number, char *buffer, size_t buffer_size) {
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
    static char fallback[] = "user";
    char *value = getenv("LOGNAME");

    if (value == NULL || value[0] == '\0') {
        value = getenv("USER");
    }
    return value != NULL && value[0] != '\0' ? value : fallback;
}

__attribute__((weak)) int getgroups(int size, gid_t list[]) {
    if (size < 0) {
        errno = EINVAL;
        return -1;
    }
    if (size == 0) {
        return 1;
    }
    if (list == NULL) {
        errno = EFAULT;
        return -1;
    }
    list[0] = configured_group_id();
    return 1;
}

__attribute__((weak)) int setgroups(
#if defined(__wasi__)
    size_t size,
#else
    int size,
#endif
    const gid_t list[]
) {
    if (size == 0) {
        return 0;
    }
    if (size == 1 && list != NULL && list[0] == getgid()) {
        return 0;
    }
    errno = EPERM;
    return -1;
}

__attribute__((weak)) int chroot(const char *path) {
    (void)path;
    errno = ENOSYS;
    return -1;
}

#if defined(__wasi__)
__attribute__((weak)) int fchdir(int file_descriptor) {
    (void)file_descriptor;
    errno = ENOSYS;
    return -1;
}
#endif

__attribute__((weak)) int mknod(const char *path, mode_t mode, dev_t device) {
    (void)path;
    (void)mode;
    (void)device;
    errno = ENOSYS;
    return -1;
}

__attribute__((weak)) int mkfifo(const char *path, mode_t mode) {
    return mknod(path, mode | S_IFIFO, 0);
}

__attribute__((weak)) int mkfifoat(
    int directory,
    const char *path,
    mode_t mode
) {
    (void)directory;
    (void)path;
    (void)mode;
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

#if !defined(EDGETERM_POSIX_THREADS)
__attribute__((weak)) void __wasm_init_tls(void *tls_base) {
    (void)tls_base;
}
#endif
