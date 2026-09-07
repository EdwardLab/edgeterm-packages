#ifndef EDGETERM_POSIX_IFADDRS_H
#define EDGETERM_POSIX_IFADDRS_H

#if defined(__has_include_next)
#if __has_include_next(<ifaddrs.h>)
#include_next <ifaddrs.h>
#define EDGETERM_POSIX_HAS_NATIVE_IFADDRS 1
#endif
#endif

#ifndef EDGETERM_POSIX_HAS_NATIVE_IFADDRS
#include <sys/socket.h>

struct ifaddrs {
    struct ifaddrs *ifa_next;
    char *ifa_name;
    unsigned int ifa_flags;
    struct sockaddr *ifa_addr;
    struct sockaddr *ifa_netmask;
    struct sockaddr *ifa_dstaddr;
    void *ifa_data;
};

int getifaddrs(struct ifaddrs **addresses);
void freeifaddrs(struct ifaddrs *addresses);
#endif

#endif
