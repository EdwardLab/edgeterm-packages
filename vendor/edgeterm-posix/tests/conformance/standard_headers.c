#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <edgeterm/posix/profile.h>

#include <assert.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sched.h>
#include <sys/types.h>
#include <unistd.h>

int main(void) {
#if defined(__wasi__)
    if (strcmp(P_tmpdir, "/tmp") != 0) {
        return 1;
    }
    char first_temporary_name[L_tmpnam];
    char second_temporary_name[L_tmpnam];

    assert(tmpnam(first_temporary_name) != NULL);
    assert(tmpnam(second_temporary_name) != NULL);
    assert(strcmp(first_temporary_name, second_temporary_name) != 0);
#endif
    dev_t device = makedev(12, 34);
    double load_average[3];
#if defined(__wasi__)
    cpu_set_t processor_set;
#endif

    flockfile(stdout);
    funlockfile(stdout);
    if (major(device) != 12 || minor(device) != 34) {
        return 1;
    }
    if (getloadavg(load_average, 3) < 0) {
        return 1;
    }
    if (setlocale(LC_ALL, NULL) == NULL) {
        return 1;
    }
    if (edgeterm_posix_capability("locale_name") != EDGETERM_POSIX_COMPAT) {
        return 1;
    }
    if (edgeterm_posix_capability("processor_topology") != EDGETERM_POSIX_ADVISORY) {
        return 1;
    }
    if (edgeterm_posix_capability("system_load") != EDGETERM_POSIX_ADVISORY) {
        return 1;
    }
    if (edgeterm_posix_capability("thread_local_storage") != EDGETERM_POSIX_COMPAT) {
        return 1;
    }
#if defined(__wasi__)
    CPU_ZERO(&processor_set);
    if (sched_getaffinity(0, sizeof(processor_set), &processor_set) != 0) {
        return 1;
    }
    if (CPU_COUNT(&processor_set) < 1) {
        return 1;
    }
#endif
    return sysconf(_SC_NPROCESSORS_ONLN) > 0 ? 0 : 1;
}
