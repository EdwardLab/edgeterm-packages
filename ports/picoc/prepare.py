#!/usr/bin/env python3
from pathlib import Path
import sys


source = Path(sys.argv[1])
platform_header = source / "platform.h"
header_text = platform_header.read_text(encoding="utf-8")
header_text = header_text.replace("#define USE_READLINE", "#undef USE_READLINE")
platform_header.write_text(header_text, encoding="utf-8")

interpreter_header = source / "interpreter.h"
interpreter_text = interpreter_header.read_text(encoding="utf-8")
interpreter_text = interpreter_text.replace("    IOFILE CStdOutBase;\n", "")
interpreter_header.write_text(interpreter_text, encoding="utf-8")

stdio_source = source / "cstdlib" / "stdio.c"
stdio_text = stdio_source.read_text(encoding="utf-8")
stdio_text = stdio_text.replace("sizeof(FILE)", "sizeof(void *)")
stdio_text = stdio_text.replace("static int L_tmpnamValue = L_tmpnam;", "static int L_tmpnamValue = 20;")
stdio_source.write_text(stdio_text, encoding="utf-8")

unistd_source = source / "cstdlib" / "unistd.c"
unistd_text = unistd_source.read_text(encoding="utf-8")
compatibility = r'''
#include <errno.h>
static int PicoCGetdtablesize(void) { return 256; }
static int PicoCLockf(int fd, int command, off_t length) {
    (void)fd; (void)command; (void)length; errno = ENOSYS; return -1;
}
static int PicoCNice(int increment) { (void)increment; return 0; }
static int PicoCPause(void) { errno = EINTR; return -1; }
static int PicoCSetregid(gid_t real_id, gid_t effective_id) {
    (void)real_id; (void)effective_id; errno = ENOSYS; return -1;
}
static int PicoCSetreuid(uid_t real_id, uid_t effective_id) {
    (void)real_id; (void)effective_id; errno = ENOSYS; return -1;
}
static int PicoCChroot(const char *path) {
    (void)path; errno = ENOSYS; return -1;
}
static char *PicoCCtermid(char *buffer) {
    static char terminal_name[] = "/dev/tty";
    if (buffer != NULL) {
        strcpy(buffer, terminal_name);
        return buffer;
    }
    return terminal_name;
}
static int PicoCFchdir(int fd) { (void)fd; errno = ENOSYS; return -1; }
static char *PicoCGetlogin(void) { return "user"; }
static int PicoCGetloginR(char *buffer, size_t size) {
    static const char login[] = "user";
    if (buffer == NULL || size < sizeof(login)) { return ERANGE; }
    memcpy(buffer, login, sizeof(login));
    return 0;
}
static void PicoCSync(void) {}
#define getdtablesize PicoCGetdtablesize
#define lockf PicoCLockf
#define nice PicoCNice
#define pause PicoCPause
#define setregid PicoCSetregid
#define setreuid PicoCSetreuid
#define chroot PicoCChroot
#define ctermid PicoCCtermid
#define fchdir PicoCFchdir
#define getlogin PicoCGetlogin
#define getlogin_r PicoCGetloginR
#define sync PicoCSync
'''
unistd_text = unistd_text.replace('#include "../interpreter.h"', f'#include "../interpreter.h"\n{compatibility}', 1)
unistd_source.write_text(unistd_text, encoding="utf-8")
