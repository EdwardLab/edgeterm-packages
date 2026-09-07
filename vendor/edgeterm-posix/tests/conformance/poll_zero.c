#include <assert.h>
#include <poll.h>
#include <stddef.h>

int main(void) {
    struct pollfd ignored = { .fd = -1, .events = POLLIN, .revents = 0 };

    assert(poll(NULL, 0, 0) == 0);
    assert(poll(&ignored, 1, 0) == 0);
    return 0;
}
