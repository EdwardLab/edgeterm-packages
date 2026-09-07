#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utime.h>
#include <edgeterm/posix/profile.h>

int main(void) {
    char *original_directory;
    char fchdir_directory[] = "/tmp/edgeterm-posix-fchdir.XXXXXX";
    struct stat fchdir_information;
    int directory_descriptor;
    int marker_descriptor;

    assert(edgeterm_posix_capability("working_directory") == EDGETERM_POSIX_COMPAT);
    assert(edgeterm_posix_capability("timestamp_conversion") == EDGETERM_POSIX_COMPAT);
    struct utimbuf legacy_times = { 100, 200 };

    original_directory = getcwd(NULL, 0);
    assert(original_directory != NULL);
    assert(mkdtemp(fchdir_directory) == fchdir_directory);
    assert(chdir(fchdir_directory) == 0);
    marker_descriptor = open("marker", O_CREAT | O_WRONLY, 0600);
    assert(marker_descriptor >= 0);
    assert(close(marker_descriptor) == 0);
    assert(utime("marker", &legacy_times) == 0);
    assert(stat("marker", &fchdir_information) == 0);
    assert(S_ISREG(fchdir_information.st_mode));
    directory_descriptor = open(".", O_RDONLY | O_DIRECTORY);
    assert(directory_descriptor >= 0);
    assert(chdir("/") == 0);
    assert(fchdir(directory_descriptor) == 0);
    {
        char current_directory[512];

        assert(getcwd(current_directory, sizeof(current_directory)) != NULL);
#ifdef __wasi__
        assert(strcmp(current_directory, fchdir_directory) == 0);
#endif
    }
    assert(stat("marker", &fchdir_information) == 0);
    assert(S_ISREG(fchdir_information.st_mode));
    assert(close(directory_descriptor) == 0);
    assert(unlink("marker") == 0);
    assert(chdir(original_directory) == 0);
    assert(rmdir(fchdir_directory) == 0);
    free(original_directory);
    char directory[512];
    char file_path[640];
    char slashed_file_path[642];
    const char *base = getenv("EDGETERM_POSIX_TEST_DIRECTORY_BASE");
    int file_descriptor;
    struct stat information;
    const char *existing = getenv("EDGETERM_POSIX_TEST_RMDIR_EXISTING");
    const char *mounted_base = getenv("EDGETERM_POSIX_TEST_FILE_BASE");

    if (mounted_base != NULL && mounted_base[0] != '\0') {
        FILE *stream;

        assert(snprintf(
            file_path,
            sizeof(file_path),
            "%s/config.lock",
            mounted_base
        ) > 0);
        errno = 0;
        file_descriptor = open(
            file_path,
            O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC,
            0600
        );
        if (file_descriptor < 0 && errno == EINVAL) {
            file_descriptor = open(
                file_path,
                O_RDWR | O_CREAT | O_EXCL,
                0600
            );
        }
        assert(file_descriptor >= 0);
        stream = fdopen(file_descriptor, "w");
        if (stream == NULL) {
            fprintf(stderr, "fdopen mounted file returned errno %d\n", errno);
        }
        assert(stream != NULL);
        assert(fputs("[core]\n", stream) >= 0);
        assert(fclose(stream) == 0);
        assert(unlink(file_path) == 0);
        errno = 0;
        assert(open(file_path, O_RDONLY) == -1);
        assert(errno == ENOENT);
        assert(snprintf(
            file_path,
            sizeof(file_path),
            "%s/missing-directory/config.lock",
            mounted_base
        ) > 0);
        errno = 0;
        assert(open(file_path, O_RDWR | O_CREAT | O_EXCL, 0600) == -1);
        assert(errno == ENOENT);
        assert(snprintf(
            directory,
            sizeof(directory),
            "%s/object-directory",
            mounted_base
        ) > 0);
        assert(mkdir(directory, 0777) == 0);
        assert(chmod(directory, 0755) == 0);
        assert(snprintf(
            file_path,
            sizeof(file_path),
            "%s/tmp_obj_XXXXXX",
            directory
        ) > 0);
        file_descriptor = mkstemp(file_path);
        assert(file_descriptor >= 0);
        assert(close(file_descriptor) == 0);
        assert(unlink(file_path) == 0);
        assert(snprintf(
            file_path,
            sizeof(file_path),
            "%s/readonly-mode-object",
            directory
        ) > 0);
        file_descriptor = open(
            file_path,
            O_RDWR | O_CREAT | O_EXCL,
            0444
        );
        assert(file_descriptor >= 0);
        assert(write(file_descriptor, "x", 1) == 1);
        assert(close(file_descriptor) == 0);
        assert(stat(file_path, &information) == 0);
        /* Host-backed WASIX mounts may not expose permission bits. */
        assert(information.st_size == 1);
        assert(unlink(file_path) == 0);
        assert(rmdir(directory) == 0);
        return 0;
    }

    if (existing != NULL && existing[0] != '\0') {
        if (rmdir(existing) != 0) {
            fprintf(stderr, "rmdir existing failed with errno %d\n", errno);
            return 2;
        }
        errno = 0;
        assert(stat(existing, &information) == -1);
        assert(errno == ENOENT);
        errno = 0;
        assert(open(existing, O_RDONLY | O_NONBLOCK | O_DIRECTORY) == -1);
        if (errno != ENOENT) {
            fprintf(stderr, "open missing mounted directory returned errno %d\n", errno);
        }
        assert(errno == ENOENT);
        return 0;
    }

    if (base != NULL && base[0] != '\0') {
        assert(snprintf(
            directory,
            sizeof(directory),
            "%s/edgeterm-posix-rmdir-test.XXXXXX",
            base
        ) > 0);
    } else {
        assert(snprintf(
            directory,
            sizeof(directory),
            "edgeterm-posix-rmdir-test.XXXXXX"
        ) > 0);
    }
    assert(mkdtemp(directory) == directory);
    assert(stat(directory, &information) == 0);
    assert(S_ISDIR(information.st_mode));
    assert(snprintf(
        file_path,
        sizeof(file_path),
        "%s/file",
        directory
    ) > 0);
    file_descriptor = open(file_path, O_CREAT | O_WRONLY, 0600);
    assert(file_descriptor >= 0);
    assert(close(file_descriptor) == 0);
    assert(stat(file_path, &information) == 0);
    assert(S_ISREG(information.st_mode));
    assert(snprintf(
        slashed_file_path,
        sizeof(slashed_file_path),
        "%s/",
        file_path
    ) > 0);
    errno = 0;
    assert(stat(slashed_file_path, &information) == -1);
    assert(errno != 0);
    assert(unlink(file_path) == 0);
    assert(rmdir(directory) == 0);
    errno = 0;
    assert(stat(directory, &information) == -1);
    assert(errno == ENOENT);
    errno = 0;
    assert(open(directory, O_RDONLY | O_NONBLOCK | O_DIRECTORY) == -1);
    if (errno != ENOENT) {
        fprintf(stderr, "open missing directory returned errno %d\n", errno);
    }
    assert(errno == ENOENT);
    return 0;
}
