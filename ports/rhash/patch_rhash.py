#!/usr/bin/env python3
from pathlib import Path


source = Path("/build/source-root/RHash-1.4.6/parse_cmdline.c")
text = source.read_text()

text = text.replace(
    "typedef void(*opt_handler_t)(void);",
    "typedef void (*opt_handler_t)(options_t*, char*, unsigned);",
)

anchor = "/* supported program options */\ncmdline_opt_t cmdline_opt[] =\n"
wrappers = r'''/* WebAssembly requires exact indirect-call signatures. */
static void wasm_list_hashes(options_t* options, char* value, unsigned parameter)
{
	(void)options; (void)value; (void)parameter;
	list_hashes();
}

static void wasm_print_help(options_t* options, char* value, unsigned parameter)
{
	(void)options; (void)value; (void)parameter;
	print_help();
}

static void wasm_print_version(options_t* options, char* value, unsigned parameter)
{
	(void)options; (void)value; (void)parameter;
	print_version();
}

static void wasm_on_verbose(options_t* options, char* value, unsigned parameter)
{
	(void)value; (void)parameter;
	on_verbose(options);
}

static void wasm_add_hash_id(options_t* options, char* value, unsigned parameter)
{
	(void)value;
	add_hash_id(options, parameter);
}

static void wasm_accept_video(options_t* options, char* value, unsigned parameter)
{
	(void)value; (void)parameter;
	accept_video(options);
}

static void wasm_nya(options_t* options, char* value, unsigned parameter)
{
	(void)options; (void)value; (void)parameter;
	nya();
}

/* supported program options */
cmdline_opt_t cmdline_opt[] =
'''
if anchor not in text:
    raise SystemExit("RHash option table anchor was not found")
text = text.replace(anchor, wrappers, 1)

replacements = {
    "(opt_handler_t)list_hashes": "wasm_list_hashes",
    "(opt_handler_t)print_help": "wasm_print_help",
    "(opt_handler_t)print_version": "wasm_print_version",
    "(opt_handler_t)on_verbose": "wasm_on_verbose",
    "(opt_handler_t)add_hash_id": "wasm_add_hash_id",
    "(opt_handler_t)accept_video": "wasm_accept_video",
    "(opt_handler_t)nya": "wasm_nya",
}
for old, new in replacements.items():
    text = text.replace(old, new)

text = text.replace(
    "( (void(*)(options_t*, char*, unsigned))o->handler )(opts, value, o->param);",
    "o->handler(opts, value, o->param);",
)
text = text.replace(
    "( (void(*)(options_t*, unsigned))o->handler )(opts, o->param); /* call option handler */",
    "o->handler(opts, NULL, o->param); /* call option handler */",
)

source.write_text(text)
