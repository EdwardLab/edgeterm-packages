#include <assert.h>
#include <spawn.h>
#include <string.h>
#include <sys/wait.h>

extern char **environ;

int main(int argc, char **argv) {
    pid_t child;
    int status;
    char *child_argv[] = {
        argv[0],
        (char *)"--child",
        NULL,
    };

    if (argc == 2 && strcmp(argv[1], "--child") == 0) {
        return 23;
    }

#if defined(__wasi__)
    assert(posix_spawnp(
        &child,
        "edgeterm-posix-spawn",
#else
    assert(posix_spawn(
        &child,
        argv[0],
#endif
        NULL,
        NULL,
        child_argv,
        environ
    ) == 0);
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status));
    assert(WEXITSTATUS(status) == 23);
    return 0;
}
