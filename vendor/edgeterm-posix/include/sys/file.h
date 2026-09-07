#ifndef EDGETERM_POSIX_OVERLAY_SYS_FILE_H
#define EDGETERM_POSIX_OVERLAY_SYS_FILE_H

#if defined(__has_include_next)
#if __has_include_next(<sys/file.h>)
#include_next <sys/file.h>
#endif
#endif

#ifdef __cplusplus
extern "C" {
#endif

int flock(int file_descriptor, int operation);

#ifdef __cplusplus
}
#endif

#endif
