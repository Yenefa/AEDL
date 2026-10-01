"""Bounded scope checks and opt-in real native episode, never network in tests."""
import copy
import os
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.nativeports import DOMAIN, INITIAL_SUBJECT, NativeEpisodePolicy
from aedl_sandbox.protocol import PolicyRequest, Outcome


class NativeScopeTests(unittest.TestCase):
    def evaluate(self, subject, action="execute_candidate", domain=DOMAIN):
        return NativeEpisodePolicy().evaluate(PolicyRequest("r", domain, "a", action,
                                                            Path("."), subject))

    def test_initial_fault_and_scoped_repair_allowed(self):
        self.assertEqual(self.evaluate(INITIAL_SUBJECT).outcome, Outcome.ALLOW)
        subject = copy.deepcopy(INITIAL_SUBJECT)
        subject["design_subject"]["function"] = "GND"
        subject.pop("output_kind")
        self.assertEqual(self.evaluate(subject).outcome, Outcome.ALLOW)

    def test_foreign_pin_domain_kind_and_authority_are_refused(self):
        for field, value in (("pin", "U1.2"), ("function", "+3V3"),
                             ("approval_status", "APPROVED"), ("authority", "ALLOW")):
            with self.subTest(field=field):
                subject = copy.deepcopy(INITIAL_SUBJECT)
                subject["design_subject"][field] = value
                self.assertEqual(self.evaluate(subject).outcome, Outcome.BLOCKED)
        subject = copy.deepcopy(INITIAL_SUBJECT)
        subject["output_kind"] = "kicad_pcb"
        self.assertEqual(self.evaluate(subject).outcome, Outcome.BLOCKED)
        self.assertEqual(self.evaluate(INITIAL_SUBJECT, domain="EDD-001").outcome, Outcome.BLOCKED)
        self.assertEqual(self.evaluate(INITIAL_SUBJECT, action="promote").outcome, Outcome.BLOCKED)

    @unittest.skipUnless(os.environ.get("AEDL_EPISODE_NATIVE") == "1", "native tools require explicit opt-in")
    def test_native_control_repairs_actual_schematic_and_kills_frozen_initial_verifier(self):
        from tools.run_arh_episode import run_episode
        from aedl_sandbox.arh.model_adapter import FakeModelAdapter, ModelResponse, ModelUsage
        import json
        proposal = {"diagnosis": "SHT30_ADDRESS: U2.2 floating",
            "design_action": "DESIGN_ASSIGN_PIN", "design_subject": {
                "pin": "U2.2", "function": "GND", "approval_status": "NOT_REQUIRED"},
            "evidence_ids": ["SHT30_ADDRESS"], "locator": {"pin": "U2.2"}}
        with tempfile.TemporaryDirectory() as temp:
            summary = run_episode(Path(temp) / "episode", os.environ["AEDL_AKCLI_PYTHON"],
                os.environ["AEDL_KICAD_CLI"], FakeModelAdapter([
                    ModelResponse(json.dumps(proposal), ModelUsage(), "offline-control")]), real_model=False)
            self.assertEqual(summary["result"], "CONTROL_RUN")
            self.assertEqual([o["status"] for o in summary["observations"]], ["FAIL", "PASS"])
            self.assertEqual(summary["transactions"][0]["status"], "COMMITTED")
            self.assertNotEqual(summary["observations"][0]["source_sha256"],
                                summary["observations"][1]["source_sha256"])
            self.assertEqual(summary["model_budget"]["calls"], 1)
            self.assertFalse(summary["real_model"])
            self.assertFalse(summary["manufacturing_release"])


