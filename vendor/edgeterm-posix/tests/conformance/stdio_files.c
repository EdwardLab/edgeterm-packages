#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(void) {
#if defined(__wasi__)
    const char *path = "/tmp/edgeterm-posix-stdio-file";
    const char *missing = "/tmp/edgeterm-posix-stdio-missing";
    char buffer[16] = {0};
    FILE *stream;

    remove(path);
    remove(missing);
    errno = 0;
    assert(fopen(missing, "r") == NULL);
    assert(errno == ENOENT);

    stream = fopen(path, "w+");
    assert(stream != NULL);
    assert(fputs("ready", stream) >= 0);
    assert(fseek(stream, 0, SEEK_SET) == 0);
    assert(fread(buffer, 1, 5, stream) == 5);
    assert(strcmp(buffer, "ready") == 0);
    assert(fclose(stream) == 0);
    assert(remove(path) == 0);
#endif
    return 0;
}
