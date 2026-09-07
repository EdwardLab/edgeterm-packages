#ifndef EDGETERM_POSIX_DIRENT_H
#define EDGETERM_POSIX_DIRENT_H

/*
 * Keep the target ABI field order while exposing a bounded d_name array.
 * Many portable programs use sizeof(d_name) when allocating synthetic
 * directory entries, and POSIX limits a single component to NAME_MAX bytes.
 */
#if defined(__wasi__) && !defined(__wasilibc___struct_dirent_h)
#define __wasilibc___struct_dirent_h
#include <__typedef_ino_t.h>
#define _DIRENT_HAVE_D_TYPE
struct dirent {
    ino_t d_ino;
    unsigned char d_type;
    char d_name[256];
};
#endif

#include_next <dirent.h>

#endif
