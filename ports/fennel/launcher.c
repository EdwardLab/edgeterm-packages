#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char **child_argv = calloc((size_t)argc + 2, sizeof(char *));
    int index;
    if (child_argv == NULL) {
        fputs("fennel: unable to allocate argument list\n", stderr);
        return 1;
    }
    child_argv[0] = "/usr/local/bin/lua";
    child_argv[1] = "/usr/local/share/fennel/fennel.lua";
    for (index = 1; index < argc; index++) {
        child_argv[index + 1] = argv[index];
    }
    child_argv[argc + 1] = NULL;
    execv(child_argv[0], child_argv);
    int error_number = errno;
    perror("fennel");
    free(child_argv);
    return error_number == 0 ? 1 : error_number;
}
