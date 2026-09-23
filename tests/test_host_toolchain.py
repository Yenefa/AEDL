"""PR1-C5-PRE: the host toolchain binding and its two derived slices.

These tests establish the integration primitive only.  They read no file, run no
tool and touch no candidate: every property under test is a pure function of the
binding.  The strongest assertions here are the cross-layer ones -- a derived
slice is only a slice if the *real* C3/C4 validator accepts it unchanged, and the
C4 installed-distribution digest is an observation that must not be cast from a
portable declaration.
"""

import copy
import os
import unittest
from unittest import mock

from gates import repair_verification
from tools import akcli_adapter
from tools import host_toolchain


def abs_path(*parts):
    return os.path.abspath(os.path.join(os.sep, *parts))


def base_binding():
    return {
        "version": 1,
        "manifest": {
            "version": 1,
            "akcli": {
                "version": "0.21.0",
                "sdist_sha256": "1" * 64,
                "package_files_sha256": {"version": 1, "files": [
                    {"path": "akcli/__init__.py", "sha256": "2" * 64,
                     "size_bytes": 10, "role": "READONLY_DEPENDENCY"}]},
            },
            "python": {"version": "3.11.15", "executable_sha256": "3" * 64},
            "kicad": {"version": "10.0.5", "executable_sha256": "4" * 64},
            "libraries": {"version": 1, "files": [
                {"path": "libs/Device.kicad_sym", "sha256": "5" * 64,
                 "size_bytes": 20, "role": "READONLY_DEPENDENCY"}]},
            "configs": {"version": 1, "files": []},
            "execution": {"worker_timeout_seconds": 60, "kicad_timeout_seconds": 60,
                          "argv_profile": "PR1_V1"},
        },
        "resolution": {
            "executables": {"akcli": abs_path("opt", "akcli", "akcli.exe"),
                            "python": abs_path("opt", "py311", "python.exe"),
                            "kicad": abs_path("opt", "kicad", "kicad-cli.exe")},
            "files": {"libraries": {"libs/Device.kicad_sym":
                                    abs_path("opt", "libs", "Device.kicad_sym")},
                      "configs": {}},
            "environment": {"kicad": {"SYSTEMROOT": abs_path("WINDOWS")},
                            "akcli": {}},
            "launcher_argv": [abs_path("opt", "akcli", "akcli.exe")],
            "installed_akcli": {"package": "akcli-kicad", "version": "0.21.0",
                                "files": 245, "sha256": "6" * 64},
        },
    }


SYMBOL = "7" * 64


class DerivationTests(unittest.TestCase):
    def test_the_real_validators_accept_both_derived_slices(self):
        binding = base_binding()
        kicad = host_toolchain.derive_kicad_slice(binding)
        # the C3 layer's own validator, not a parallel one
        self.assertIs(repair_verification.toolchain_manifest(kicad), kicad)
        akcli = host_toolchain.derive_akcli_slice(binding, SYMBOL)
        self.assertIs(akcli_adapter.toolchain_manifest(akcli), akcli)

    def test_the_slice_digests_match_what_the_two_layers_compute(self):
        binding = base_binding()
        kicad = host_toolchain.derive_kicad_slice(binding)
        akcli = host_toolchain.derive_akcli_slice(binding, SYMBOL)
        self.assertEqual(host_toolchain.toolchain_slice_sha256(kicad),
                         repair_verification.canonical_sha256("toolchain", kicad))
        self.assertEqual(host_toolchain.toolchain_slice_sha256(akcli),
                         akcli_adapter._toolchain_digest(akcli))

    def test_the_kicad_slice_never_carries_a_launcher(self):
        binding = base_binding()
        self.assertTrue(binding["resolution"]["launcher_argv"])
        kicad = host_toolchain.derive_kicad_slice(binding)
        self.assertEqual(kicad["launcher_argv"], [])
        self.assertEqual(kicad["kicad_cli"], binding["resolution"]["executables"]["kicad"])
        akcli = host_toolchain.derive_akcli_slice(binding, SYMBOL)
        self.assertEqual(akcli["launcher_argv"], binding["resolution"]["launcher_argv"])

    def test_portable_library_paths_are_resolved_to_host_paths(self):
        binding = base_binding()
        kicad = host_toolchain.derive_kicad_slice(binding)
        rows = kicad["libraries"]["files"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"],
                         binding["resolution"]["files"]["libraries"]["libs/Device.kicad_sym"])
        self.assertEqual(rows[0]["role"], "READONLY_DEPENDENCY")
        self.assertEqual(rows[0]["sha256"], "5" * 64)
        self.assertEqual(rows[0]["size_bytes"], 20)

    def test_empty_libraries_and_configs_are_allowed(self):
        binding = base_binding()
        binding["manifest"]["libraries"] = {"version": 1, "files": []}
        binding["resolution"]["files"]["libraries"] = {}
        kicad = host_toolchain.derive_kicad_slice(binding)
        self.assertEqual(kicad["libraries"]["files"], [])
        self.assertEqual(kicad["configs"]["files"], [])

    def test_the_installed_digest_is_an_observation_not_a_declaration(self):
        """The C4 artifact digest must not be cast from a portable declaration.

        manifest.akcli.sdist_sha256 and manifest.akcli.package_files_sha256 are
        declarations in another domain; C4 verifies the installed distribution.
        This contract defines no derivation between them, so the derived slice has
        to carry the observed value and nothing else.
        """
        binding = base_binding()
        binding["manifest"]["akcli"]["sdist_sha256"] = "a" * 64
        binding["manifest"]["akcli"]["package_files_sha256"]["files"][0]["sha256"] = "b" * 64
        akcli = host_toolchain.derive_akcli_slice(binding, SYMBOL)
        self.assertEqual(akcli["akcli_artifact_sha256"], "6" * 64)
        self.assertNotEqual(akcli["akcli_artifact_sha256"],
                            binding["manifest"]["akcli"]["sdist_sha256"])
        self.assertNotEqual(akcli["akcli_artifact_sha256"], "b" * 64)
        # the upstream commit is the frozen constant, not a second host field
        self.assertEqual(akcli["akcli_upstream_commit"],
                         akcli_adapter.AKCLI_UPSTREAM_COMMIT)

    def test_normalization_makes_path_spelling_irrelevant(self):
        direct = base_binding()
        detour = copy.deepcopy(direct)
        detour["resolution"]["executables"]["kicad"] = os.path.join(
            abs_path("opt", "kicad"), "..", "kicad", "kicad-cli.exe")
        self.assertEqual(host_toolchain.host_binding_sha256(direct),
                         host_toolchain.host_binding_sha256(detour))

    def test_the_binding_digest_is_deterministic_across_key_order(self):
        forward = base_binding()
        reversed_binding = {}
        for key in reversed(list(forward)):
            value = forward[key]
            if isinstance(value, dict):
                value = {inner: value[inner] for inner in reversed(list(value))}
            reversed_binding[key] = value
        self.assertEqual(host_toolchain.host_binding_sha256(forward),
                         host_toolchain.host_binding_sha256(reversed_binding))


