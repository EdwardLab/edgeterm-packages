from pathlib import Path
import sys


root = Path(sys.argv[1])

for relative_path in ("sshkey.c", "sshbuf-misc.c", "hostfile.c"):
    path = root / relative_path
    content = path.read_text()
    old = "#include <resolv.h>"
    new = '#include "openbsd-compat/base64.h"'
    if new not in content:
        if old not in content:
            raise RuntimeError(f"OpenSSH base64 include was not found in {relative_path}")
        path.write_text(content.replace(old, new, 1))

header = root / "openbsd-compat/getrrsetbyname.h"
content = header.read_text()
old = "#include <resolv.h>"
new = """#if !defined(__wasi__)
#include <resolv.h>
#endif"""
if new not in content:
    if old not in content:
        raise RuntimeError("OpenSSH resolver include was not found")
    header.write_text(content.replace(old, new, 1))

implementation = root / "openbsd-compat/getrrsetbyname.c"
content = implementation.read_text()
old = "#if !defined (HAVE_GETRRSETBYNAME) && !defined (HAVE_LDNS)"
new = "#if !defined (HAVE_GETRRSETBYNAME) && !defined (HAVE_LDNS) && !defined (__wasi__)"
if new not in content:
    if old not in content:
        raise RuntimeError("OpenSSH resolver implementation guard was not found")
    implementation.write_text(content.replace(old, new, 1))

dns = root / "dns.c"
content = dns.read_text()
start = """verify_host_key_dns(const char *hostname, struct sockaddr *address,
    struct sshkey *hostkey, int *flags)
{"""
replacement = """verify_host_key_dns(const char *hostname, struct sockaddr *address,
    struct sshkey *hostkey, int *flags)
{
#if defined(__wasi__)
	(void)hostname;
	(void)address;
	(void)hostkey;
	*flags = 0;
	return -1;
#else"""
if replacement not in content:
    if start not in content:
        raise RuntimeError("OpenSSH DNS verification function was not found")
    content = content.replace(start, replacement, 1)
    marker = """	return 0;
}

/*
 * Export the fingerprint"""
    replacement_end = """	return 0;
#endif
}

/*
 * Export the fingerprint"""
    if marker not in content:
        raise RuntimeError("OpenSSH DNS verification function end was not found")
    content = content.replace(marker, replacement_end, 1)
    dns.write_text(content)

fdpass = root / "monitor_fdpass.c"
content = fdpass.read_text()
for macro in ("HAVE_SENDMSG", "HAVE_RECVMSG"):
    old = f"#if defined({macro}) && (defined(HAVE_ACCRIGHTS_IN_MSGHDR) || defined(HAVE_CONTROL_IN_MSGHDR))"
    new = f"#if !defined(__wasi__) && defined({macro}) && (defined(HAVE_ACCRIGHTS_IN_MSGHDR) || defined(HAVE_CONTROL_IN_MSGHDR))"
    if new not in content:
        if old not in content:
            raise RuntimeError(f"OpenSSH fd passing guard for {macro} was not found")
        content = content.replace(old, new, 1)
fdpass.write_text(content)

curve = root / "smult_curve25519_ref.c"
content = curve.read_text()
content = content.replace(
    "static void select(unsigned int p[64],unsigned int q[64],",
    "static void curve_select(unsigned int p[64],unsigned int q[64],",
    1,
)
content = content.replace("    select(xzmb,xzm1b,xzm,xzm1,b);", "    curve_select(xzmb,xzm1b,xzm,xzm1,b);")
content = content.replace("    select(xzm,xzm1,xznb,xzn1b,b);", "    curve_select(xzm,xzm1,xznb,xzn1b,b);")
curve.write_text(content)

fallback_passwd = """#if defined(__wasi__)
\tif (pw == NULL) {
\t\tstatic struct passwd edgeterm_pw = {
\t\t\t.pw_name = \"user\",
\t\t\t.pw_passwd = \"x\",
\t\t\t.pw_uid = 1000,
\t\t\t.pw_gid = 1000,
\t\t\t.pw_gecos = \"EdgeTerm User\",
\t\t\t.pw_dir = \"/home/user\",
\t\t\t.pw_shell = \"/bin/ash\",
\t\t};
\t\tpw = &edgeterm_pw;
\t}
#endif
"""

for relative_path, marker in (
    ("ssh-keygen.c", "\tpw = getpwuid(getuid());\n\tif (!pw)\n"),
    ("ssh.c", "\tpw = getpwuid(getuid());\n\tif (!pw) {\n"),
):
    path = root / relative_path
    content = path.read_text()
    replacement = marker.split("\n", 1)[0] + "\n" + fallback_passwd + marker.split("\n", 1)[1]
    if fallback_passwd not in content:
        if marker not in content:
            raise RuntimeError(f"OpenSSH passwd lookup was not found in {relative_path}")
        path.write_text(content.replace(marker, replacement, 1))

makefile = root / "Makefile.in"
lines = makefile.read_text().splitlines()
client_targets = (
    "TARGETS=ssh$(EXEEXT) ssh-add$(EXEEXT) ssh-keygen$(EXEEXT) "
    "ssh-keyscan" + "$" + "{EXEEXT} ssh-agent$(EXEEXT) scp$(EXEEXT) sftp$(EXEEXT)"
)
for index, line in enumerate(lines):
    if line.startswith("TARGETS="):
        lines[index] = client_targets
        break
else:
    raise RuntimeError("OpenSSH TARGETS declaration was not found")

excluded_install_entries = (
    "sshd$(EXEEXT)",
    "sshd-session$(EXEEXT)",
    "sshd-auth$(EXEEXT)",
    "ssh-keysign$(EXEEXT)",
    "ssh-pkcs11-helper$(EXEEXT)",
    "ssh-sk-helper$(EXEEXT)",
    "sftp-server$(EXEEXT)",
    "sshd.8.out",
    "sshd_config.5.out",
    "ssh-keysign.8.out",
    "ssh-pkcs11-helper.8.out",
    "ssh-sk-helper.8.out",
    "sftp-server.8.out",
)
inside_install_files = False
filtered = []
for line in lines:
    if line.startswith("install-files:"):
        inside_install_files = True
    elif line.startswith("install-sysconf:"):
        inside_install_files = False
    if inside_install_files and any(entry in line for entry in excluded_install_entries):
        continue
    filtered.append(line)
makefile.write_text("\n".join(filtered) + "\n")
