#ifndef EDGETERM_POSIX_OVERLAY_GRP_H
#define EDGETERM_POSIX_OVERLAY_GRP_H

#include_next <grp.h>
#include <stddef.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__wasi__)
int setgroups(size_t size, const gid_t *list);
#endif

#ifdef __cplusplus
}
#endif

#endif
