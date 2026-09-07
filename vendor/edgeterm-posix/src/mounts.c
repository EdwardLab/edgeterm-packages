#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <mntent.h>

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct synthetic_mount_stream {
    FILE *stream;
    char *buffer;
    struct synthetic_mount_stream *next;
};

static struct synthetic_mount_stream *synthetic_mount_streams;

static int is_default_mount_table(const char *filename) {
    return filename != NULL && (
        strcmp(filename, _PATH_MOUNTED) == 0 ||
        strcmp(filename, "/proc/mounts") == 0 ||
        strcmp(filename, "/proc/self/mounts") == 0
    );
}

static FILE *open_synthetic_mount_table(void) {
    static const char contents[] = "rootfs / posixfs rw 0 0\n";
    struct synthetic_mount_stream *entry;
    char *buffer;
    FILE *stream;

    entry = malloc(sizeof(*entry));
    buffer = malloc(sizeof(contents));
    if (entry == NULL || buffer == NULL) {
        free(entry);
        free(buffer);
        errno = ENOMEM;
        return NULL;
    }
    memcpy(buffer, contents, sizeof(contents));
    stream = fmemopen(buffer, sizeof(contents) - 1, "r");
    if (stream == NULL) {
        free(buffer);
        free(entry);
        return NULL;
    }
    entry->stream = stream;
    entry->buffer = buffer;
    entry->next = synthetic_mount_streams;
    synthetic_mount_streams = entry;
    return stream;
}

__attribute__((weak)) FILE *setmntent(const char *filename, const char *type) {
    FILE *stream;

    if (filename == NULL || type == NULL) {
        errno = EINVAL;
        return NULL;
    }
    stream = fopen(filename, type);
    if (stream != NULL || !is_default_mount_table(filename) || type[0] != 'r') {
        return stream;
    }
    return open_synthetic_mount_table();
}

static char *next_field(char **cursor) {
    char *start = *cursor;
    char *end;

    start += strspn(start, " \t");
    if (*start == '\0' || *start == '\n' || *start == '#') {
        *cursor = start;
        return NULL;
    }
    end = start + strcspn(start, " \t\r\n");
    if (*end != '\0') {
        *end++ = '\0';
    }
    *cursor = end;
    return start;
}

__attribute__((weak)) struct mntent *getmntent_r(
    FILE *stream,
    struct mntent *result,
    char *buffer,
    int buffer_size
) {
    if (stream == NULL || result == NULL || buffer == NULL || buffer_size <= 0) {
        errno = EINVAL;
        return NULL;
    }

    while (fgets(buffer, buffer_size, stream) != NULL) {
        char *cursor = buffer;
        char *frequency;
        char *pass_number;

        result->mnt_fsname = next_field(&cursor);
        if (result->mnt_fsname == NULL) {
            continue;
        }
        result->mnt_dir = next_field(&cursor);
        result->mnt_type = next_field(&cursor);
        result->mnt_opts = next_field(&cursor);
        frequency = next_field(&cursor);
        pass_number = next_field(&cursor);
        if (result->mnt_dir == NULL || result->mnt_type == NULL ||
            result->mnt_opts == NULL) {
            errno = EINVAL;
            return NULL;
        }
        result->mnt_freq = frequency != NULL ? atoi(frequency) : 0;
        result->mnt_passno = pass_number != NULL ? atoi(pass_number) : 0;
        return result;
    }
    return NULL;
}

__attribute__((weak)) struct mntent *getmntent(FILE *stream) {
    static struct mntent result;
    static char buffer[4096];

    return getmntent_r(stream, &result, buffer, (int)sizeof(buffer));
}

__attribute__((weak)) int addmntent(FILE *stream, const struct mntent *entry) {
    if (stream == NULL || entry == NULL || entry->mnt_fsname == NULL ||
        entry->mnt_dir == NULL || entry->mnt_type == NULL ||
        entry->mnt_opts == NULL) {
        errno = EINVAL;
        return 1;
    }
    return fprintf(
        stream,
        "%s %s %s %s %d %d\n",
        entry->mnt_fsname,
        entry->mnt_dir,
        entry->mnt_type,
        entry->mnt_opts,
        entry->mnt_freq,
        entry->mnt_passno
    ) < 0;
}

__attribute__((weak)) int endmntent(FILE *stream) {
    struct synthetic_mount_stream **cursor = &synthetic_mount_streams;

    while (*cursor != NULL) {
        struct synthetic_mount_stream *entry = *cursor;

        if (entry->stream == stream) {
            *cursor = entry->next;
            fclose(stream);
            free(entry->buffer);
            free(entry);
            return 1;
        }
        cursor = &entry->next;
    }
    if (stream != NULL) {
        fclose(stream);
    }
    return 1;
}

__attribute__((weak)) char *hasmntopt(const struct mntent *entry, const char *option) {
    const char *cursor;
    size_t option_length;

    if (entry == NULL || entry->mnt_opts == NULL || option == NULL ||
        option[0] == '\0') {
        return NULL;
    }
    option_length = strlen(option);
    cursor = entry->mnt_opts;
    while (*cursor != '\0') {
        const char *end = strchr(cursor, ',');
        size_t length = end != NULL ? (size_t)(end - cursor) : strlen(cursor);

        if (length == option_length && strncmp(cursor, option, length) == 0) {
            return (char *)cursor;
        }
        if (end == NULL) {
            break;
        }
        cursor = end + 1;
    }
    return NULL;
}
