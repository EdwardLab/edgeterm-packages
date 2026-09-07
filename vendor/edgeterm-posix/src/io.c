#define _POSIX_C_SOURCE 200809L
#define EDGETERM_POSIX_INTERNAL 1

#include <errno.h>
#include <poll.h>
#include <time.h>

#if defined(__wasi__)
extern int __real_poll(struct pollfd *descriptors, nfds_t count, int timeout);
#endif

static int poll_compat(
    struct pollfd *descriptors,
    nfds_t count,
    int timeout
) {
    nfds_t index;
    struct timespec delay;

    for (index = 0; index < count; index += 1) {
        if (descriptors[index].fd >= 0) {
#if defined(__wasi__)
            return __real_poll(descriptors, count, timeout);
#else
            return poll(descriptors, count, timeout);
#endif
        }
    }
    if (timeout <= 0) {
        return 0;
    }
    delay.tv_sec = timeout / 1000;
    delay.tv_nsec = (long)(timeout % 1000) * 1000000L;
    while (nanosleep(&delay, &delay) != 0) {
        if (errno != EINTR) return -1;
    }
    return 0;
}

__attribute__((weak)) int edgeterm_posix_poll(
    struct pollfd *descriptors,
    nfds_t count,
    int timeout
) {
    return poll_compat(descriptors, count, timeout);
}

__attribute__((weak)) int __wrap_poll(
    struct pollfd *descriptors,
    nfds_t count,
    int timeout
) {
    return poll_compat(descriptors, count, timeout);
}
