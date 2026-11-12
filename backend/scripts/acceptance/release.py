"""Run actual release checks and map their JUnit cases to docs/11 T01-T18."""

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

BACKEND = Path(__file__).resolve().parents[2]
PROJECT = BACKEND.parent

MATRIX = {
    "T01": ["test_three_business_messages_and_no_invented_interview_plan", "test_full_mock_flow"],
    "T02": ["test_three_business_messages_and_no_invented_interview_plan"],
    "T03": ["test_mock_durable_ack_pipeline_dedup_and_minimal_notice"],
    "T04": ["test_name_conflict_confirm_select_replay_and_only_once"],
    "T05": ["test_one_candidate_two_positions_and_no_name_merge"],
    "T06": ["test_terminal_reversal_persists_confirmation_without_changing_application"],
    "T07": ["test_ambiguous_schedule_can_be_corrected_and_executed"],
    "T08": ["test_offer_decline_and_waiting_denominator"],
    "T09": ["test_model_failure_reaches_review_without_business_write[T09]"],
    "T10": ["test_model_failure_reaches_review_without_business_write[T10-model]", "test_model_failure_reaches_review_without_business_write[T10-prompt]"],
    "T11": ["test_remote_failure_keeps_business_and_exponential_dead_letter", "test_admin_retry_rbac_revision_idempotency_and_recovery"],
    "T12": ["test_remote_success_before_local_ack_is_idempotently_recovered"],
    "T13": ["test_optimistic_conflict_idempotent_replay_and_if_match_required"],
    "T14": ["test_rbac_read_scopes"],
    "T15": ["test_T15_dashboard_matches_independent_sql_and_calendar"],
    "T16": ["T16 空库候选人列表显示明确空态，不生成示例行"],
    "T17": ["test_full_mock_flow", "test_missing_credentials_and_mock_mode_never_call_network"],
    "T18": ["test_unsafe_modes_refuse_startup", "test_production_configuration_fail_closed", "test_tencent_config_never_silently_falls_back_or_claims_real_success"],
}


def junit_cases(path):
    if not path.exists():
        return []
    return [{"name": row.get("name", ""), "suite": row.get("classname", ""),
             "status": "failed" if row.find("failure") is not None or row.find("error") is not None else "skipped" if row.find("skipped") is not None else "passed"}
            for row in ElementTree.parse(path).iter("testcase")]


def matrix_results(cases):
    results = []
    for ident, requirements in MATRIX.items():
        evidence, missing = [], []
        for name in requirements:
            found = [case for case in cases if name in case["name"]]
            evidence.extend(found)
            if not found:
                missing.append(name)
        status = "not_run" if missing else "failed" if any(case["status"] == "failed" for case in evidence) else "skipped" if any(case["status"] == "skipped" for case in evidence) else "passed"
        results.append({"id": ident, "status": status, "evidence": evidence, "missing": missing})
    return results


def main():
    node = shutil.which("node")
    npm_cli = os.environ.get("npm_execpath")
    if not npm_cli:
        executable = shutil.which("npm")
        if executable:
            resolved = Path(executable).resolve()
            npm_cli = str(resolved if resolved.name == "npm-cli.js" else resolved.parent / "node_modules/npm/bin/npm-cli.js")
    if not node or not npm_cli or not Path(npm_cli).is_file():
        raise RuntimeError("Use npm run acceptance with Node.js and npm installed")
    root = PROJECT / ".tools" / ("s7-acceptance-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True)
    api_xml, web_xml = root / "backend.xml", root / "frontend.xml"
    npm = [node, npm_cli]
    steps = [
        ("contracts", npm + ["run", "contracts:check"], PROJECT),
        ("lint", npm + ["run", "lint"], PROJECT),
        ("types", npm + ["run", "typecheck"], PROJECT),
        ("backend", [sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(api_xml)], BACKEND),
        ("frontend", npm + ["run", "test", "--workspace", "frontend", "--", "--reporter=default", "--reporter=junit", "--outputFile.junit=" + str(web_xml)], PROJECT),
        ("build", npm + ["run", "build"], PROJECT),
        ("isolated_mock_http", [sys.executable, "-m", "scripts.acceptance.demo", "--verify"], BACKEND),
        ("synthetic_sso_http", [sys.executable, "-m", "scripts.smoke.security"], BACKEND),
    ]
    checks = []
    for name, command, cwd in steps:
        print("\nRELEASE CHECK: " + name, flush=True)
        started = time.monotonic()
        result = subprocess.run(command, cwd=cwd, check=False)
        checks.append({"name": name, "status": "passed" if result.returncode == 0 else "failed", "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 2)})
    cases = junit_cases(api_xml) + junit_cases(web_xml)
    matrix = matrix_results(cases)
    passed = all(row["status"] == "passed" for row in checks + matrix)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "mode": "mock_and_synthetic_transports", "status": "passed" if passed else "failed",
        "checks": checks, "tests": {state: sum(row["status"] == state for row in cases) for state in ("passed", "failed", "skipped")},
        "matrix": matrix, "external_acceptance": {name: "not_executed_requires_authorization" for name in ("deepseek_live_and_accuracy", "tencent_mcp_write", "wecom_tenant", "enterprise_sso_tls")},
        "docker_runtime": "not_executed_by_this_command"}
    (root / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in matrix:
        print(f"{row['id']}: {row['status']}")
    print("Release evidence: " + str(root), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
