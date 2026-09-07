#include <fcntl.h>

int main(void) {
    struct flock lock = {0};
    lock.l_type = F_WRLCK;
    lock.l_whence = SEEK_SET;
    lock.l_start = 0;
    lock.l_len = 0;
    return F_GETLK == F_SETLK || F_SETLK == F_SETLKW;
}
