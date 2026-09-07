#ifndef EDGETERM_POSIX_OVERLAY_SYS_SOCKET_H
#define EDGETERM_POSIX_OVERLAY_SYS_SOCKET_H

#include_next <sys/socket.h>

#if defined(__wasi__) && !defined(CMSG_SPACE)
struct cmsghdr {
    socklen_t cmsg_len;
    int cmsg_level;
    int cmsg_type;
};

#define SCM_RIGHTS 0x01
#define CMSG_ALIGN(length) (((length) + sizeof(size_t) - 1) & ~(sizeof(size_t) - 1))
#define CMSG_DATA(header) ((unsigned char *)(header) + CMSG_ALIGN(sizeof(struct cmsghdr)))
#define CMSG_SPACE(length) (CMSG_ALIGN(sizeof(struct cmsghdr)) + CMSG_ALIGN(length))
#define CMSG_LEN(length) (CMSG_ALIGN(sizeof(struct cmsghdr)) + (length))
#define CMSG_FIRSTHDR(message) \
    ((message)->msg_controllen >= sizeof(struct cmsghdr) \
         ? (struct cmsghdr *)(message)->msg_control \
         : (struct cmsghdr *)0)
#define CMSG_NXTHDR(message, header) edgeterm_posix_cmsg_nxthdr((message), (header))

static inline struct cmsghdr *edgeterm_posix_cmsg_nxthdr(
    const struct msghdr *message,
    const struct cmsghdr *header
) {
    const unsigned char *next = (const unsigned char *)header + CMSG_ALIGN(header->cmsg_len);
    const unsigned char *end = (const unsigned char *)message->msg_control + message->msg_controllen;
    if (header->cmsg_len < sizeof(struct cmsghdr) || next + sizeof(struct cmsghdr) > end) {
        return (struct cmsghdr *)0;
    }
    return (struct cmsghdr *)(void *)next;
}
#endif

#endif
