#include <edgeterm/posix/profile.h>

#include <stddef.h>
#include <string.h>

struct capability_entry {
    const char *name;
    int status;
};

static const struct capability_entry capabilities[] = {
    {"advisory_memory", EDGETERM_POSIX_ADVISORY},
    {"cmsg_layout", EDGETERM_POSIX_COMPAT},
    {"file_locking", EDGETERM_POSIX_UNSUPPORTED},
    {"filesystem", EDGETERM_POSIX_NATIVE},
    {"filesystem_statistics", EDGETERM_POSIX_COMPAT},
    {"mount_table", EDGETERM_POSIX_COMPAT},
    {"directory_namespace", EDGETERM_POSIX_COMPAT},
    {"working_directory", EDGETERM_POSIX_COMPAT},
    {"identity", EDGETERM_POSIX_COMPAT},
    {"interface_enumeration", EDGETERM_POSIX_UNSUPPORTED},
    {"locale_name", EDGETERM_POSIX_COMPAT},
    {"path_error_reporting", EDGETERM_POSIX_COMPAT},
    {"process_spawn", EDGETERM_POSIX_NATIVE},
    {"processor_topology", EDGETERM_POSIX_ADVISORY},
    {"random", EDGETERM_POSIX_COMPAT},
    {"stdio_locking", EDGETERM_POSIX_COMPAT},
    {"system_load", EDGETERM_POSIX_ADVISORY},
    {"terminal", EDGETERM_POSIX_NATIVE},
    {"timestamp_conversion", EDGETERM_POSIX_COMPAT},
    {"thread_local_storage", EDGETERM_POSIX_COMPAT},
    {"signal_mask_jump", EDGETERM_POSIX_UNSUPPORTED},
    {"virtual_root", EDGETERM_POSIX_UNSUPPORTED},
    {"wide_memory", EDGETERM_POSIX_COMPAT}
};

__attribute__((weak)) int edgeterm_posix_capability(const char *name) {
    size_t index;

    if (name == NULL) {
        return EDGETERM_POSIX_UNSUPPORTED;
    }
    for (index = 0; index < sizeof(capabilities) / sizeof(capabilities[0]); index++) {
        if (strcmp(name, capabilities[index].name) == 0) {
            return capabilities[index].status;
        }
    }
    return EDGETERM_POSIX_UNSUPPORTED;
}

__attribute__((weak)) const char *edgeterm_posix_status_name(int status) {
    switch (status) {
        case EDGETERM_POSIX_NATIVE:
            return "native";
        case EDGETERM_POSIX_COMPAT:
            return "compat";
        case EDGETERM_POSIX_ADVISORY:
            return "advisory";
        default:
            return "unsupported";
    }
}

__attribute__((weak)) const char *edgeterm_posix_profile_version(void) {
    return EDGETERM_POSIX_VERSION_STRING;
}
