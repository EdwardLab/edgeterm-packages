#define EDGETERM_POSIX_INTERNAL 1

#include <sys/types.h>
#include <utime.h>

__attribute__((weak)) time_t timezone = 0;

__attribute__((weak)) int edgeterm_posix_utime(
    const char *path,
    const struct utimbuf *times
) {
    return utime(path, times);
}
