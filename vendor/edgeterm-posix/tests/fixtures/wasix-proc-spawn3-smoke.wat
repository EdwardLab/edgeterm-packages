(module
  (import "wasix_32v1" "proc_spawn3"
    (func $proc_spawn3
      (param i32 i32 i32 i32 i32 i32 i32 i32 i32 i32 i32 i32 i32 i32)
      (result i32)))
  (memory (export "memory") 1)
  (func (export "_start")))
