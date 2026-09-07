#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int is_safe_absolute_path(const char *path) {
    return path != NULL && path[0] == '/' &&
        strcmp(path, "/..") != 0 && strstr(path, "/../") == NULL;
}

__attribute__((constructor)) static void edgeterm_posix_restore_working_directory(void) {
    const char *pwd = getenv("PWD");
    char current[4096];

    if (!is_safe_absolute_path(pwd)) {
        return;
    }
    if (getcwd(current, sizeof(current)) != NULL && strcmp(current, pwd) == 0) {
        return;
    }
    (void)chdir(pwd);
}
