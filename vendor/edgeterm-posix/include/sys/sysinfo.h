#ifndef EDGETERM_POSIX_SYSINFO_H
#define EDGETERM_POSIX_SYSINFO_H

#if defined(__has_include_next)
#if __has_include_next(<sys/sysinfo.h>)
#include_next <sys/sysinfo.h>
#define EDGETERM_POSIX_HAS_NATIVE_SYSINFO 1
#endif
#endif

#ifndef EDGETERM_POSIX_HAS_NATIVE_SYSINFO
struct sysinfo {
    long uptime;
    unsigned long loads[3];
    unsigned long totalram;
    unsigned long freeram;
    unsigned long sharedram;
    unsigned long bufferram;
    unsigned long totalswap;
    unsigned long freeswap;
    unsigned short procs;
    unsigned long totalhigh;
    unsigned long freehigh;
    unsigned int mem_unit;
};

int sysinfo(struct sysinfo *information);
#endif

#endif
