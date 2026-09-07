#include <edgeterm/posix/compat.h>

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <mntent.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

int main(void) {
    void *allocation;
    wchar_t source[] = L"posix";
    wchar_t destination[6] = {0};
    char error_buffer[128];
    FILE *mount_table;
    struct mntent *mount_entry;
    struct statvfs filesystem_status;

#if defined(__wasi__)
    allocation = malloc(16);
    assert(allocation != NULL);
    (void)malloc_usable_size(allocation);
    free(allocation);
#else
    (void)allocation;
#endif
    assert(wmempcpy(destination, source, 6) == destination + 6);
    assert(wcscmp(destination, source) == 0);
    assert(strerror_r(ENOENT, error_buffer, sizeof(error_buffer)) == 0);
    assert(error_buffer[0] != '\0');
    mount_table = setmntent(_PATH_MOUNTED, "r");
    assert(mount_table != NULL);
    mount_entry = getmntent(mount_table);
    assert(mount_entry != NULL);
    assert(strcmp(mount_entry->mnt_dir, "/") == 0);
    assert(strcmp(mount_entry->mnt_type, "posixfs") == 0);
    assert(hasmntopt(mount_entry, "rw") != NULL);
    assert(hasmntopt(mount_entry, "bind") == NULL);
    assert(endmntent(mount_table) == 1);
    assert(statvfs("/", &filesystem_status) == 0);
    assert(filesystem_status.f_bsize > 0);
    assert(filesystem_status.f_blocks > 0);
    assert(filesystem_status.f_bfree <= filesystem_status.f_blocks);
#if defined(__wasi__)
    assert(filesystem_status.f_bsize == 4096);
    assert(filesystem_status.f_namemax == 255);
    assert(strcmp(filesystem_status.f_fstypename, "posixfs") == 0);
#endif
    assert(setenv("EDGETERM_STDIN_MODE", "pipe", 1) == 0);
    errno = 0;
    assert(edgeterm_posix_isatty(STDIN_FILENO) == 0);
    assert(errno == ENOTTY);
    assert(unsetenv("EDGETERM_STDIN_MODE") == 0);
    assert(setenv("EDGETERM_STDOUT_MODE", "file", 1) == 0);
    errno = 0;
    assert(edgeterm_posix_isatty(STDOUT_FILENO) == 0);
    assert(errno == ENOTTY);
    assert(unsetenv("EDGETERM_STDOUT_MODE") == 0);
#if defined(__wasi__)
    struct stat information;
    char link_buffer[32];

    assert(fdopen(STDIN_FILENO, "rb") == stdin);
    assert(fdopen(STDOUT_FILENO, "wb") == stdout);
    assert(fdopen(STDERR_FILENO, "wb") == stderr);
    errno = 0;
    assert(stat("/edgeterm-posix-missing", &information) == -1);
    assert(errno != 0);
    errno = 0;
    assert(readlink("/edgeterm-posix-not-a-link", link_buffer, sizeof(link_buffer)) == -1);
    assert(errno != 0);
    errno = 0;
    assert(mkfifo("/edgeterm-posix-fifo", 0600) == -1);
    assert(errno == ENOSYS);
    errno = 0;
    assert(mkfifoat(AT_FDCWD, "/edgeterm-posix-fifo", 0600) == -1);
    assert(errno == ENOSYS);
#endif
    assert(edgeterm_posix_capability("wide_memory") == EDGETERM_POSIX_COMPAT);
    assert(edgeterm_posix_capability("filesystem_statistics") == EDGETERM_POSIX_COMPAT);
    assert(edgeterm_posix_capability("mount_table") == EDGETERM_POSIX_COMPAT);
    assert(edgeterm_posix_capability("directory_namespace") == EDGETERM_POSIX_COMPAT);
    assert(strcmp(edgeterm_posix_profile_version(), "0.1.0") == 0);
    return 0;
}