class SameHostToolchainTests(unittest.TestCase):
    def proof(self, binding, symbol=SYMBOL):
        c3 = host_toolchain.toolchain_slice_sha256(
            host_toolchain.derive_kicad_slice(binding))
        c4 = host_toolchain.toolchain_slice_sha256(
            host_toolchain.derive_akcli_slice(binding, symbol))
        return c3, c4

    def test_the_proof_is_common_ancestry_not_leaf_equality(self):
        binding = base_binding()
        c3, c4 = self.proof(binding)
        self.assertNotEqual(c3, c4, "the two slices must not share a digest")
        result = host_toolchain.same_host_toolchain(c3, c4, binding, SYMBOL)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        self.assertEqual(result["host_binding_sha256"],
                         host_toolchain.host_binding_sha256(binding))
        self.assertEqual(result["expected_c3_sha256"], c3)
        self.assertEqual(result["expected_c4_sha256"], c4)
        self.assertNotEqual(result["expected_c3_sha256"], result["expected_c4_sha256"])

    def test_a_receipt_from_another_host_binding_is_refused(self):
        binding = base_binding()
        c3, c4 = self.proof(binding)
        moved = copy.deepcopy(binding)
        moved["resolution"]["executables"]["kicad"] = abs_path("elsewhere", "kicad-cli.exe")
        result = host_toolchain.same_host_toolchain(c3, c4, moved, SYMBOL)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual([r["code"] for r in result["reasons"]], ["REPAIR_INPUT_DRIFT"])
        self.assertIn("KiCad slice", result["reasons"][0]["detail"])

    def test_a_swapped_candidate_symbol_digest_is_refused(self):
        binding = base_binding()
        c3, c4 = self.proof(binding, symbol="8" * 64)
        result = host_toolchain.same_host_toolchain(c3, c4, binding, "9" * 64)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("akcli slice", result["reasons"][0]["detail"])

    def test_the_symbol_digest_is_not_part_of_the_host_identity(self):
        binding = base_binding()
        first = host_toolchain.same_host_toolchain(*self.proof(binding, "8" * 64),
                                                   binding, "8" * 64)
        second = host_toolchain.same_host_toolchain(*self.proof(binding, "9" * 64),
                                                    binding, "9" * 64)
        self.assertEqual(first["status"], "PASS", first["reasons"])
        self.assertEqual(second["status"], "PASS", second["reasons"])
        self.assertEqual(first["host_binding_sha256"], second["host_binding_sha256"])
        self.assertNotEqual(first["expected_c4_sha256"], second["expected_c4_sha256"])

    def test_a_binding_that_smuggles_a_symbol_digest_is_refused(self):
        binding = base_binding()
        binding["resolution"]["symbol_digest"] = SYMBOL
        result = host_toolchain.same_host_toolchain("0" * 64, "0" * 64, binding, SYMBOL)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("unknown fields", result["reasons"][0]["detail"])

    def test_a_malformed_receipt_hash_is_refused(self):
        binding = base_binding()
        c3, c4 = self.proof(binding)
        for bad in ("not-a-digest", "A" * 64, "0" * 63):
            with self.subTest(bad=bad):
                result = host_toolchain.same_host_toolchain(bad, c4, binding, SYMBOL)
                self.assertEqual(result["status"], "BLOCKED")


