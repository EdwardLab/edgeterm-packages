#ifndef EDGETERM_NETCAT_COMPAT_H
#define EDGETERM_NETCAT_COMPAT_H

#include <stddef.h>
#include <stdint.h>

#ifndef RPP_REQUIRE_TTY
#define RPP_REQUIRE_TTY 0x02
#endif

#ifndef SO_DEBUG
#define SO_DEBUG 1
#endif

#ifndef IPTOS_DSCP_VA
#define IPTOS_DSCP_VA 0x2c
#endif

long long strtonum(const char *text, long long minimum, long long maximum, const char **error);
size_t strlcpy(char *destination, const char *source, size_t size);
char *readpassphrase(const char *prompt, char *buffer, size_t size, int flags);
int b64_ntop(const unsigned char *source, size_t source_length, char *target, size_t target_size);

#endif
