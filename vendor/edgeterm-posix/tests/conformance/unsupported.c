#include <edgeterm/posix/compat.h>

#include <assert.h>
#include <errno.h>

int main(void) {
#if defined(__wasi__)
    errno = 0;
    assert(memfd_create("test", 0) == -1);
    assert(errno == ENOSYS);

    errno = 0;
    assert(chroot("/") == -1);
    assert(errno == ENOSYS);
#else
    assert(edgeterm_posix_capability("virtual_root") == EDGETERM_POSIX_UNSUPPORTED);
    assert(edgeterm_posix_capability("file_locking") == EDGETERM_POSIX_UNSUPPORTED);
#endif
    return 0;
}