class FailClosedTests(unittest.TestCase):
    def refuse(self, mutate, fragment):
        binding = base_binding()
        mutate(binding)
        with self.assertRaises(host_toolchain.HostBindingError) as caught:
            host_toolchain.validate_host_binding(binding)
        self.assertIn(fragment, str(caught.exception))

    def test_unknown_or_missing_fields_are_refused_at_every_level(self):
        self.refuse(lambda b: b.update(extra=1), "host toolchain binding")
        self.refuse(lambda b: b["manifest"].update(extra=1), "portable manifest")
        self.refuse(lambda b: b["manifest"]["akcli"].update(extra=1), "akcli declaration")
        self.refuse(lambda b: b["resolution"].update(extra=1), "host resolution")
        self.refuse(lambda b: b["resolution"]["executables"].update(extra=abs_path("x")),
                    "executable map")
        self.refuse(lambda b: b["resolution"]["environment"].update(extra={}),
                    "resolution environment")
        self.refuse(lambda b: b["resolution"]["installed_akcli"].update(extra=1),
                    "installed akcli observation")

    def test_pinned_versions_and_timeouts_are_enforced(self):
        self.refuse(lambda b: b["manifest"]["kicad"].update(version="10.0.6"), "KiCad 10.0.5")
        self.refuse(lambda b: b["manifest"]["akcli"].update(version="0.22.0"), "akcli 0.21.0")
        self.refuse(lambda b: b["manifest"]["execution"].update(kicad_timeout_seconds=61),
                    "frozen maximum")
        self.refuse(lambda b: b["manifest"]["execution"].update(worker_timeout_seconds=0),
                    "worker timeout")
        self.refuse(lambda b: b["manifest"]["execution"].update(argv_profile="PR2_V1"),
                    "frozen argv profile")
        self.refuse(lambda b: b["resolution"]["installed_akcli"].update(version="0.20.0"),
                    "disagree")

    def test_host_paths_must_be_absolute_and_portable_paths_must_not_be(self):
        self.refuse(lambda b: b["resolution"]["executables"].update(kicad="kicad-cli.exe"),
                    "absolute host path")
        self.refuse(lambda b: b["resolution"]["launcher_argv"].append("akcli"),
                    "launcher_argv")
        self.refuse(lambda b: b["resolution"]["files"]["libraries"].update(
            {"libs/Device.kicad_sym": "libs/Device.kicad_sym"}), "absolute host path")
        self.refuse(lambda b: b["manifest"]["libraries"]["files"][0].update(
            path=abs_path("opt", "Device.kicad_sym")), "candidate-relative")

    def test_the_resolution_must_map_exactly_the_declared_logical_paths(self):
        self.refuse(lambda b: b["resolution"]["files"]["libraries"].clear(), "exactly")
        self.refuse(lambda b: b["resolution"]["files"]["libraries"].update(
            {"libs/Other.kicad_sym": abs_path("opt", "Other.kicad_sym")}), "exactly")

    def test_file_entries_are_closed_and_readonly(self):
        self.refuse(lambda b: b["manifest"]["libraries"]["files"][0].update(
            role="TARGET"), "READONLY_DEPENDENCY")
        self.refuse(lambda b: b["manifest"]["libraries"]["files"][0].update(
            sha256="nope"), "library digest")
        self.refuse(lambda b: b["manifest"]["libraries"]["files"][0].update(
            size_bytes=-1), "library size")
        self.refuse(lambda b: b["manifest"]["libraries"]["files"].append(
            dict(b["manifest"]["libraries"]["files"][0])), "case-colliding")

    def test_malformed_digests_are_refused(self):
        self.refuse(lambda b: b["manifest"]["kicad"].update(executable_sha256="z" * 64),
                    "kicad executable digest")
        self.refuse(lambda b: b["manifest"]["akcli"].update(sdist_sha256="1" * 63),
                    "akcli sdist digest")
        self.refuse(lambda b: b["resolution"]["installed_akcli"].update(sha256="6" * 64 + "0"),
                    "installed akcli digest")

    def test_a_derivation_that_the_layer_would_refuse_is_a_binding_error(self):
        """The slice validator is the contract: if it rejects, so does the binding."""
        binding = base_binding()
        with mock.patch.object(host_toolchain, "_kicad_validator",
                               side_effect=ValueError("layer refuses")):
            with self.assertRaises(host_toolchain.HostBindingError) as caught:
                host_toolchain.derive_kicad_slice(binding)
        self.assertIn("not accepted by its layer", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
