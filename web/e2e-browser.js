/* Browser end-to-end driver for the MOCK closed loop.
 *
 * Open:  web/index.html?e2e=1
 *
 * Drives the real UI - real DOM, real event handlers, real buttons - through:
 *   fill NL request -> propose -> answer every question + decide every
 *   assumption -> finalize -> validate
 * and prints PASS/FAIL per assertion into a #e2e-result panel.
 *
 * This exists because "浏览器打开能用" is an acceptance criterion for
 * TASK-P2, and a headless module test cannot prove that the DOM wiring works.
 * It is loaded only when ?e2e=1 is present.
 */
(function () {
  "use strict";

  var results = [];

  function check(label, condition, detail) {
    results.push({ label: label, ok: !!condition, detail: detail || "" });
  }

  function fire(node, type) {
    node.dispatchEvent(new Event(type, { bubbles: true }));
  }

  function setText(node, value) {
    node.value = value;
    fire(node, "input");
  }

  function waitFor(label, predicate, budgetMs) {
    return new Promise(function (resolve, reject) {
      var started = Date.now();
      (function poll() {
        var ok = false;
        try {
          ok = predicate();
        } catch (exc) {
          ok = false;
        }
        if (ok) return resolve();
        if (Date.now() - started > (budgetMs || 4000)) {
          return reject(new Error("timeout waiting for " + label));
        }
        setTimeout(poll, 25);
      })();
    });
  }

  var el = function (id) {
    return document.getElementById(id);
  };

  function run() {
    setText(
      el("nl-input"),
      "ESP32-C3 + SHT30 温湿度载板，USB-C 供电，BLE 上报",
    );
    setText(el("meta-board-id"), "e2e-browser-board");
    setText(el("meta-author"), "human+ai");
    setText(el("meta-intent-path"), "src/hardware/m2-board/intent_v1.json");

    check("初始状态：生成合同按钮禁用", el("btn-finalize").disabled);

    /* --- step 1: propose --- */
    el("btn-propose").click();

    return waitFor("问题渲染", function () {
      return el("questions-list").querySelectorAll(".card").length === 3;
    })
      .then(function () {
        check("POST /api/propose 渲染出 3 个问题卡片", true);
        // The answer row is the last .card-row of each card; the rows above it
        // hold the (pre-filled) question text and options, so scope the query.
        var answerInputs = Array.prototype.map.call(
          el("questions-list").querySelectorAll(".card"),
          function (card) {
            var rows = card.querySelectorAll(".card-row");
            return rows[rows.length - 1].querySelector("input[type=text]");
          },
        );
        check(
          "建议层 answer 恒为 null（答案输入框初始为空）",
          answerInputs.every(function (input) {
            return input && input.value === "";
          }),
        );

        var blockingBefore = el("counter-blocking").textContent;
        check(
          "未作答时提示剩余必答问题：" + blockingBefore,
          /还剩 2 个必答问题/.test(blockingBefore),
          blockingBefore,
        );
        check("未作答时生成合同按钮仍禁用", el("btn-finalize").disabled);

        /* --- step 2: answer everything --- */
        var cards = el("questions-list").querySelectorAll(".card");
        var answers = ["USB-C 5V", "No preference", "unknown"];
        for (var i = 0; i < cards.length; i++) {
          var rows = cards[i].querySelectorAll(".card-row");
          var answerRow = rows[rows.length - 1];
          var answerInput = answerRow.querySelector("input[type=text]");
          setText(answerInput, answers[i]);
        }

        var radios = el("assumptions-list").querySelectorAll(
          "input[type=radio][value=confirmed]",
        );
        check("假设渲染出确认单选框", radios.length === 1);
        Array.prototype.forEach.call(radios, function (radio) {
          radio.checked = true;
          fire(radio, "change");
        });

        check(
          "全部作答后必答计数归零：" + el("counter-blocking").textContent,
          /必答问题已全部作答/.test(el("counter-blocking").textContent),
        );
        check("全部作答后生成合同按钮启用", !el("btn-finalize").disabled);

        /* --- step 3: finalize --- */
        el("btn-finalize").click();
        return waitFor("合同生成", function () {
          return (
            el("contract-preview").textContent.indexOf("contract_sha256") !== -1
          );
        });
      })
      .then(function () {
        var preview = el("contract-preview").textContent;
        var contract = JSON.parse(preview);

        check(
          "合同含 contract_sha256（由 /api/finalize 写入）",
          /^[0-9a-f]{64}$/.test(contract.contract_sha256),
          contract.contract_sha256,
        );
        check(
          "合同 open_questions 均有非空答案",
          contract.open_questions.every(function (q) {
            return typeof q.answer === "string" && q.answer.trim().length > 0;
          }),
        );
        check(
          "合同保留 unknown / No preference 原值（未被前端改写）",
          contract.open_questions.some(function (q) {
            return q.answer === "No preference";
          }) &&
            contract.open_questions.some(function (q) {
              return q.answer === "unknown";
            }),
        );
        check(
          "open_questions 恰好含 id/question/answer/kind/source_ids",
          contract.open_questions.every(function (q) {
            return (
              Object.keys(q).sort().join(",") ===
              "answer,id,kind,question,source_ids"
            );
          }),
        );
        check(
          "已确认假设写入合同且 status=recorded",
          contract.assumptions.length === 1 &&
            contract.assumptions[0].status === "recorded",
        );
        check("下载按钮已启用", !el("btn-download").disabled);
        check("校验按钮已启用", !el("btn-validate").disabled);

        /* --- step 4: validate --- */
        el("btn-validate").click();
        return waitFor("校验结果", function () {
          return !el("verdict-box").classList.contains("hidden");
        }).then(function () {
          return contract;
        });
      })
      .then(function (contract) {
        check(
          "校验徽标为 PASS",
          el("verdict-badge").textContent === "PASS",
          el("verdict-badge").textContent,
        );
        check(
          "校验来源标注为 MOCK 本地预检（不冒充真实门禁）",
          /MOCK 本地预检/.test(el("verdict-source").textContent),
          el("verdict-source").textContent,
        );

        /* --- step 5: fail-closed re-check ---
         * Clearing a blocking answer must re-disable contract generation. */
        var firstAnswer = el("questions-list")
          .querySelector(".card")
          .querySelectorAll(".card-row");
        var answerInput =
          firstAnswer[firstAnswer.length - 1].querySelector("input[type=text]");
        setText(answerInput, "");
        check(
          "清空 blocking 答案后生成合同按钮重新禁用",
          el("btn-finalize").disabled,
        );
        check(
          "清空后提示剩余必答问题：" + el("counter-blocking").textContent,
          /还剩 1 个必答问题/.test(el("counter-blocking").textContent),
        );

        return contract;
      })
      .then(function (contract) {
        render(contract);
      })
      .catch(function (exc) {
        check(
          "驱动执行完成",
          false,
          exc && exc.message ? exc.message : String(exc),
        );
        render(null);
      });
  }

  function render(contract) {
    var panel = document.createElement("div");
    panel.id = "e2e-result";
    panel.style.cssText =
      "margin:16px;padding:12px;border:2px solid #0969da;" +
      "border-radius:6px;background:#ddf4ff;font:13px/1.6 monospace;white-space:pre-wrap";

    var failed = results.filter(function (r) {
      return !r.ok;
    });
    var lines = results.map(function (r) {
      return (
        (r.ok ? "PASS  " : "FAIL  ") +
        r.label +
        (r.detail ? "\n        " + r.detail : "")
      );
    });
    lines.push("");
    lines.push(
      "E2E " +
        (failed.length ? "FAILED" : "PASSED") +
        " (" +
        (results.length - failed.length) +
        "/" +
        results.length +
        ")",
    );
    if (contract) lines.push("contract_sha256 = " + contract.contract_sha256);

    panel.textContent = lines.join("\n");
    document.body.insertBefore(panel, document.body.firstChild);
  }

  /* app.js initializes on DOMContentLoaded; this script is appended after that
   * handler is registered, so a tick is enough to let it finish. */
  setTimeout(run, 50);
})();
