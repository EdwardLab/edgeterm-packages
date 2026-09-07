from __future__ import annotations

import importlib.util
import hashlib
import lzma
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ports", ROOT / "scripts/ports.py")
PORTS_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = PORTS_MODULE
SPEC.loader.exec_module(PORTS_MODULE)
ACCEPTANCE_SPEC = importlib.util.spec_from_file_location("acceptance", ROOT / "scripts/acceptance.py")
ACCEPTANCE_MODULE = importlib.util.module_from_spec(ACCEPTANCE_SPEC)
assert ACCEPTANCE_SPEC and ACCEPTANCE_SPEC.loader
sys.modules[ACCEPTANCE_SPEC.name] = ACCEPTANCE_MODULE
ACCEPTANCE_SPEC.loader.exec_module(ACCEPTANCE_MODULE)
REPOSITORY_SPEC = importlib.util.spec_from_file_location("repository", ROOT / "scripts/repository.py")
REPOSITORY_MODULE = importlib.util.module_from_spec(REPOSITORY_SPEC)
assert REPOSITORY_SPEC and REPOSITORY_SPEC.loader
sys.modules[REPOSITORY_SPEC.name] = REPOSITORY_MODULE
REPOSITORY_SPEC.loader.exec_module(REPOSITORY_MODULE)
SOURCE_AUDIT_SPEC = importlib.util.spec_from_file_location("source_audit", ROOT / "scripts/source_audit.py")
SOURCE_AUDIT_MODULE = importlib.util.module_from_spec(SOURCE_AUDIT_SPEC)
assert SOURCE_AUDIT_SPEC and SOURCE_AUDIT_SPEC.loader
sys.modules[SOURCE_AUDIT_SPEC.name] = SOURCE_AUDIT_MODULE
SOURCE_AUDIT_SPEC.loader.exec_module(SOURCE_AUDIT_MODULE)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ports = PORTS_MODULE.load_ports()

    def test_catalog_delivers_at_least_one_hundred_packages(self) -> None:
        PORTS_MODULE.validate_catalog(self.ports)
        self.assertGreaterEqual(sum(port.user_visible for port in self.ports.values()), 100)

    def test_all_user_visible_packages_require_pristine_sources(self) -> None:
        for port in self.ports.values():
            if not port.user_visible:
                continue
            with self.subTest(package=port.name):
                self.assertTrue(port.data["build"].get("pristine_source"))

    def test_batches_cover_catalog_exactly_once(self) -> None:
        batches = PORTS_MODULE.load_batches(self.ports)
        flattened = [package for packages in batches.values() for package in packages]
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(set(flattened), {name for name, port in self.ports.items() if port.user_visible})

    def test_every_source_is_pinned(self) -> None:
        for port in self.ports.values():
            self.assertRegex(port.source_sha256, r"^[a-f0-9]{64}$")
            self.assertTrue(port.source_url.startswith("https://"))

    def test_build_dependencies_are_known_and_acyclic(self) -> None:
        PORTS_MODULE.validate_catalog(self.ports)
        for port in self.ports.values():
            for dependency in port.data["build"].get("dependencies", []):
                self.assertIn(dependency, self.ports)

    def test_runtime_exec_dependencies_are_known(self) -> None:
        PORTS_MODULE.validate_catalog(self.ports)
        self.assertEqual(self.ports["bison"].data["runtime"]["exec_dependencies"], ["m4"])
        for port in self.ports.values():
            for dependency in port.data.get("runtime", {}).get("exec_dependencies", []):
                self.assertIn(dependency, self.ports)

    def test_runtime_bundle_uses_executable_dependency_closure(self) -> None:
        dependencies = PORTS_MODULE.runtime_bundle_dependencies(self.ports["bison"], self.ports)
        self.assertEqual([dependency.name for dependency in dependencies], ["m4"])

    def test_runtime_bundle_versions_are_semver(self) -> None:
        self.assertEqual(PORTS_MODULE.runtime_semver("2026-06-04"), "2026.6.4")
        self.assertEqual(PORTS_MODULE.runtime_semver("10.4p1"), "10.4.1")
        self.assertEqual(PORTS_MODULE.runtime_semver("0.5.13.5"), "0.5.13-5")
        self.assertEqual(PORTS_MODULE.runtime_semver("708"), "708.0.0")

    def test_library_dependencies_are_not_runtime_executables(self) -> None:
        dependencies = PORTS_MODULE.runtime_bundle_dependencies(self.ports["bash"], self.ports)
        self.assertEqual(dependencies, [])

    def test_build_cache_ignores_package_assembly_functions(self) -> None:
        names = {function.__name__ for function in PORTS_MODULE.build_pipeline_sources()}
        self.assertEqual(names, {"extraction_command", "configure_script", "build_port"})
        self.assertNotIn("build_runtime_bundle", names)
        self.assertNotIn("package_port", names)

    def test_rust_target_cache_is_invalidated_only_when_the_abi_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "cargo-target" / "wasm32-wasmer-wasi"
            target.mkdir(parents=True)
            (target / "old.rlib").write_bytes(b"old")
            compatibility = root / "compatibility.rs"
            compatibility.write_text("pub const ABI: u8 = 1;\n", encoding="utf-8")

            self.assertTrue(
                PORTS_MODULE.refresh_rust_target_cache(
                    root, "wasm32-wasmer-wasi", [compatibility]
                )
            )
            self.assertFalse(target.exists())
            target.mkdir(parents=True)
            (target / "kept.rlib").write_bytes(b"kept")
            self.assertFalse(
                PORTS_MODULE.refresh_rust_target_cache(
                    root, "wasm32-wasmer-wasi", [compatibility]
                )
            )
            self.assertTrue((target / "kept.rlib").is_file())

            compatibility.write_text("pub const ABI: u8 = 2;\n", encoding="utf-8")
            self.assertTrue(
                PORTS_MODULE.refresh_rust_target_cache(
                    root, "wasm32-wasmer-wasi", [compatibility]
                )
            )
            self.assertFalse(target.exists())

    def test_multi_command_packages_receive_runtime_bundles(self) -> None:
        source = (ROOT / "scripts/ports.py").read_text(encoding="utf-8")
        self.assertIn("if len(commands) == 1 and not dependencies", source)
        self.assertIn("command_modules[command] = module_name", source)
        self.assertIn("runtime bundle command collision", source)

    def test_runtime_bundle_exposes_commands_without_shadowing_bin(self) -> None:
        source = (ROOT / "scripts/ports.py").read_text(encoding="utf-8")
        self.assertNotIn('\'"/bin" = "bin"\'', source)
        self.assertIn("alias_arguments = aliases.get(command, {}).get", source)

    def test_command_aliases_reference_a_real_command(self) -> None:
        alias = self.ports["bison"].data["runtime"]["command_aliases"]["yacc"]
        self.assertEqual(alias, {"target": "bison", "args": ["-y"]})
        source = (ROOT / "scripts/ports.py").read_text(encoding="utf-8")
        self.assertIn("json.dumps(shlex.join(alias_arguments))", source)

    def test_network_packages_are_not_full(self) -> None:
        for name in ("curl", "wget"):
            self.assertEqual(self.ports[name].data["runtime"]["capability"], "http")
        for name in ("openssh-client", "rsync", "dnsutils", "netcat-openbsd", "openssl"):
            self.assertEqual(self.ports[name].data["runtime"]["capability"], "socket-preview")

    def test_curl_avoids_runtime_wakeup_descriptors(self) -> None:
        arguments = self.ports["curl"].data["build"]["configure_args"]
        self.assertIn("--disable-threaded-resolver", arguments)
        self.assertIn("--disable-socketpair", arguments)

    def test_stable_requires_every_acceptance_check(self) -> None:
        artifact = "a" * 64
        data = {
            "artifact_sha256": artifact,
            "checks": {
                name: {"passed": True, "artifact_sha256": artifact}
                for name in ACCEPTANCE_MODULE.CHECKS
            },
        }
        self.assertTrue(ACCEPTANCE_MODULE.is_stable(data))
        data["checks"]["chrome"] = {"passed": False}
        self.assertFalse(ACCEPTANCE_MODULE.is_stable(data))

    def test_stable_rejects_evidence_from_another_artifact(self) -> None:
        artifact = "a" * 64
        data = {
            "artifact_sha256": artifact,
            "checks": {
                name: {"passed": True, "artifact_sha256": artifact}
                for name in ACCEPTANCE_MODULE.CHECKS
            },
        }
        data["checks"]["chrome"]["artifact_sha256"] = "b" * 64
        self.assertFalse(ACCEPTANCE_MODULE.is_stable(data))

    def test_stage_rejects_native_or_missing_commands(self) -> None:
        port = self.ports["grep"]
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            binary = stage / "usr/local/bin/grep"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"native")
            with self.assertRaises(PORTS_MODULE.PortError):
                PORTS_MODULE.validate_stage(port, stage)

    def test_stage_rejects_non_executable_wasm_commands(self) -> None:
        port = self.ports["grep"]
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            binary = stage / "usr/local/bin/grep"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"\x00asm")
            binary.chmod(0o644)
            with self.assertRaises(PORTS_MODULE.PortError):
                PORTS_MODULE.validate_stage(port, stage)

    def test_every_user_visible_package_has_a_runtime_fixture(self) -> None:
        acceptance_script = (ROOT / "scripts/runtime-acceptance.sh").read_text(encoding="utf-8")
        for name, port in self.ports.items():
            if port.user_visible:
                self.assertIn(f"  {name})", acceptance_script)

    def test_runtime_acceptance_can_isolate_the_current_package(self) -> None:
        script = (ROOT / "scripts/runtime-acceptance.sh").read_text(encoding="utf-8")
        self.assertIn("EDGETERM_ACCEPTANCE_CURRENT_PACKAGE_ONLY", script)
        self.assertIn('pending.extend(port.data["package"].get("depends", []))', script)
        self.assertIn("write_packages_index(repository, repository", script)
        self.assertIn("file:/home/user/repository ./", script)

    def test_bash_runtime_fixture_avoids_nested_shell_escaping(self) -> None:
        script = (ROOT / "scripts/runtime-acceptance.sh").read_text(encoding="utf-8")
        self.assertIn('cat > "$SANDBOX/home/user/bash-loop.sh"', script)
        self.assertIn("/usr/local/bin/bash /home/user/bash-loop.sh", script)
        self.assertNotIn("printf BASH_%s", script)

    def test_cross_builds_do_not_regenerate_release_documentation(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["bc"])
        self.assertIn("export MAKEINFO=true", script)
        self.assertIn('make -j"${BUILD_JOBS:-4}" MAKEINFO=true', script)
        self.assertIn("make MAKEINFO=true DESTDIR=/build/stage install", script)
        self.assertIn("find \"$SOURCE_DIR\" -type f -name '*.info' -exec touch", script)

    def test_builds_use_the_central_target_and_sysroot_profile(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["grep"])
        self.assertIn('prepare-sysroot.sh "$WASIX_SYSROOT"', script)
        self.assertIn("--target=wasm32-wasip1", script)
        self.assertIn("PKG_CONFIG_SYSROOT_DIR", script)
        self.assertIn("PKG_CONFIG_LIBDIR", script)

    def test_cargo_build_outputs_stay_outside_the_upstream_source_tree(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["htmlq"])
        self.assertIn("export CARGO_TARGET_DIR=/build/cargo-target", script)
        self.assertIn('"$CARGO_TARGET_DIR"/wasm32-wasip1/release/htmlq.wasm', script)
        self.assertNotIn("install -m 755 target/", script)

    def test_source_subdirectory_keeps_integrity_scope_at_archive_root(self) -> None:
        port = self.ports["xdelta3"]
        PORTS_MODULE.validate_port(port)
        script = PORTS_MODULE.configure_script(port)
        self.assertIn('SOURCE_DIR="$SOURCE_ROOT/xdelta3"', script)
        self.assertIn('verify "$SOURCE_ROOT" /build/source-integrity.json', script)
        self.assertNotIn('verify "$SOURCE_DIR" /build/source-integrity.json', script)

    def test_autoreconf_uses_a_shadow_tree(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["xdelta3"])
        self.assertIn("AUTORECONF_SOURCE=/build/work/autoreconf-source", script)
        self.assertIn('cp -a "$SOURCE_DIR"/. "$AUTORECONF_SOURCE"/', script)
        self.assertIn('SOURCE_DIR="$AUTORECONF_SOURCE"', script)

    def test_non_executable_config_guess_runs_without_source_mutation(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["bash"])
        self.assertIn('if [ -x "$CONFIG_GUESS" ]', script)
        self.assertIn('BUILD_TRIPLET=$(sh "$CONFIG_GUESS")', script)
        self.assertNotIn('chmod +x "$CONFIG_GUESS"', script)

    def test_generated_sources_can_use_a_shadow_tree(self) -> None:
        port = self.ports["less"]
        PORTS_MODULE.validate_port(port)
        script = PORTS_MODULE.configure_script(port)
        self.assertIn("SHADOW_SOURCE=/build/work/source", script)
        self.assertIn('cp -a "$SOURCE_DIR"/. "$SHADOW_SOURCE"/', script)
        self.assertIn('SOURCE_DIR="$SHADOW_SOURCE"', script)
        self.assertIn('verify "$SOURCE_ROOT" /build/source-integrity.json', script)

    def test_autotools_builds_preserve_configure_generated_flags(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["rsync"])
        self.assertNotIn('CFLAGS="$EDGETERM_COMPILE_CFLAGS"', script)
        self.assertIn('make -j"${BUILD_JOBS:-4}" MAKEINFO=true', script)
        self.assertIn("ensure-build-profile.py", script)
        self.assertIn("--export=__stack_pointer", script)
        self.assertIn("--export=__data_end", script)

    def test_nonstandard_main_uses_the_posix_entry_adapter(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["make"])
        self.assertIn("-Dmain=edgeterm_main_with_env", script)
        self.assertIn("libedgeterm-main-env.a", script)

    def test_reproducibility_check_forces_two_root_builds(self) -> None:
        script = (ROOT / "scripts/build-acceptance.sh").read_text(encoding="utf-8")
        self.assertEqual(script.count("EDGETERM_FORCE_REBUILD=1"), 2)
        self.assertIn("mode=forced-root-rebuild-v1", script)
        ports_source = (ROOT / "scripts/ports.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("EDGETERM_FORCE_REBUILD", "0") == "1"', ports_source)

    def test_stack_checkpoint_detection_is_safe_with_pipefail(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["coreutils"])
        self.assertIn('inspection="${executable}.wat"', script)
        self.assertIn('grep -q \'"stack_checkpoint"\' "$inspection"', script)
        self.assertNotIn('wasm-dis "$executable" -o -', script)
        self.assertIn('chmod --reference="$executable" "$transformed"', script)

    def test_threaded_rust_wasix_abi_overlays_are_build_local(self) -> None:
        script = PORTS_MODULE.configure_script(self.ports["hyperfine"])
        self.assertIn("prepare-rust-libc-overlay.py", script)
        self.assertIn("prepare-rust-rand-os-overlay.py", script)
        self.assertIn(
            '--config /build/rust-compat/libc/cargo-config.toml',
            script,
        )
        self.assertIn("--extra-path /build/rust-compat/rand_os", script)
        self.assertIn("cargo build", script)
        self.assertIn("-Z build-std=std,panic_abort", script)
        self.assertIn("export RUSTC=/wasix-rust/bin/rustc", script)
        self.assertIn(
            "--target /toolchain/edgeterm-posix/config/threaded/wasm32-wasmer-wasi.json",
            script,
        )
        self.assertIn("-Z json-target-spec", script)
        self.assertIn("crt1-command.o", script)
        self.assertIn("-pthread", script)
        self.assertIn("rustc-posix-wrapper.py", script)
        self.assertIn('EDGETERM_RUST_WORKSPACE="$SOURCE_DIR"', script)
        self.assertNotIn('--cfg unix', script)
        self.assertNotIn("sed -i", script)

    def test_migrated_gnu_tools_require_pristine_sources(self) -> None:
        for name in (
            "bash",
            "bc",
            "bison",
            "brotli",
            "bzip2",
            "choose",
            "cmark",
            "coreutils",
            "cpio",
            "dash",
            "datamash",
            "diffutils",
            "dos2unix",
            "ed",
            "expat",
            "file",
            "findutils",
            "gawk",
            "grep",
            "gzip",
            "jq",
            "lz4",
            "lua",
            "m4",
            "make",
            "ncdu",
            "ncompress",
            "ncurses",
            "patch",
            "pcre2",
            "rsync",
            "sed",
            "sqlite3",
            "tar",
            "tree",
            "unzip",
            "xz-utils",
            "zstd",
        ):
            with self.subTest(package=name):
                port = self.ports[name]
                self.assertTrue(port.data["build"].get("pristine_source"))
                self.assertTrue(PORTS_MODULE.requires_pristine_source(port))

    def test_migrated_rust_tools_require_pristine_sources(self) -> None:
        for name in ("eza", "hyperfine"):
            with self.subTest(package=name):
                port = self.ports[name]
                self.assertTrue(port.data["build"].get("pristine_source"))
                self.assertTrue(PORTS_MODULE.requires_pristine_source(port))
                self.assertEqual(port.data["build"].get("pre", []), [])
                self.assertEqual(list(port.path.glob("*.patch")), [])

    def test_quickjs_uses_pristine_upstream_sources(self) -> None:
        port = self.ports["quickjs"]
        self.assertTrue(port.data["build"].get("pristine_source"))
        self.assertEqual(port.data["build"].get("pre", []), [])
        self.assertFalse((port.path / "prepare.py").exists())

    def test_file_uses_the_compatibility_layer_without_source_rewrites(self) -> None:
        pre = self.ports["file"].data["build"]["pre"]
        self.assertFalse((ROOT / "ports/file/patch_file.py").exists())
        self.assertFalse(any("patch_file.py" in command for command in pre))
        self.assertTrue(any("CPPFLAGS=" in command and "LIBS=" in command for command in pre))

    def test_python_repository_index_contains_all_current_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            pool = repository / "current"
            pool.mkdir()
            package = next((ROOT / "dist").glob("*.deb"))
            target = pool / package.name
            target.write_bytes(package.read_bytes())
            index = repository / "Packages"
            REPOSITORY_MODULE.write_packages_index(repository, pool, index)
            contents = index.read_text(encoding="utf-8")
            self.assertIn(f"Filename: current/{package.name}", contents)
            self.assertIn(f"Size: {package.stat().st_size}", contents)
            self.assertIn(f"SHA256: {hashlib.sha256(package.read_bytes()).hexdigest()}", contents)

    def test_candidate_repository_indexes_the_current_catalog(self) -> None:
        index = ROOT / "repository/dists/candidate/main/binary-wasm32-wasix/Packages"
        compressed = index.with_suffix(".xz")
        if not index.exists() or not compressed.exists():
            self.skipTest("Candidate repository has not been generated")
        contents = index.read_bytes()
        self.assertEqual(contents.count(b"Package: "), sum(port.user_visible for port in self.ports.values()))
        self.assertEqual(lzma.open(compressed, "rb").read(), contents)

    def test_source_audit_covers_every_user_visible_package(self) -> None:
        report = SOURCE_AUDIT_MODULE.build_report()
        self.assertEqual(len(report), sum(port.user_visible for port in self.ports.values()))
        self.assertEqual(
            {item["package"] for item in report},
            {name for name, port in self.ports.items() if port.user_visible},
        )

    def test_locked_pristine_ports_have_no_checked_in_patch_files(self) -> None:
        for name, port in self.ports.items():
            if not port.data["build"].get("pristine_source"):
                continue
            self.assertEqual(list(port.path.glob("*.patch")), [], name)


if __name__ == "__main__":
    unittest.main()
