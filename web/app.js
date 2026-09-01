/* Requirements workbench UI.
 *
 * Contract: docs/api/requirements_api.md is the only specification this file
 * implements. The five semantics in that document's "前端必须遵守的语义"
 * section are enforced here, in order:
 *
 *   1. an unanswered blocking question disables contract generation;
 *   2. "unknown" / "No preference" are offered, but an answer must be chosen
 *      explicitly - an empty answer is never submitted;
 *   3. the LLM's question list is editable before answering;
 *   4. validation errors[] are rendered verbatim, never filtered or polished.
 *
 * No framework, no build step, no external dependency: open index.html
 * directly. Scripts are plain (not modules) so file:// origins work.
 */
(function () {
  "use strict";

  var AEDL = window.AEDL;
  var client = new AEDL.api.ApiClient("mock", "http://127.0.0.1:8787");

  var SCHEMA = "https://aedl.local/schemas/requirements-contract.v1.json";

  var DIMENSIONS = [
    "power",
    "mcu",
    "sensor",
    "connectivity",
    "display",
    "formfactor",
    "other",
  ];
  var STATEMENT_TYPES = [
    "power",
    "mcu",
    "sensor",
    "connectivity",
    "display",
    "formfactor",
    "other",
  ];
  var EXPLICIT_ANSWERS = ["unknown", "No preference"];

  var state = {
    mode: "mock",
    baseUrl: "http://127.0.0.1:8787",
    questions: [],
    assumptions: [],
    statements: [],
    requirements: [],
    forbidden: [],
    contract: null,
    verdict: null,
  };

  /* --------------------------------------------------------------- utils */

  function el(id) {
    return document.getElementById(id);
  }

  function h(tag, attrs, children) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined) return;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.indexOf("on") === 0)
        node.addEventListener(key.slice(2).toLowerCase(), value);
      else node.setAttribute(key, value === true ? "" : value);
    });
    (children || []).forEach(function (child) {
      node.appendChild(child);
    });
    return node;
  }

  function parseIdList(text) {
    return String(text || "")
      .split(",")
      .map(function (part) {
        return part.trim();
      })
      .filter(function (part) {
        return part.length > 0;
      });
  }

  function isoNow() {
    var d = new Date();
    var pad = function (n) {
      return String(n).padStart(2, "0");
    };
    var off = -d.getTimezoneOffset();
    var sign = off >= 0 ? "+" : "-";
    var abs = Math.abs(off);
    return (
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      "T" +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes()) +
      ":" +
      pad(d.getSeconds()) +
      sign +
      pad(Math.floor(abs / 60)) +
      ":" +
      pad(abs % 60)
    );
  }

  function nextNumericId(prefix, items) {
    var max = 0;
    items.forEach(function (item) {
      var m = /^([A-Za-z]+)(\d+)$/.exec(String(item.id || ""));
      if (m && m[1] === prefix) max = Math.max(max, parseInt(m[2], 10));
    });
    return prefix + (max + 1);
  }

  function setStatus(node, message, kind) {
    node.textContent = message || "";
    node.className = "status" + (kind ? " " + kind : "");
  }

  /* --------------------------------------------------------------- config */

  function loadConfig() {
    try {
      var raw = window.localStorage.getItem("aedl.workbench");
      if (!raw) return;
      var cfg = JSON.parse(raw);
      if (cfg && typeof cfg === "object") {
        if (cfg.mode === "http" || cfg.mode === "mock") state.mode = cfg.mode;
        if (typeof cfg.baseUrl === "string") state.baseUrl = cfg.baseUrl;
      }
    } catch (exc) {
      /* file:// origins may deny storage; defaults are fine. */
    }
  }

  function saveConfig() {
    try {
      window.localStorage.setItem(
        "aedl.workbench",
        JSON.stringify({ mode: state.mode, baseUrl: state.baseUrl }),
      );
    } catch (exc) {
      /* non-fatal */
    }
  }

  function applyMode() {
    client.setMode(state.mode, state.baseUrl);
    el("mode-select").value = state.mode;
    el("base-url").value = state.baseUrl;
    el("base-url").disabled = state.mode !== "http";

    var banner = el("mode-banner");
    banner.className = "banner " + state.mode;
    if (state.mode === "http") {
      banner.textContent =
        "真实 API 模式：请求发往 " +
        state.baseUrl +
        "。P1 的 gates/requirements_runtime_server.py 尚未提供，连接失败属预期。";
    } else {
      banner.textContent =
        "MOCK 模式：/api/* 由浏览器内的 mock 传输层应答，不联网。" +
        "第 5 步的校验结果是前端本地预检，不是 gates/requirements_contract.py 的真实门禁结果。";
    }
    saveConfig();
  }

  /* --------------------------------------------------------------- step 1 */

  function loadProposal() {
    var request = el("nl-input").value.trim();
    if (!request) {
      setStatus(el("propose-status"), "请先填写需求原文", "error");
      return;
    }
    setStatus(el("propose-status"), "请求中…");
    el("btn-propose").disabled = true;

    client
      .propose(request)
      .then(function (proposal) {
        state.questions = proposal.questions;
        state.assumptions = proposal.assumptions.map(function (a) {
          a.decision = null;
          return a;
        });
        state.contract = null;
        state.verdict = null;

        renderWarnings(proposal.warnings);
        renderQuestions();
        renderAssumptions();
        seedStatements(request);
        renderForbidden();
        updateCounters();
        renderPreview();
        renderVerdict();

        setStatus(
          el("propose-status"),
          "已获取 " +
            proposal.questions.length +
            " 个问题、" +
            proposal.assumptions.length +
            " 条假设",
          "ok",
        );
      })
      .catch(function (exc) {
        setStatus(el("propose-status"), exc.message, "error");
      })
      .then(function () {
        el("btn-propose").disabled = false;
      });
  }

  function renderWarnings(warnings) {
    var box = el("warnings-box");
    box.textContent = "";
    if (!warnings || !warnings.length) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    box.appendChild(h("strong", { text: "建议层告警（原样展示，不隐藏）：" }));
    box.appendChild(
      h(
        "ul",
        {},
        warnings.map(function (w) {
          return h("li", { text: w });
        }),
      ),
    );
  }

  /** The contract must trace back to the user's own words; seed one statement. */
  function seedStatements(request) {
    if (state.statements.length) return;
    state.statements = [{ id: "S1", text: request, type: "other" }];
    renderStatements();
  }

  /* --------------------------------------------------------------- step 2 */

  function renderQuestions() {
    var list = el("questions-list");
    list.textContent = "";
    if (!state.questions.length) {
      list.appendChild(
        h("p", {
          class: "hint",
          text: "尚无问题清单。先在左侧填入需求并点击「获取建议问题」。",
        }),
      );
      return;
    }
    state.questions.forEach(function (q, index) {
      list.appendChild(questionCard(q, index));
    });
  }

  function questionCard(q, index) {
    var card = h("div", { class: "card " + q.kind });

    /* --- head: id + kind tag + dimension + delete --- */
    var kindSelect = h(
      "select",
      {
        class:
          "tag " + (q.kind === "blocking" ? "tag-blocking" : "tag-nonblocking"),
        onchange: function (event) {
          q.kind = event.target.value;
          card.className = "card " + q.kind;
          kindSelect.className =
            "tag " +
            (q.kind === "blocking" ? "tag-blocking" : "tag-nonblocking");
          updateCounters();
        },
      },
      [
        h("option", { value: "blocking", text: "blocking" }),
        h("option", { value: "nonblocking", text: "nonblocking" }),
      ],
    );
    kindSelect.value = q.kind;

    var dimensionSelect = h(
      "select",
      {},
      DIMENSIONS.map(function (d) {
        return h("option", { value: d, text: d });
      }),
    );
    dimensionSelect.value = q.dimension;
    dimensionSelect.addEventListener("change", function (event) {
      q.dimension = event.target.value;
    });

    card.appendChild(
      h("div", { class: "card-head" }, [
        h("span", { class: "card-id", text: q.id }),
        kindSelect,
        dimensionSelect,
        h("span", { class: "card-spacer" }),
        h("button", {
          class: "btn btn-ghost btn-sm",
          text: "删除",
          onclick: function () {
            state.questions.splice(index, 1);
            renderQuestions();
            updateCounters();
          },
        }),
      ]),
    );

    /* --- question text (editable: the proposal is only a proposal) --- */
    var textInput = h("input", {
      type: "text",
      class: "grow",
      value: q.question,
    });
    textInput.addEventListener("input", function (event) {
      q.question = event.target.value;
    });
    card.appendChild(
      h("div", { class: "card-row" }, [
        h("label", { class: "grow" }, [
          h("span", { text: "问题（可修改）" }),
          textInput,
        ]),
      ]),
    );

    /* --- options ---
     * Options are advisory scaffolding for the human; they are NOT contract
     * fields (open_questions carries exactly id/question/answer/kind/source_ids)
     * so they never reach the generated JSON.
     */
    var optionsInput = h("input", {
      type: "text",
      value: (q.options || []).join(", "),
      placeholder: "选项，逗号分隔；留空则为自由文本作答",
    });
    optionsInput.addEventListener("input", function (event) {
      var parsed = parseIdList(event.target.value);
      q.options = parsed.length ? parsed : null;
      renderAnswerRow();
    });

    var sourceIdsInput = h("input", {
      type: "text",
      value: (q.sourceIds || []).join(", "),
      placeholder: "如 S1, S2",
    });
    sourceIdsInput.addEventListener("input", function (event) {
      q.sourceIds = parseIdList(event.target.value);
    });

    card.appendChild(
      h("div", { class: "card-row" }, [
        h("label", { class: "grow" }, [
          h("span", { text: "选项（仅辅助作答，不进合同）" }),
          optionsInput,
        ]),
        h("label", {}, [h("span", { text: "source_ids" }), sourceIdsInput]),
      ]),
    );

    /* --- answer row ---
     * Contract semantics #2: "unknown" and "No preference" are valid answers,
     * but the human must choose one; an empty answer is never submitted.
     */
    var answerRow = h("div", { class: "card-row" });
    function renderAnswerRow() {
      answerRow.textContent = "";

      var choices = [{ value: "", label: "— 请选择答案 —" }];
      (q.options || []).forEach(function (opt) {
        choices.push({ value: opt, label: opt });
      });
      EXPLICIT_ANSWERS.forEach(function (opt) {
        choices.push({ value: opt, label: opt });
      });
      choices.push({ value: "__custom__", label: "自定义…" });

      var select = h(
        "select",
        {},
        choices.map(function (c) {
          return h("option", { value: c.value, text: c.label });
        }),
      );
      select.value = syncSelectToAnswer(select, q.answer);

      var input = h("input", {
        type: "text",
        class: "grow",
        value: q.answer || "",
      });
      input.addEventListener("input", function (event) {
        q.answer = event.target.value;
        select.value = syncSelectToAnswer(select, q.answer);
        renderFlag();
        updateCounters();
      });
      select.addEventListener("change", function (event) {
        if (event.target.value === "__custom__") {
          q.answer = "";
          input.value = "";
          input.focus();
        } else {
          q.answer = event.target.value;
          input.value = q.answer;
        }
        renderFlag();
        updateCounters();
      });

      var flag = h("span", { class: "answered-flag" });
      function renderFlag() {
        var filled = typeof q.answer === "string" && q.answer.trim().length > 0;
        flag.textContent = filled ? "已作答" : "未作答";
        flag.className = filled ? "answered-flag" : "unanswered-flag";
      }
      renderFlag();

      answerRow.appendChild(
        h("label", { class: "grow" }, [
          h("span", {
            text: "答案（必填；unknown / No preference 也是有效答案）",
          }),
          input,
        ]),
      );
      answerRow.appendChild(
        h("label", {}, [h("span", { text: "快速选择" }), select]),
      );
      answerRow.appendChild(flag);
    }
    renderAnswerRow();
    card.appendChild(answerRow);

    return card;
  }

  function syncSelectToAnswer(select, answer) {
    var values = Array.prototype.map.call(select.options, function (o) {
      return o.value;
    });
    if (!answer) return "";
    if (values.indexOf(answer) !== -1) return answer;
    return "__custom__";
  }

  function addQuestion() {
    state.questions.push({
      id: nextNumericId("Q", state.questions),
      question: "",
      kind: "blocking",
      dimension: "other",
      options: null,
      source: "human",
      answer: null,
      sourceIds: [],
    });
    renderQuestions();
    updateCounters();
  }

  function renderAssumptions() {
    var list = el("assumptions-list");
    list.textContent = "";
    if (!state.assumptions.length) {
      list.appendChild(
        h("p", { class: "hint", text: "本轮建议层没有提出假设。" }),
      );
      return;
    }
    state.assumptions.forEach(function (a, index) {
      var textInput = h("input", {
        type: "text",
        class: "grow",
        value: a.text,
      });
      textInput.addEventListener("input", function (event) {
        a.text = event.target.value;
      });

      function makeRadio(value, label) {
        var radio = h("input", {
          type: "radio",
          name: "assumption-" + a.id,
          value: value,
        });
        radio.checked = a.decision === value;
        radio.addEventListener("change", function () {
          a.decision = value;
          updateCounters();
        });
        return h("label", { class: "radio-inline" }, [
          radio,
          h("span", { text: label }),
        ]);
      }

      list.appendChild(
        h("div", { class: "card nonblocking" }, [
          h("div", { class: "card-head" }, [
            h("span", { class: "card-id", text: a.id }),
            h("span", { class: "tag", text: "requires_human_confirmation" }),
            h("span", { class: "card-spacer" }),
            h("button", {
              class: "btn btn-ghost btn-sm",
              text: "删除",
              onclick: function () {
                state.assumptions.splice(index, 1);
                renderAssumptions();
                updateCounters();
              },
            }),
          ]),
          h("div", { class: "card-row" }, [
            h("label", { class: "grow" }, [
              h("span", { text: "假设内容（可修改）" }),
              textInput,
            ]),
          ]),
          h("div", { class: "card-row" }, [
            makeRadio("confirmed", "确认（写入合同，status: recorded）"),
            makeRadio("rejected", "剔除（不写入合同）"),
          ]),
        ]),
      );
    });
  }

  /* --------------------------------------------------------------- step 3 */

  function renderStatements() {
    var list = el("statements-list");
    list.textContent = "";
    if (!state.statements.length) {
      list.appendChild(
        h("p", { class: "hint", text: "尚未添加源语句。合同必须至少有一条。" }),
      );
      return;
    }
    state.statements.forEach(function (s, index) {
      var typeSelect = h(
        "select",
        {},
        STATEMENT_TYPES.map(function (t) {
          return h("option", { value: t, text: t });
        }),
      );
      typeSelect.value = s.type;
      typeSelect.addEventListener("change", function (event) {
        s.type = event.target.value;
      });

      var idInput = h("input", { type: "text", value: s.id });
      idInput.addEventListener("input", function (event) {
        s.id = event.target.value;
      });

      var textInput = h("input", {
        type: "text",
        class: "grow",
        value: s.text,
      });
      textInput.addEventListener("input", function (event) {
        s.text = event.target.value;
      });

      list.appendChild(
        h("div", { class: "card" }, [
          h("div", { class: "card-row" }, [
            h("label", {}, [h("span", { text: "id" }), idInput]),
            h("label", { class: "grow" }, [
              h("span", { text: "text（用户原话）" }),
              textInput,
            ]),
            h("label", {}, [h("span", { text: "type" }), typeSelect]),
            h("button", {
              class: "btn btn-ghost btn-sm",
              text: "删除",
              onclick: function () {
                state.statements.splice(index, 1);
                renderStatements();
                updateCounters();
              },
            }),
          ]),
        ]),
      );
    });
  }

  function addStatement() {
    state.statements.push({
      id: nextNumericId("S", state.statements),
      text: "",
      type: "other",
    });
    renderStatements();
    updateCounters();
  }

  function renderRequirements() {
    var list = el("requirements-list");
    list.textContent = "";
    if (!state.requirements.length) {
      list.appendChild(
        h("p", { class: "hint", text: "尚未添加已决需求（可留空）。" }),
      );
      return;
    }
    state.requirements.forEach(function (r, index) {
      var idInput = h("input", { type: "text", value: r.id });
      idInput.addEventListener("input", function (event) {
        r.id = event.target.value;
      });

      var textInput = h("input", {
        type: "text",
        class: "grow",
        value: r.text,
      });
      textInput.addEventListener("input", function (event) {
        r.text = event.target.value;
      });

      var sourceInput = h("input", {
        type: "text",
        value: (r.sourceIds || []).join(", "),
      });
      sourceInput.addEventListener("input", function (event) {
        r.sourceIds = parseIdList(event.target.value);
      });

      list.appendChild(
        h("div", { class: "card" }, [
          h("div", { class: "card-row" }, [
            h("label", {}, [h("span", { text: "id" }), idInput]),
            h("label", { class: "grow" }, [
              h("span", { text: "text" }),
              textInput,
            ]),
            h("label", {}, [h("span", { text: "source_ids" }), sourceInput]),
            h("button", {
              class: "btn btn-ghost btn-sm",
              text: "删除",
              onclick: function () {
                state.requirements.splice(index, 1);
                renderRequirements();
              },
            }),
          ]),
        ]),
      );
    });
  }

  function addRequirement() {
    state.requirements.push({
      id: nextNumericId("R", state.requirements),
      text: "",
      sourceIds: [],
    });
    renderRequirements();
  }

  function renderForbidden() {
    var list = el("forbidden-list");
    list.textContent = "";
    if (!state.forbidden.length) {
      list.appendChild(h("p", { class: "hint", text: "尚未添加禁用假设。" }));
      return;
    }
    state.forbidden.forEach(function (text, index) {
      var input = h("input", { type: "text", class: "grow", value: text });
      input.addEventListener("input", function (event) {
        state.forbidden[index] = event.target.value;
      });

      list.appendChild(
        h("div", { class: "card" }, [
          h("div", { class: "card-row" }, [
            h("label", { class: "grow" }, [
              h("span", { text: "禁用假设" }),
              input,
            ]),
            h("button", {
              class: "btn btn-ghost btn-sm",
              text: "删除",
              onclick: function () {
                state.forbidden.splice(index, 1);
                renderForbidden();
              },
            }),
          ]),
        ]),
      );
    });
  }

  function addForbidden() {
    state.forbidden.push("");
    renderForbidden();
  }

  /* --------------------------------------------------------------- gating */

  function unansweredCounts() {
    var blocking = 0;
    var nonblocking = 0;
    state.questions.forEach(function (q) {
      var filled = typeof q.answer === "string" && q.answer.trim().length > 0;
      if (filled) return;
      if (q.kind === "blocking") blocking++;
      else nonblocking++;
    });
    return { blocking: blocking, nonblocking: nonblocking };
  }

  function blockers() {
    var reasons = [];
    var counts = unansweredCounts();

    if (!state.questions.length) {
      reasons.push("尚未获取或新增任何问题");
    }
    if (counts.blocking > 0) {
      reasons.push("还有 " + counts.blocking + " 个 blocking 问题未作答");
    }
    if (counts.nonblocking > 0) {
      reasons.push(
        "还有 " +
          counts.nonblocking +
          " 个 nonblocking 问题未作答" +
          "（契约语义 #2：必须显式选择，unknown / No preference 亦可，但不能空着）",
      );
    }
    state.assumptions.forEach(function (a) {
      if (!a.decision)
        reasons.push(
          "假设 " + a.id + " 未确认也未剔除（requires_human_confirmation）",
        );
    });
    if (!el("nl-input").value.trim()) reasons.push("user_goal 为空");
    if (!el("meta-board-id").value.trim()) reasons.push("board_id 为空");
    if (!el("meta-author").value.trim()) reasons.push("author 为空");
    if (!el("meta-intent-path").value.trim())
      reasons.push("intent_binding.intent_path 为空");
    if (
      !state.statements.filter(function (s) {
        return s.text.trim();
      }).length
    ) {
      reasons.push("source_statements 为空（合同必须能追溯到用户原话）");
    }
    return reasons;
  }

  function updateCounters() {
    var counts = unansweredCounts();

    var blockingPill = el("counter-blocking");
    blockingPill.textContent =
      counts.blocking > 0
        ? "还剩 " + counts.blocking + " 个必答问题"
        : "必答问题已全部作答";
    blockingPill.className =
      "pill " + (counts.blocking > 0 ? "pill-danger" : "pill-clear");

    el("counter-nonblocking").textContent = counts.nonblocking + " 个选答未答";

    var reasons = blockers();
    el("btn-finalize").disabled = reasons.length > 0;
    el("finalize-blocker").textContent = reasons.length
      ? "无法生成合同：" + reasons.join("；")
      : "";
  }

  /* --------------------------------------------------------------- step 4 */

  /** Collect UI state into a draft via the shared builder (see contract-builder.js). */
  function buildDraft() {
    return AEDL.contractBuilder.buildDraft({
      boardId: el("meta-board-id").value,
      author: el("meta-author").value,
      userGoal: el("nl-input").value,
      intentPath: el("meta-intent-path").value,
      statements: state.statements,
      requirements: state.requirements,
      questions: state.questions,
      assumptions: state.assumptions,
      forbidden: state.forbidden,
    });
  }

  function finalize() {
    setStatus(el("finalize-status"), "生成中…");
    el("btn-finalize").disabled = true;

    client
      .finalize(buildDraft())
      .then(function (contract) {
        state.contract = contract;
        state.verdict = null;
        renderPreview();
        renderVerdict();
        el("btn-download").disabled = false;
        el("btn-copy").disabled = false;
        el("btn-validate").disabled = false;
        setStatus(
          el("finalize-status"),
          "合同已生成（自哈希由 /api/finalize 写入）",
          "ok",
        );
      })
      .catch(function (exc) {
        setStatus(el("finalize-status"), exc.message, "error");
      })
      .then(function () {
        updateCounters();
      });
  }

  function renderPreview() {
    var pre = el("contract-preview");
    pre.textContent = "";
    var code = document.createElement("code");
    code.textContent = state.contract
      ? JSON.stringify(state.contract, null, 2)
      : "// 尚未生成合同";
    pre.appendChild(code);
  }

  function contractFileName() {
    var boardId = el("meta-board-id").value.trim() || "contract";
    return boardId.replace(/[^\w.-]+/g, "_") + ".requirements_contract.json";
  }

  function download() {
    if (!state.contract) return;
    var blob = new Blob([JSON.stringify(state.contract, null, 2) + "\n"], {
      type: "application/json",
    });
    var url = URL.createObjectURL(blob);
    var link = h("a", { href: url, download: contractFileName() });
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function copyJson() {
    if (!state.contract) return;
    var text = JSON.stringify(state.contract, null, 2);
    var done = function () {
      setStatus(el("finalize-status"), "已复制到剪贴板", "ok");
    };
    var fail = function () {
      setStatus(el("finalize-status"), "复制失败，请手动从预览区选择", "error");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fail);
    } else {
      fail();
    }
  }

  /* --------------------------------------------------------------- step 5 */

  function validate() {
    setStatus(el("validate-status"), "校验中…");
    el("btn-validate").disabled = true;

    client
      .validate(contractPathInput())
      .then(function (verdict) {
        state.verdict = verdict;
        renderVerdict(client.isMock());
        setStatus(el("validate-status"), "校验完成", "ok");
      })
      .catch(function (exc) {
        state.verdict = null;
        renderVerdict(client.isMock());
        setStatus(el("validate-status"), exc.message, "error");
      })
      .then(function () {
        el("btn-validate").disabled = !state.contract;
      });
  }

  function contractPathInput() {
    var custom = el("validate-path").value.trim();
    if (custom) return custom;
    return "web/_session/" + contractFileName();
  }

  function renderVerdict(isMock) {
    var box = el("verdict-box");
    if (!state.verdict) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");

    var badge = el("verdict-badge");
    badge.textContent = state.verdict.status === "pass" ? "PASS" : "FAIL";
    badge.className =
      "badge " +
      (state.verdict.status === "pass" ? "badge-pass" : "badge-fail");

    el("verdict-source").textContent = isMock
      ? "来源：MOCK 本地预检（仅覆盖 docs/api/requirements_api.md 明文规定的规则）— 不是 gates/requirements_contract.py 的真实门禁结果"
      : "来源：POST /api/validate";

    // Semantics #4: errors[] rendered verbatim, no filtering, no rewording.
    var list = el("verdict-errors");
    list.textContent = "";
    state.verdict.errors.forEach(function (message) {
      list.appendChild(h("li", { text: message }));
    });
    if (!state.verdict.errors.length) {
      list.appendChild(h("li", { class: "hint", text: "（无错误信息）" }));
    }
  }

  /* --------------------------------------------------------------- wiring */

  function bind() {
    el("mode-select").addEventListener("change", function (event) {
      state.mode = event.target.value;
      applyMode();
    });
    el("base-url").addEventListener("change", function (event) {
      state.baseUrl = event.target.value.trim() || state.baseUrl;
      applyMode();
    });

    ["nl-input", "meta-board-id", "meta-author", "meta-intent-path"].forEach(
      function (id) {
        el(id).addEventListener("input", function () {
          if (state.questions.length) updateCounters();
        });
      },
    );

    el("btn-propose").addEventListener("click", loadProposal);
    el("btn-add-question").addEventListener("click", addQuestion);
    el("btn-add-statement").addEventListener("click", addStatement);
    el("btn-add-requirement").addEventListener("click", addRequirement);
    el("btn-add-forbidden").addEventListener("click", addForbidden);
    el("btn-finalize").addEventListener("click", finalize);
    el("btn-download").addEventListener("click", download);
    el("btn-copy").addEventListener("click", copyJson);
    el("btn-validate").addEventListener("click", validate);
  }

  function init() {
    loadConfig();
    bind();
    applyMode();
    renderQuestions();
    renderAssumptions();
    renderStatements();
    renderRequirements();
    renderForbidden();
    renderPreview();
    updateCounters();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
