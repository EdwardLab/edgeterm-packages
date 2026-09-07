#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(EDGETERM_POSIX_THREADS)
#include <pthread.h>
#endif

#if defined(__wasi__)
#include <wasi/libc.h>
#include <wasi/libc-nocwd.h>
#undef chdir
#undef close
#undef dup
#undef dup2
#undef fchdir
#undef getcwd
#undef open
#undef openat

#define EDGETERM_DESCRIPTOR_LIMIT 4096

extern int __real_open(const char *path, int flags, ...);
extern int __real_openat(int directory, const char *path, int flags, ...);

static char *directory_paths[EDGETERM_DESCRIPTOR_LIMIT];
static char *active_directory_path;

static char *normalize_absolute_path(const char *path);

#if defined(EDGETERM_POSIX_THREADS)
static pthread_mutex_t directory_paths_lock = PTHREAD_MUTEX_INITIALIZER;

static void lock_directory_paths(void) {
    pthread_mutex_lock(&directory_paths_lock);
}

static void unlock_directory_paths(void) {
    pthread_mutex_unlock(&directory_paths_lock);
}
#else
static void lock_directory_paths(void) {
}

static void unlock_directory_paths(void) {
}
#endif

static void replace_directory_path(int descriptor, char *path) {
    if (descriptor < 0 || descriptor >= EDGETERM_DESCRIPTOR_LIMIT) {
        free(path);
        return;
    }
    lock_directory_paths();
    free(directory_paths[descriptor]);
    directory_paths[descriptor] = path;
    unlock_directory_paths();
}

static char *copy_directory_path(int descriptor) {
    char *path = NULL;

    if (descriptor < 0 || descriptor >= EDGETERM_DESCRIPTOR_LIMIT) {
        return NULL;
    }
    lock_directory_paths();
    if (directory_paths[descriptor] != NULL) {
        path = strdup(directory_paths[descriptor]);
    }
    unlock_directory_paths();
    return path;
}

static char *copy_active_directory_path(void) {
    char *path = NULL;

    lock_directory_paths();
    if (active_directory_path != NULL) {
        path = strdup(active_directory_path);
    }
    unlock_directory_paths();
    if (path == NULL) {
        const char *environment_path = getenv("PWD");

        /*
         * Some WASIX hosts return a damaged string from getcwd() when the
         * inherited directory is backed by a mounted host filesystem.  The
         * process environment is the authoritative initial directory in that
         * case.  Once chdir() is called, active_directory_path takes over.
         */
        if (environment_path != NULL && environment_path[0] == '/') {
            path = normalize_absolute_path(environment_path);
        }
        if (path == NULL) {
            path = getcwd(NULL, 0);
        }
    }
    return path;
}

static char *normalize_absolute_path(const char *path) {
    char *working;
    char *normalized;
    char *component;
    char *state = NULL;
    size_t length;

    if (path == NULL || path[0] != '/') {
        errno = EINVAL;
        return NULL;
    }
    working = strdup(path);
    normalized = malloc(strlen(path) + 2);
    if (working == NULL || normalized == NULL) {
        free(working);
        free(normalized);
        return NULL;
    }
    normalized[0] = '/';
    normalized[1] = '\0';
    length = 1;
    component = strtok_r(working, "/", &state);
    while (component != NULL) {
        if (strcmp(component, ".") == 0 || component[0] == '\0') {
            component = strtok_r(NULL, "/", &state);
            continue;
        }
        if (strcmp(component, "..") == 0) {
            if (length > 1) {
                if (normalized[length - 1] == '/') {
                    --length;
                }
                while (length > 1 && normalized[length - 1] != '/') {
                    --length;
                }
                normalized[length] = '\0';
            }
            component = strtok_r(NULL, "/", &state);
            continue;
        }
        if (length > 1 && normalized[length - 1] != '/') {
            normalized[length++] = '/';
        }
        memcpy(normalized + length, component, strlen(component));
        length += strlen(component);
        normalized[length] = '\0';
        component = strtok_r(NULL, "/", &state);
    }
    if (length > 1 && normalized[length - 1] == '/') {
        normalized[--length] = '\0';
    }
    free(working);
    return normalized;
}

