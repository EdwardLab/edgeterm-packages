#ifndef EDGETERM_POSIX_OVERLAY_SYS_TYPES_H
#define EDGETERM_POSIX_OVERLAY_SYS_TYPES_H

#include_next <sys/types.h>
#include <stdint.h>

#ifndef major
#define major(device) \
    ((unsigned int)(((uint64_t)(device) >> 32) & UINT32_MAX))
#endif
#ifndef minor
#define minor(device) \
    ((unsigned int)((uint64_t)(device) & UINT32_MAX))
#endif
#ifndef makedev
#define makedev(major_value, minor_value) \
    ((dev_t)((((uint64_t)(major_value)) << 32) | (uint32_t)(minor_value)))
#endif

#endif