class NativeInspectionTests(unittest.TestCase):
    """Isolation and drift attacks against registered native observations."""
    def setUp(self):
        import json
        from types import SimpleNamespace
        from aedl_sandbox.nativeports import NativeEpisodePorts, sha
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = self.base / 'repo'
        self.root = self.base / 'candidate' / 'cand-1'
        source = self.root / 'design/fault.kicad_sch'
        source.parent.mkdir(parents=True)
        source.write_text('frozen candidate', encoding='utf-8')
        firmware = self.root / 'design/src/firmware/include/sht30.h'
        firmware.parent.mkdir(parents=True)
        firmware.write_text('static constexpr uint8_t DEFAULT_ADDR = 0x44;\n', encoding='utf-8')
        canonical = self.repo / 'src/firmware/include/sht30.h'
        canonical.parent.mkdir(parents=True)
        canonical.write_bytes(firmware.read_bytes())
        contract = self.repo / 'gates/contracts/address.json'
        contract.parent.mkdir(parents=True)
        rule = {'id': 'SHT30_ADDRESS', 'checks': {'netlist': {'pins': {'U2.2': {'net': 'GND'}}}}}
        contract.write_text(json.dumps(rule), encoding='utf-8')
        report = self.base / 'reports'
        report.mkdir()
        netlist = report / 'after.net.xml'
        netlist.write_text('<export><components><comp ref="U2"><value>SHT30</value></comp>'
            '</components><nets><net name="unconnected-U2-2"><node ref="U2" pin="2"/>'
            '</net></nets></export>', encoding='utf-8')
        self.ports = NativeEpisodePorts.__new__(NativeEpisodePorts)
        self.ports.repo, self.ports.report = self.repo, report
        self.ports.firmware_path, self.ports.firmware_sha = canonical, sha(canonical)
        self.ports.contract_path, self.ports.contract_sha = contract, sha(contract)
        self.ports.rule = rule
        self.ports.identities = {str(self.root): ('r', 'cand-1')}
        self.ports.inspection_candidate = self.root
        self.ports.inspection_paths = {'cand-1': netlist}
        self.ports.observations = [{'candidate_id': 'cand-1', 'source_sha256': sha(source),
                                   'netlist_sha256': sha(netlist),
                                   'observed': {'net': None, 'no_connect': False}}]
        self.ctx = SimpleNamespace(verification_ref={'run_id': 'r', 'candidate_id': 'cand-1'})

    def test_projection_and_full_source_hashes_have_distinct_bindings(self):
        import hashlib
        from aedl_sandbox.nativeports import sha
        resources = self.ports.investigation_resources()
        for key in resources:
            result = resources[key](self.ctx)
            self.assertEqual(hashlib.sha256(result['content'].encode()).hexdigest(), result['sha256'])
            self.assertEqual(len(result['source_sha256']), 64)
        result = resources['current_netlist'](self.ctx)
        self.assertEqual(result['source_sha256'], sha(self.ports.inspection_paths['cand-1']))
        self.assertNotEqual(result['sha256'], result['source_sha256'])
        self.assertNotIn('GND', result['content'])

    def test_foreign_run_or_candidate_cannot_read_any_source(self):
        from types import SimpleNamespace
        for ref in ({'run_id': 'foreign', 'candidate_id': 'cand-1'},
                    {'run_id': 'r', 'candidate_id': 'foreign'}, {}):
            for provider in self.ports.investigation_resources().values():
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    provider(SimpleNamespace(verification_ref=ref))

    def test_source_drift_invalidates_all_projections(self):
        (self.root / 'design/fault.kicad_sch').write_text('changed')
        for provider in self.ports.investigation_resources().values():
            with self.assertRaisesRegex(ValueError, 'source drift'):
                provider(self.ctx)

    def test_netlist_contract_and_coordinated_firmware_drift_are_refused(self):
        resources = self.ports.investigation_resources()
        self.ports.inspection_paths['cand-1'].write_text('changed')
        with self.assertRaisesRegex(ValueError, 'netlist drift'):
            resources['current_netlist'](self.ctx)
        self.ports.contract_path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'contract drift'):
            resources['address_contract'](self.ctx)
        self.ports.firmware_path.write_text('new address = 0x45;')
        (self.root / 'design/src/firmware/include/sht30.h').write_bytes(self.ports.firmware_path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'firmware drift'):
            resources['firmware_address'](self.ctx)

    def test_aliased_source_is_refused_even_when_bytes_match(self):
        target = self.root / 'design/src/firmware/include/sht30.h'
        target.unlink()
        try:
            os.link(self.ports.firmware_path, target)
        except OSError as exc:
            self.skipTest('hard links unavailable: ' + type(exc).__name__)
        with self.assertRaises(ValueError):
            self.ports.investigation_resources()['firmware_address'](self.ctx)

    def test_invalid_runner_config_has_no_filesystem_side_effect(self):
        from tools.run_arh_episode import run_episode
        from aedl_sandbox.arh.model_adapter import FakeModelAdapter
        destination = self.base / 'must-not-exist'
        for args in ({'max_calls': 0}, {'max_repairs': -1},
                     {'adaptive': True, 'specialist_models': {'a': object()}},
                     {'adaptive': True, 'specialist_models': {str(i): object() for i in range(3)}}):
            with self.subTest(args=args), self.assertRaises((ValueError, TypeError)):
                run_episode(destination, 'missing', 'missing', FakeModelAdapter([]), real_model=False, **args)
            self.assertFalse(destination.exists())

    @unittest.skipUnless(os.environ.get('AEDL_EPISODE_NATIVE') == '1', 'native tools require explicit opt-in')
    def test_native_stall_uses_one_source_cited_specialist_and_actual_verdicts(self):
        import hashlib
        import json
        from tools.run_arh_episode import run_episode, REPO
        from aedl_sandbox.arh.model_adapter import FakeModelAdapter, ModelResponse, ModelUsage
        def response(data):
            return ModelResponse(json.dumps(data), ModelUsage(input_tokens=2, output_tokens=2), 'offline-control')
        def proposal(function):
            return {'diagnosis': 'SHT30_ADDRESS: inspected address mismatch',
                'design_action': 'DESIGN_ASSIGN_PIN', 'design_subject': {'pin': 'U2.2',
                    'function': function, 'approval_status': 'NOT_REQUIRED'}, 'evidence_ids': ['SHT30_ADDRESS']}
        inspect = {'type': 'inspect', 'resource_ids': ['current_netlist', 'address_contract']}
        rule = next(r for r in json.loads((REPO / 'gates/contracts/m2_schematic_contract_v1.json').read_text())['rules']
                    if r['id'] == 'SHT30_ADDRESS')
        contract_hash = hashlib.sha256(json.dumps(rule, ensure_ascii=False).encode()).hexdigest()
        lead = FakeModelAdapter([response(inspect), response(proposal('FLOATING')),
                                 response(inspect), response(proposal('GND'))])
        expert = FakeModelAdapter([response({'type': 'ready'}), response({'advice': 'The measured ADDR is floating; '
            'the independent address contract requires GND.', 'citations': [{'resource_id': 'address_contract',
                'sha256': contract_hash, 'evidence_ids': ['SHT30_ADDRESS']}]})])
        summary = run_episode(self.base / 'episode', os.environ['AEDL_AKCLI_PYTHON'],
            os.environ['AEDL_KICAD_CLI'], lead, real_model=False, adaptive=True,
            specialist_models={'address-specialist': expert}, max_repairs=2, max_calls=8)
        self.assertEqual(summary['result'], 'CONTROL_RUN')
        self.assertEqual([o['status'] for o in summary['observations']], ['FAIL', 'FAIL', 'PASS'])
        self.assertEqual(summary['model_budget']['calls'], 6)
        self.assertEqual(summary['repair_count'], 2)
        self.assertEqual(summary['agent_roster'], ['lead', 'address-specialist'])
        self.assertEqual(summary['role_calls']['expert:address-specialist'], 1)
        self.assertEqual(len(summary['inspections']), 4)
        self.assertEqual(len([e for e in summary['specialist_events'] if 'citations' in e]), 1)
        self.assertFalse(summary['manufacturing_release'])
