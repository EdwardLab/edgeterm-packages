#ifndef EDGETERM_POSIX_MNTENT_H
#define EDGETERM_POSIX_MNTENT_H

#include_next <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef _PATH_MOUNTED
#define _PATH_MOUNTED "/etc/mtab"
#endif

#ifndef MNTTAB
#define MNTTAB _PATH_MOUNTED
#endif

#ifndef MNTTYPE_IGNORE
#define MNTTYPE_IGNORE "ignore"
#endif

struct mntent {
    char *mnt_fsname;
    char *mnt_dir;
    char *mnt_type;
    char *mnt_opts;
    int mnt_freq;
    int mnt_passno;
};

FILE *setmntent(const char *filename, const char *type);
struct mntent *getmntent(FILE *stream);
struct mntent *getmntent_r(
    FILE *stream,
    struct mntent *result,
    char *buffer,
    int buffer_size
);
int addmntent(FILE *stream, const struct mntent *entry);
int endmntent(FILE *stream);
char *hasmntopt(const struct mntent *entry, const char *option);

#ifdef __cplusplus
}
#endif

#endif
