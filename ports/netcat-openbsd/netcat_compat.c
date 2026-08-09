#include "netcat_compat.h"

#include <errno.h>
#include <err.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

void
vwarn(const char *format, va_list arguments)
{
	int saved_errno = errno;
	if (format != NULL) {
		vfprintf(stderr, format, arguments);
		fputs(": ", stderr);
	}
	fputs(strerror(saved_errno), stderr);
	fputc('\n', stderr);
}

void
vwarnx(const char *format, va_list arguments)
{
	if (format != NULL)
		vfprintf(stderr, format, arguments);
	fputc('\n', stderr);
}

void
warn(const char *format, ...)
{
	va_list arguments;
	va_start(arguments, format);
	vwarn(format, arguments);
	va_end(arguments);
}

void
warnx(const char *format, ...)
{
	va_list arguments;
	va_start(arguments, format);
	vwarnx(format, arguments);
	va_end(arguments);
}

_Noreturn void
verr(int status, const char *format, va_list arguments)
{
	vwarn(format, arguments);
	exit(status);
}

_Noreturn void
verrx(int status, const char *format, va_list arguments)
{
	vwarnx(format, arguments);
	exit(status);
}

_Noreturn void
err(int status, const char *format, ...)
{
	va_list arguments;
	va_start(arguments, format);
	verr(status, format, arguments);
}

_Noreturn void
errx(int status, const char *format, ...)
{
	va_list arguments;
	va_start(arguments, format);
	verrx(status, format, arguments);
}

long long
strtonum(const char *text, long long minimum, long long maximum, const char **error)
{
	char *end = NULL;
	long long value;

	if (error != NULL)
		*error = NULL;
	errno = 0;
	value = strtoll(text, &end, 10);
	if (text == end || end == NULL || *end != '\0') {
		if (error != NULL)
			*error = "invalid";
		errno = EINVAL;
		return 0;
	}
	if ((value == LLONG_MIN && errno == ERANGE) || value < minimum) {
		if (error != NULL)
			*error = "too small";
		errno = ERANGE;
		return 0;
	}
	if ((value == LLONG_MAX && errno == ERANGE) || value > maximum) {
		if (error != NULL)
			*error = "too large";
		errno = ERANGE;
		return 0;
	}
	return value;
}

size_t
strlcpy(char *destination, const char *source, size_t size)
{
	size_t length = strlen(source);
	if (size != 0) {
		size_t count = length >= size ? size - 1 : length;
		memcpy(destination, source, count);
		destination[count] = '\0';
	}
	return length;
}

char *
readpassphrase(const char *prompt, char *buffer, size_t size, int flags)
{
	FILE *input = stdin;
	FILE *output = stderr;
	(void)flags;

	if (size == 0) {
		errno = EINVAL;
		return NULL;
	}
	fputs(prompt, output);
	fflush(output);
	if (fgets(buffer, (int)size, input) == NULL)
		return NULL;
	buffer[strcspn(buffer, "\r\n")] = '\0';
	return buffer;
}

int
b64_ntop(const unsigned char *source, size_t source_length, char *target, size_t target_size)
{
	static const char alphabet[] =
	    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
	size_t input = 0;
	size_t output = 0;

	if (target_size < 4 * ((source_length + 2) / 3) + 1) {
		errno = EMSGSIZE;
		return -1;
	}
	while (input < source_length) {
		uint32_t value = (uint32_t)source[input++] << 16;
		int remaining = 0;
		if (input < source_length) {
			value |= (uint32_t)source[input++] << 8;
			remaining = 1;
		}
		if (input < source_length) {
			value |= source[input++];
			remaining = 2;
		}
		target[output++] = alphabet[(value >> 18) & 0x3f];
		target[output++] = alphabet[(value >> 12) & 0x3f];
		target[output++] = remaining >= 1 ? alphabet[(value >> 6) & 0x3f] : '=';
		target[output++] = remaining >= 2 ? alphabet[value & 0x3f] : '=';
	}
	target[output] = '\0';
	return (int)output;
}
