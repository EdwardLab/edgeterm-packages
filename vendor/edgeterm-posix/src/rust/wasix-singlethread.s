.globl __tls_align
.globaltype __tls_align, i32, immutable
__tls_align:

.globl __tls_base
.globaltype __tls_base, i32
__tls_base:

.globl __tls_size
.globaltype __tls_size, i32, immutable
__tls_size:

.globl __wasm_init_tls
.type __wasm_init_tls,@function
__wasm_init_tls:
  .functype __wasm_init_tls (i32) -> ()
  end_function
