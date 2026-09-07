#include <stddef.h>

extern char **environ;
extern int edgeterm_main_with_env(int argc, char **argv, char **envp);

int main(int argc, char **argv) {
    return edgeterm_main_with_env(argc, argv, environ);
}
