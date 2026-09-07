#ifndef EDGETERM_POSIX_OVERLAY_WCHAR_H
#define EDGETERM_POSIX_OVERLAY_WCHAR_H

#include_next <wchar.h>

#ifdef __cplusplus
extern "C" {
#endif

wchar_t *wmempcpy(wchar_t *destination, const wchar_t *source, size_t count);

#ifdef __cplusplus
}
#endif

#endif
