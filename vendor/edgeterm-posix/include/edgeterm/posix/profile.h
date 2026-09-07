#ifndef EDGETERM_POSIX_PROFILE_H
#define EDGETERM_POSIX_PROFILE_H

#define EDGETERM_POSIX_PROFILE_VERSION 1
#define EDGETERM_POSIX_ABI_VERSION 1
#define EDGETERM_POSIX_VERSION_STRING "0.1.0"

#ifdef __cplusplus
extern "C" {
#endif

enum edgeterm_posix_capability_status {
    EDGETERM_POSIX_UNSUPPORTED = 0,
    EDGETERM_POSIX_NATIVE = 1,
    EDGETERM_POSIX_COMPAT = 2,
    EDGETERM_POSIX_ADVISORY = 3
};

int edgeterm_posix_capability(const char *name);
const char *edgeterm_posix_status_name(int status);
const char *edgeterm_posix_profile_version(void);

#ifdef __cplusplus
}
#endif

#endif
