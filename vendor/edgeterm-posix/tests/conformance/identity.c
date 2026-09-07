#include <edgeterm/posix/compat.h>

#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(void) {
    gid_t groups[1];

#if defined(__wasi__)
    assert(setenv("LOGNAME", "edgeterm-test", 1) == 0);
    assert(strcmp(getlogin(), "edgeterm-test") == 0);
    assert(getgroups(0, NULL) == 1);
    assert(getgroups(1, groups) == 1);
    assert(setgroups(0, NULL) == 0);
#else
    (void)groups;
    assert(edgeterm_posix_capability("identity") == EDGETERM_POSIX_COMPAT);
#endif
    return 0;
}
