#ifndef EDGETERM_POSIX_OVERLAY_POLL_H
#define EDGETERM_POSIX_OVERLAY_POLL_H

#include_next <poll.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__wasi__)
int edgeterm_posix_poll(struct pollfd *descriptors, nfds_t count, int timeout);
#if !defined(EDGETERM_POSIX_INTERNAL)
int poll(struct pollfd *descriptors, nfds_t count, int timeout) __asm__("edgeterm_posix_poll");
#endif
#endif

#ifdef __cplusplus
}
#endif

#endif