static char *join_path(const char *base, const char *path) {
    size_t base_length;
    size_t path_length;
    int separator;
    char *joined;

    if (path[0] == '/') {
        return strdup(path);
    }
    base_length = strlen(base);
    path_length = strlen(path);
    separator = base_length > 0 && base[base_length - 1] != '/';
    if (base_length > SIZE_MAX - path_length - (size_t)separator - 1) {
        errno = ENAMETOOLONG;
        return NULL;
    }
    joined = malloc(base_length + path_length + (size_t)separator + 1);
    if (joined == NULL) {
        return NULL;
    }
    memcpy(joined, base, base_length);
    if (separator) {
        joined[base_length++] = '/';
    }
    memcpy(joined + base_length, path, path_length + 1);
    {
        char *normalized = normalize_absolute_path(joined);

        free(joined);
        return normalized;
    }
}

static void remember_directory(int descriptor, int directory, const char *path) {
    char *base = NULL;
    char *candidate;

    if (descriptor < 0) {
        return;
    }
    if (path[0] == '/') {
        candidate = strdup(path);
    } else {
        if (directory == AT_FDCWD) {
            base = copy_active_directory_path();
        } else {
            base = copy_directory_path(directory);
        }
        if (base == NULL) {
            return;
        }
        candidate = join_path(base, path);
    }
    free(base);
    if (candidate == NULL) {
        return;
    }
    replace_directory_path(descriptor, candidate);
}

static int normalize_failed_open_errno(
    int descriptor,
    int directory,
    const char *path,
    int flags
) {
    int original_errno;
    struct stat information;

    if (descriptor >= 0) {
        return descriptor;
    }
    original_errno = errno;
    if ((flags & O_CREAT) != 0 && original_errno == EINVAL) {
        char *parent = strdup(path);
        char *separator;
        int status;

        if (parent == NULL) {
            return descriptor;
        }
        separator = strrchr(parent, '/');
        if (separator == NULL) {
            strcpy(parent, ".");
        } else if (separator == parent) {
            parent[1] = '\0';
        } else {
            *separator = '\0';
        }
        errno = 0;
        if (directory == AT_FDCWD || parent[0] == '/') {
            status = __wasilibc_stat(parent, &information, 0);
        } else {
            status = __wasilibc_nocwd_fstatat(directory, parent, &information, 0);
        }
        free(parent);
        if (status != 0) {
            errno = ENOENT;
            return descriptor;
        }
    }
    if ((flags & O_CREAT) == 0) {
        errno = 0;
        int status;

        if (directory == AT_FDCWD || path[0] == '/') {
            status = __wasilibc_stat(path, &information, 0);
        } else {
            status = __wasilibc_nocwd_fstatat(directory, path, &information, 0);
        }
        if (status != 0 &&
            (errno == ENOENT || errno == EINVAL || original_errno == EINVAL)) {
            errno = ENOENT;
            return descriptor;
        }
    }
    errno = original_errno == 0 ? ENOENT : original_errno;
    return descriptor;
}

static int open_with_mode(const char *path, int flags, mode_t mode) {
    int descriptor;
    int original_errno;

    if ((flags & O_CREAT) != 0) {
        descriptor = __real_open(path, flags, mode);
    } else {
        descriptor = __real_open(path, flags);
    }
    original_errno = errno;
    descriptor = normalize_failed_open_errno(descriptor, AT_FDCWD, path, flags);
    if (descriptor < 0 && getenv("EDGETERM_POSIX_TRACE_OPEN") != NULL) {
        fprintf(
            stderr,
            "open path=%s flags=%d mode=%o original_errno=%d errno=%d\n",
            path,
            flags,
            (unsigned int)mode,
            original_errno,
            errno
        );
    }
    remember_directory(descriptor, AT_FDCWD, path);
    return descriptor;
}

static int openat_with_mode(
    int directory,
    const char *path,
    int flags,
    mode_t mode
) {
    int descriptor;
    int original_errno;

    if ((flags & O_CREAT) != 0) {
        descriptor = __real_openat(directory, path, flags, mode);
    } else {
        descriptor = __real_openat(directory, path, flags);
    }
    original_errno = errno;
    descriptor = normalize_failed_open_errno(descriptor, directory, path, flags);
    if (descriptor < 0 && getenv("EDGETERM_POSIX_TRACE_OPEN") != NULL) {
        fprintf(
            stderr,
            "openat directory=%d path=%s flags=%d mode=%o original_errno=%d errno=%d\n",
            directory,
            path,
            flags,
            (unsigned int)mode,
            original_errno,
            errno
        );
    }
    remember_directory(descriptor, directory, path);
    return descriptor;
}

