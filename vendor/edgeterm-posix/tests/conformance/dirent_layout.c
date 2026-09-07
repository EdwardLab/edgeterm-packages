#include <dirent.h>
#include <stddef.h>

_Static_assert(offsetof(struct dirent, d_ino) == 0, "d_ino must remain first");
#if defined(__wasi__)
_Static_assert(sizeof(((struct dirent *)0)->d_name) == 256,
               "d_name must expose the portable component limit");
#endif

int main(void) {
    struct dirent entry = {0};
    entry.d_type = DT_REG;
    entry.d_name[0] = 'x';
    return entry.d_name[0] == 'x' ? 0 : 1;
}
