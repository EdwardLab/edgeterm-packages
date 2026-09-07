#ifndef EDGETERM_POSIX_SYS_STATVFS_H
#define EDGETERM_POSIX_SYS_STATVFS_H

#if !defined(__wasi__)

#include_next <sys/statvfs.h>

#else

#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

struct statvfs {
    unsigned long f_bsize;
    unsigned long f_frsize;
    fsblkcnt_t f_blocks;
    fsblkcnt_t f_bfree;
    fsblkcnt_t f_bavail;
    fsfilcnt_t f_files;
    fsfilcnt_t f_ffree;
    fsfilcnt_t f_favail;
    unsigned long f_fsid;
    unsigned long f_flag;
    unsigned long f_namemax;
    char f_fstypename[16];
};

#ifndef ST_RDONLY
#define ST_RDONLY 1
#endif

#ifndef ST_NOSUID
#define ST_NOSUID 2
#endif

int statvfs(const char *path, struct statvfs *information);
int fstatvfs(int file_descriptor, struct statvfs *information);

#ifdef __cplusplus
}
#endif

#endif

#endif
