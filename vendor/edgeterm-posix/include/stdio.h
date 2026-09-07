#ifndef EDGETERM_POSIX_OVERLAY_STDIO_H
#define EDGETERM_POSIX_OVERLAY_STDIO_H

#include_next <stdio.h>

#ifndef L_tmpnam
#define L_tmpnam 64
#endif

#ifndef P_tmpdir
#define P_tmpdir "/tmp"
#endif

#ifdef __cplusplus
extern "C" {
#endif

#ifndef flockfile
void flockfile(FILE *stream);
#endif
#ifndef funlockfile
void funlockfile(FILE *stream);
#endif
#ifndef ftrylockfile
int ftrylockfile(FILE *stream);
#endif
int fileno(FILE *stream);
char *edgeterm_posix_tmpnam(char *buffer);

#if defined(__wasi__)
FILE *edgeterm_posix_fdopen(int file_descriptor, const char *mode);
FILE *edgeterm_posix_fopen(const char *path, const char *mode);
#if !defined(EDGETERM_POSIX_INTERNAL)
char *tmpnam(char *buffer) __asm__("edgeterm_posix_tmpnam");
FILE *fdopen(int file_descriptor, const char *mode) __asm__("edgeterm_posix_fdopen");
FILE *fopen(const char *path, const char *mode) __asm__("edgeterm_posix_fopen");
#endif
#endif

#ifdef __cplusplus
}
#endif

#endif
