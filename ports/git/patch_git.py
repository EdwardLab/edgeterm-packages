#!/usr/bin/env python3
from pathlib import Path
import sys


source = Path(sys.argv[1]) / "abspath.c"
text = source.read_text()
old = '''		if (lstat(resolved->buf, &st)) {
			/* error out unless this was the last component */
'''
new = '''		if (lstat(resolved->buf, &st)) {
#ifdef __wasi__
			if (errno == 0)
				errno = ENOENT;
#endif
			/* error out unless this was the last component */
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git path resolution block was not found")
source.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "path.c"
text = path.read_text()
old = '''void safe_create_dir(struct repository *repo, const char *dir, int share)
{
	if (mkdir(dir, 0777) < 0) {
		if (errno != EEXIST) {
			perror(dir);
			exit(1);
		}
	}
'''
new = '''void safe_create_dir(struct repository *repo, const char *dir, int share)
{
	if (mkdir(dir, 0777) < 0) {
		struct stat st;
		if (errno != EEXIST && (stat(dir, &st) < 0 || !S_ISDIR(st.st_mode))) {
			perror(dir);
			exit(1);
		}
	}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git directory creation block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "strbuf.c"
text = path.read_text()
old = '''\tfd = open(path, O_RDONLY);
\tif (fd < 0)
\t\treturn -1;
'''
new = '''\tfd = open(path, O_RDONLY);
\tif (fd < 0) {
#ifdef __wasi__
\t\tif (errno == 0)
\t\t\terrno = ENOENT;
#endif
\t\treturn -1;
\t}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git strbuf file read block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "setup.c"
text = path.read_text()
old = '''\tif (is_missing_file_error(errno)) {
\t\tfree(to_free);
\t\treturn 0; /* file does not exist */
\t}
'''
new = '''#ifdef __wasi__
\tif (errno == 0)
\t\terrno = ENOENT;
#endif
\tif (is_missing_file_error(errno)) {
\t\tfree(to_free);
\t\treturn 0; /* file does not exist */
\t}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git filename check block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "wrapper.c"
text = path.read_text()
old = '''FILE *fopen_or_warn(const char *path, const char *mode)
{
	FILE *fp = fopen(path, mode);

	if (fp)
		return fp;

	warn_on_fopen_errors(path);
	return NULL;
}
'''
new = '''FILE *fopen_or_warn(const char *path, const char *mode)
{
	FILE *fp = fopen(path, mode);

	if (fp)
		return fp;
#ifdef __wasi__
	if (errno == 0)
		errno = ENOENT;
#endif

	warn_on_fopen_errors(path);
	return NULL;
}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git fopen warning block was not found")
text = text.replace(old, new, 1)

old = '''int access_or_warn(const char *path, int mode, unsigned flag)
{
	int ret = access(path, mode);
	if (ret && !access_error_is_ok(errno, flag))
		warn_on_inaccessible(path);
	return ret;
}

int access_or_die(const char *path, int mode, unsigned flag)
{
	int ret = access(path, mode);
	if (ret && !access_error_is_ok(errno, flag))
		die_errno(_("unable to access '%s'"), path);
	return ret;
}
'''
new = '''int access_or_warn(const char *path, int mode, unsigned flag)
{
	int ret = access(path, mode);
#ifdef __wasi__
	if (ret && errno == 0)
		errno = ENOENT;
#endif
	if (ret && !access_error_is_ok(errno, flag))
		warn_on_inaccessible(path);
	return ret;
}

int access_or_die(const char *path, int mode, unsigned flag)
{
	int ret = access(path, mode);
#ifdef __wasi__
	if (ret && errno == 0)
		errno = ENOENT;
#endif
	if (ret && !access_error_is_ok(errno, flag))
		die_errno(_("unable to access '%s'"), path);
	return ret;
}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git access warning block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "attr.c"
text = path.read_text()
old = '''\tif (fd < 0) {
\t\twarn_on_fopen_errors(path);
\t\treturn NULL;
\t}
'''
new = '''\tif (fd < 0) {
#ifdef __wasi__
\t\tif (errno == 0)
\t\t\terrno = ENOENT;
#endif
\t\twarn_on_fopen_errors(path);
\t\treturn NULL;
\t}
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git attributes open block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "dir.c"
text = path.read_text()
old = '''\tif (fd < 0 || fstat(fd, &st) < 0) {
\t\tif (fd < 0)
\t\t\twarn_on_fopen_errors(fname);
\t\telse
'''
new = '''\tif (fd < 0 || fstat(fd, &st) < 0) {
\t\tif (fd < 0) {
#ifdef __wasi__
\t\t\tif (errno == 0)
\t\t\t\terrno = ENOENT;
#endif
\t\t\twarn_on_fopen_errors(fname);
\t\t} else
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git ignore open block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "object-file.c"
text = path.read_text()
old = '''retry:
\tret = 0;

\tif (object_creation_mode == OBJECT_CREATION_USES_RENAMES)
\t\tgoto try_rename;
'''
new = '''retry:
\tret = 0;

#ifdef __wasi__
\tgoto try_rename;
#endif
\tif (object_creation_mode == OBJECT_CREATION_USES_RENAMES)
\t\tgoto try_rename;
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git object finalization block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "run-command.c"
text = path.read_text()
old = '''int prepare_auto_maintenance(struct repository *r, int quiet,
\t\t\t     struct child_process *maint)
{
\tint enabled = 1, auto_detach;
'''
new = '''int prepare_auto_maintenance(struct repository *r, int quiet,
\t\t\t     struct child_process *maint)
{
\tint enabled = 1, auto_detach;
#ifdef __wasi__
\treturn 0;
#endif
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git automatic maintenance block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "refs/files-backend.c"
text = path.read_text()
old = '''\t*fd = open(path, O_APPEND | O_WRONLY | O_CREAT, 0666);
\treturn (*fd < 0) ? -1 : 0;
'''
new = '''\t*fd = open(path, O_APPEND | O_WRONLY | O_CREAT, 0666);
#ifdef __wasi__
\tif (*fd < 0 && errno == 0)
\t\terrno = ENOENT;
#endif
\treturn (*fd < 0) ? -1 : 0;
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git reflog creation block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "object-file.c"
text = path.read_text()
old = '''\tfd = git_mkstemp_mode(tmp->buf, 0444);
\tif (fd < 0 && dirlen && errno == ENOENT) {
'''
new = '''\tfd = git_mkstemp_mode(tmp->buf, 0444);
#ifdef __wasi__
\tif (fd < 0 && errno == 0)
\t\terrno = ENOENT;
#endif
\tif (fd < 0 && dirlen && errno == ENOENT) {
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git loose object temporary file block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "refs/packed-backend.c"
text = path.read_text()
old = '''\tfd = open(snapshot->refs->path, O_RDONLY);
\tif (fd < 0) {
\t\tif (errno == ENOENT) {
'''
new = '''\tfd = open(snapshot->refs->path, O_RDONLY);
\tif (fd < 0) {
#ifdef __wasi__
\t\tif (errno == 0)
\t\t\terrno = ENOENT;
#endif
\t\tif (errno == ENOENT) {
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git packed reference lookup block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "read-cache.c"
text = path.read_text()
old = '''	fd = open(path, O_RDONLY);
	if (fd < 0) {
		if (!must_exist && errno == ENOENT) {
'''
new = '''	fd = open(path, O_RDONLY);
	if (fd < 0) {
#ifdef __wasi__
		if (errno == 0)
			errno = ENOENT;
#endif
		if (!must_exist && errno == ENOENT) {
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git index lookup block was not found")
path.write_text(text.replace(old, new, 1))

path = Path(sys.argv[1]) / "refs/files-backend.c"
text = path.read_text()
old = '''	if (lstat(path, &st) < 0) {
		int ignore_errno;
		myerr = errno;
'''
new = '''	if (lstat(path, &st) < 0) {
		int ignore_errno;
		myerr = errno;
#ifdef __wasi__
		if (myerr == 0)
			myerr = ENOENT;
#endif
'''
if old not in text:
    if new in text:
        raise SystemExit(0)
    raise SystemExit("Git loose reference lookup block was not found")
path.write_text(text.replace(old, new, 1))
