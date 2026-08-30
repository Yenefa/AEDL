/* Mock data and mock-side pre-checks for the requirements workbench.
 *
 * The proposal below is copied VERBATIM from the "Mock 数据" section of
 * docs/api/requirements_api.md. It is the contract's own sample, not an
 * invention of this frontend - do not "improve" it here; change the contract
 * document and mirror it.
 *
 * The pre-check at the bottom is deliberately NOT a reimplementation of
 * gates/requirements_contract.py (C1-C7). That gate is Python, is the sole
 * authority, and cannot run in a browser. This only enforces the rules the API
 * document states in its own words, so the mock never issues a verdict that
 * pretends to come from the real gate.
 */
(function (root, factory) {
  "use strict";
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  } else {
    (root.AEDL = root.AEDL || {}).mockData = mod;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /* From docs/api/requirements_api.md - "Mock 数据（真实服务未起时前端内置）". */
  var MOCK_PROPOSAL = {
    questions: [
      {
        id: "Q1",
        question: "板子如何供电？",
        kind: "blocking",
        dimension: "power",
        options: ["USB-C 5V", "锂电池", "外部电源"],
        source: "llm_proposal",
        answer: null,
      },
      {
        id: "Q2",
        question: "需要板载调试器吗？",
        kind: "blocking",
        dimension: "other",
        options: ["需要", "不需要"],
        source: "llm_proposal",
        answer: null,
      },
      {
        id: "Q3",
        question: "工作温度范围？",
        kind: "nonblocking",
        dimension: "other",
        options: ["民用 0~50°C", "工业 -40~85°C"],
        source: "llm_proposal",
        answer: null,
      },
    ],
    assumptions: [
      {
        id: "A1",
        text: "默认单面板两层布线",
        requires_human_confirmation: true,
      },
    ],
    warnings: [],
  };

  /** Mock /api/propose: returns the contract's sample regardless of input. */
  function buildProposal() {
    return JSON.parse(JSON.stringify(MOCK_PROPOSAL));
  }

  /**
   * Local pre-check of a generated contract.
   * Every rule below is traceable to docs/api/requirements_api.md:
   *   - the 合同 JSON 形状 block (field presence and primitive types);
   *   - the 前端必须遵守的语义 block (rules 1 and 2).
   * Returns an array of human-readable errors (empty = pre-check clean).
   */
  function precheckContract(contract) {
    var errors = [];

    if (!contract || typeof contract !== "object") {
      return ["合同不是一个 JSON 对象"];
    }

    if (
      contract.$schema !==
      "https://aedl.local/schemas/requirements-contract.v1.json"
    ) {
      errors.push("合同 $schema 不是 requirements-contract.v1.json");
    }
    if (contract.schema_version !== 1) {
      errors.push("合同 schema_version 必须为 1");
    }

    ["board_id", "author", "user_goal"].forEach(function (field) {
      if (typeof contract[field] !== "string" || !contract[field].trim()) {
        errors.push("合同缺少非空字段：" + field);
      }
    });

    var statements = contract.source_statements;
    if (!Array.isArray(statements) || !statements.length) {
      errors.push(
        "source_statements 不能为空（合同必须能追溯到用户的原始陈述）",
      );
    }

    var questions = contract.open_questions;
    if (!Array.isArray(questions)) {
      errors.push("open_questions 必须是数组");
    } else {
      questions.forEach(function (q, index) {
        var label = q && q.id ? q.id : "open_questions[" + index + "]";
        if (!q || typeof q !== "object") {
          errors.push("open_questions[" + index + "] 必须是对象");
          return;
        }
        if (typeof q.question !== "string" || !q.question.trim()) {
          errors.push(label + " 缺少问题文本");
        }
        if (q.kind !== "blocking" && q.kind !== "nonblocking") {
          errors.push(label + " 的 kind 非法（只能是 blocking / nonblocking）");
          return;
        }
        if (typeof q.answer !== "string") {
          errors.push(label + " 的 answer 必须是字符串");
          return;
        }
        // 契约语义 #1/#2：答案必须显式给出，空着不许提交。
        if (!q.answer.trim()) {
          errors.push(
            label +
              "（" +
              q.kind +
              "）未作答：" +
              (q.kind === "blocking"
                ? "blocking 问题未回答不得生成合同"
                : "必须显式选择，unknown / No preference 也是有效答案，但不能空着"),
          );
        }
      });
    }

    var assumptions = contract.assumptions;
    if (!Array.isArray(assumptions)) {
      errors.push("assumptions 必须是数组");
    } else {
      assumptions.forEach(function (a, index) {
        if (!a || typeof a !== "object") {
          errors.push("assumptions[" + index + "] 必须是对象");
          return;
        }
        if (typeof a.text !== "string" || !a.text.trim()) {
          errors.push("assumptions[" + (a.id || index) + "] 缺少文本");
        }
        if (a.status !== "recorded") {
          errors.push(
            "assumptions[" + (a.id || index) + "] 的 status 必须为 'recorded'",
          );
        }
      });
    }

    var forbidden = contract.forbidden_assumptions;
    if (!Array.isArray(forbidden)) {
      errors.push("forbidden_assumptions 必须是数组");
    }

    var binding = contract.intent_binding;
    if (!binding || typeof binding !== "object") {
      errors.push("intent_binding 必须是对象");
    } else if (
      typeof binding.intent_path !== "string" ||
      !binding.intent_path.trim()
    ) {
      errors.push("intent_binding.intent_path 不能为空");
    }

    var hash = contract.contract_sha256;
    if (typeof hash !== "string" || !/^[0-9a-f]{64}$/.test(hash)) {
      errors.push(
        "contract_sha256 缺失或格式非法（自哈希由 /api/finalize 写入，" +
          "其正确性由 gates/requirements_contract.py 判定，前端不做校验）",
      );
    }

    return errors;
  }

  return {
    MOCK_PROPOSAL: MOCK_PROPOSAL,
    buildProposal: buildProposal,
    precheckContract: precheckContract,
  };
});
