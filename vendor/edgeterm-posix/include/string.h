#ifndef EDGETERM_POSIX_OVERLAY_STRING_H
#define EDGETERM_POSIX_OVERLAY_STRING_H

#include_next <string.h>

#ifdef __cplusplus
extern "C" {
#endif

int strerror_r(int error_number, char *buffer, size_t buffer_size);

#ifdef __cplusplus
}
#endif

#endif
