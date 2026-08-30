/* Headless closed-loop test of the MOCK path.
 *
 * Runs the same modules the page loads (api-client, contract-builder,
 * canonical-json, mock-data) through propose -> answer -> finalize -> validate,
 * with no DOM and no network. It is not a substitute for opening index.html,
 * but it catches contract-assembly and hashing regressions on every run.
 *
 * Run:  node web/smoke-test.js
 *
 * It writes the generated contract to web/_smoke_out/requirements_contract.json
 * so the authoritative Python gate can be pointed at it. That cross-check is
 * the real verification; see web/README.md.
 */
"use strict";

var fs = require("fs");
var path = require("path");

var api = require("./api-client.js");
var builder = require("./contract-builder.js");

var OUT_DIR = path.join(__dirname, "_smoke_out");

function assert(condition, message) {
  if (!condition) {
    console.error("FAIL: " + message);
    process.exitCode = 1;
  } else {
    console.log("  ok  " + message);
  }
}

function run() {
  var client = new api.ApiClient("mock", "http://127.0.0.1:8787");

  return client
    .propose("ESP32-C3 + SHT30 温湿度载板，USB-C 供电，BLE 上报")
    .then(function (proposal) {
      console.log("[1] POST /api/propose");
      assert(proposal.questions.length === 3, "mock 返回 3 个问题");
      assert(
        proposal.questions.every(function (q) {
          return q.answer === null;
        }),
        "建议层返回的 answer 恒为 null（答案只来自人类）",
      );
      assert(
        proposal.questions.filter(function (q) {
          return q.kind === "blocking";
        }).length === 2,
        "其中 2 个是 blocking",
      );
      assert(proposal.assumptions.length === 1, "mock 返回 1 条假设");

      console.log("[2] 人工作答 + 假设确认");
      // Contract semantics #2: an explicit answer is mandatory, and
      // "unknown" / "No preference" are legitimate explicit answers.
      proposal.questions[0].answer = "USB-C 5V";
      proposal.questions[1].answer = "No preference";
      proposal.questions[2].answer = "unknown";
      proposal.assumptions[0].decision = "confirmed";

      console.log("[3] POST /api/finalize");
      var draft = builder.buildDraft({
        boardId: "smoke-test-board",
        author: "human+ai",
        userGoal: "ESP32-C3 + SHT30 温湿度载板，USB-C 供电，BLE 上报",
        intentPath: "src/hardware/m2-board/intent_v1.json",
        statements: [
          { id: "S1", text: "ESP32-C3 + SHT30 温湿度载板", type: "other" },
        ],
        requirements: [],
        questions: proposal.questions,
        assumptions: proposal.assumptions,
        forbidden: ["禁止在未询问用户的情况下增加 Wi-Fi 模块"],
      });

      assert(
        Object.keys(draft).indexOf("contract_sha256") === -1,
        "draft 不含 contract_sha256（自哈希由 /api/finalize 写入）",
      );
      assert(
        draft.open_questions.every(function (q) {
          return (
            Object.keys(q).sort().join(",") ===
            "answer,id,kind,question,source_ids"
          );
        }),
        "open_questions 恰好含 id/question/answer/kind/source_ids",
      );
      assert(
        draft.assumptions.every(function (a) {
          return (
            Object.keys(a).sort().join(",") === "id,source_ids,status,text"
          );
        }),
        "assumptions 恰好含 id/text/source_ids/status",
      );

      return client.finalize(draft);
    })
    .then(function (contract) {
      assert(
        /^[0-9a-f]{64}$/.test(contract.contract_sha256),
        "finalize 写入了合法的 contract_sha256",
      );

      fs.mkdirSync(OUT_DIR, { recursive: true });
      var outFile = path.join(OUT_DIR, "requirements_contract.json");
      fs.writeFileSync(
        outFile,
        JSON.stringify(contract, null, 2) + "\n",
        "utf8",
      );
      console.log("     已写出：" + path.relative(process.cwd(), outFile));
      console.log("     contract_sha256 = " + contract.contract_sha256);

      console.log("[4] POST /api/validate（MOCK 本地预检）");
      return client.validate(outFile).then(function (verdict) {
        assert(
          verdict.status === "pass",
          "本地预检 pass（errors: " + JSON.stringify(verdict.errors) + "）",
        );
        assert(Array.isArray(verdict.errors), "verdict.errors 是数组");
        assert(
          Object.keys(verdict).sort().join(",") === "errors,status",
          "verdict 只含契约定义的 status / errors",
        );
      });
    })
    .then(function () {
      console.log("[5] 契约语义：blocking 未答必须被拦下");
      var client2 = new api.ApiClient("mock", "");
      return client2.propose("x").then(function (proposal) {
        proposal.questions[0].answer = ""; // blocking, left empty
        proposal.questions[1].answer = ""; // blocking, left empty
        proposal.questions[2].answer = "unknown"; // nonblocking, explicit
        proposal.assumptions[0].decision = "confirmed";

        var draft = builder.buildDraft({
          boardId: "b",
          author: "a",
          userGoal: "g",
          intentPath: "p",
          statements: [{ id: "S1", text: "t", type: "other" }],
          questions: proposal.questions,
          assumptions: proposal.assumptions,
          forbidden: [],
        });
        return client2
          .finalize(draft)
          .then(function () {
            return client2.validate("in-memory");
          })
          .then(function (verdict) {
            assert(verdict.status === "fail", "blocking 未答 -> 预检 fail");
            assert(
              verdict.errors.length === 2,
              "两个 blocking 未答各报一条错误",
            );
            verdict.errors.forEach(function (e) {
              console.log("     - " + e);
            });
          });
      });
    })
    .then(function () {
      console.log(
        "\n" + (process.exitCode ? "SMOKE TEST FAILED" : "SMOKE TEST PASSED"),
      );
    })
    .catch(function (exc) {
      console.error(
        "FAIL: unexpected exception: " + (exc && exc.stack ? exc.stack : exc),
      );
      process.exitCode = 1;
    });
}

run();
