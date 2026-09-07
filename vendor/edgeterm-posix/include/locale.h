#ifndef EDGETERM_POSIX_OVERLAY_LOCALE_H
#define EDGETERM_POSIX_OVERLAY_LOCALE_H

#include_next <locale.h>

/*
 * Recent portability modules inspect private locale object layouts on known
 * hosts. The browser runtime intentionally keeps locale_t opaque and supports
 * the portable C and POSIX locale names. Select the upstream fake-locale path
 * only while that private inspection module is being compiled.
 */
#if defined(_GETLOCALENAME_L_UNSAFE_H) && !defined(HAVE_FAKE_LOCALES)
#define __OpenBSD__ 1
#define HAVE_FAKE_LOCALES 1
#endif

#endif
