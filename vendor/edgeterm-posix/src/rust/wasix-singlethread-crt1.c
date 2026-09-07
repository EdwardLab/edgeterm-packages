typedef unsigned int wasi_exit_code_t;

__attribute__((
    __import_module__("wasi_snapshot_preview1"),
    __import_name__("proc_exit"),
    __noreturn__
))
extern void edgeterm_wasi_proc_exit(wasi_exit_code_t code);

extern void __wasm_call_ctors(void);
extern void __wasm_call_dtors(void);
extern int __main_void(void);

__attribute__((export_name("_start")))
void _start(void) {
    __wasm_call_ctors();
    int code = __main_void();
    __wasm_call_dtors();
    if (code != 0) {
        edgeterm_wasi_proc_exit((wasi_exit_code_t)code);
    }
}
