#ifndef EDGETERM_POSIX_OVERLAY_STDLIB_H
#define EDGETERM_POSIX_OVERLAY_STDLIB_H

#include_next <stdlib.h>

#ifdef __cplusplus
extern "C" {
#endif

int getloadavg(double load_average[], int element_count);
#if defined(__wasi__)
unsigned int arc4random(void);
int getentropy(void *buffer, size_t length);
size_t malloc_usable_size(void *pointer);
#endif

#ifdef __cplusplus
}
#endif

#endif
