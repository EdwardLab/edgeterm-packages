#include <cstdio>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

struct PortableInterface {
    bool close() { return true; }
    bool open() { return true; }
    bool read() { return true; }
    bool stat() { return true; }
};

int main() {
    PortableInterface interface;
    if (!interface.open() || !interface.read() || !interface.stat() || !interface.close()) {
        return 1;
    }
    char byte = 0;
    return read(STDIN_FILENO, &byte, 0) < 0 ? 1 : 0;
}