static mode_t open_mode_argument(int flags, va_list arguments) {
    if ((flags & O_CREAT) == 0) {
        return 0;
    }
    return (mode_t)va_arg(arguments, int);
}

__attribute__((weak)) int edgeterm_posix_open(const char *path, int flags, ...) {
    va_list arguments;
    mode_t mode;

    va_start(arguments, flags);
    mode = open_mode_argument(flags, arguments);
    va_end(arguments);
    return open_with_mode(path, flags, mode);
}

__attribute__((weak)) int __wrap_open(const char *path, int flags, ...) {
    va_list arguments;
    mode_t mode;

    va_start(arguments, flags);
    mode = open_mode_argument(flags, arguments);
    va_end(arguments);
    return open_with_mode(path, flags, mode);
}

__attribute__((weak)) int edgeterm_posix_openat(
    int directory,
    const char *path,
    int flags,
    ...
) {
    va_list arguments;
    mode_t mode;

    va_start(arguments, flags);
    mode = open_mode_argument(flags, arguments);
    va_end(arguments);
    return openat_with_mode(directory, path, flags, mode);
}

__attribute__((weak)) int __wrap_openat(int directory, const char *path, int flags, ...) {
    va_list arguments;
    mode_t mode;

    va_start(arguments, flags);
    mode = open_mode_argument(flags, arguments);
    va_end(arguments);
    return openat_with_mode(directory, path, flags, mode);
}

__attribute__((weak)) int edgeterm_posix_close(int descriptor) {
    int result = close(descriptor);

    if (result == 0) {
        replace_directory_path(descriptor, NULL);
    }
    return result;
}

__attribute__((weak)) int edgeterm_posix_chdir(const char *path) {
    char *resolved_path;
    char *previous_path;

    if (path == NULL) {
        errno = EFAULT;
        return -1;
    }
    if (path[0] == '/') {
        resolved_path = normalize_absolute_path(path);
    } else {
        char *base = copy_active_directory_path();

        if (base == NULL) {
            return -1;
        }
        resolved_path = join_path(base, path);
        free(base);
    }
    if (resolved_path == NULL) {
        return -1;
    }
    lock_directory_paths();
    if (chdir(resolved_path) != 0) {
        int saved_errno = errno;

        unlock_directory_paths();
        free(resolved_path);
        errno = saved_errno;
        return -1;
    }
    previous_path = active_directory_path;
    active_directory_path = resolved_path;
    unlock_directory_paths();
    free(previous_path);
    return 0;
}

__attribute__((weak)) char *edgeterm_posix_getcwd(char *buffer, size_t size) {
    char *path = copy_active_directory_path();
    size_t required;

    if (path == NULL) {
        return NULL;
    }
    required = strlen(path) + 1;
    if (buffer == NULL) {
        size_t allocation_size = size == 0 ? required : size;

        if (allocation_size < required) {
            free(path);
            errno = ERANGE;
            return NULL;
        }
        buffer = malloc(allocation_size);
        if (buffer == NULL) {
            free(path);
            return NULL;
        }
    } else if (size == 0 || size < required) {
        free(path);
        errno = ERANGE;
        return NULL;
    }
    memcpy(buffer, path, required);
    free(path);
    return buffer;
}

__attribute__((weak)) int edgeterm_posix_dup(int descriptor) {
    int duplicate = dup(descriptor);

    if (duplicate >= 0) {
        replace_directory_path(duplicate, copy_directory_path(descriptor));
    }
    return duplicate;
}

__attribute__((weak)) int edgeterm_posix_dup2(int descriptor, int duplicate) {
    int result = dup2(descriptor, duplicate);

    if (result >= 0) {
        replace_directory_path(result, copy_directory_path(descriptor));
    }
    return result;
}

__attribute__((weak)) int edgeterm_posix_fchdir(int descriptor) {
    struct stat information;
    char *path;
    int result;
    int saved_errno;

    path = copy_directory_path(descriptor);
    if (path == NULL) {
        errno = ENOTSUP;
        return -1;
    }
    if (stat(path, &information) != 0) {
        saved_errno = errno;
        free(path);
        errno = saved_errno;
        return -1;
    }
    if (!S_ISDIR(information.st_mode)) {
        free(path);
        errno = ENOTDIR;
        return -1;
    }
    result = edgeterm_posix_chdir(path);
    saved_errno = errno;
    free(path);
    errno = saved_errno;
    return result;
}
#endif
