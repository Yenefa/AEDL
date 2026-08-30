/* Assembles the pre-hash requirements contract draft.
 *
 * Shape is taken verbatim from docs/api/requirements_api.md ("合同 JSON 形状").
 * This module holds no DOM knowledge so that web/smoke-test.js exercises the
 * exact same assembly path the UI does - a test that reimplements the builder
 * would only prove the test agrees with itself.
 *
 * contract_sha256 is deliberately NOT written here: the contract states that
 * /api/finalize produces the self-hash. Authoring the hash is the server's
 * job (gates/requirements_runtime.py::draft_contract -> finalize_contract).
 */
(function (root, factory) {
  "use strict";
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  } else {
    (root.AEDL = root.AEDL || {}).contractBuilder = mod;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var SCHEMA = "https://aedl.local/schemas/requirements-contract.v1.json";

  /** tz-aware ISO8601, as required by the contract's created_at field. */
  function isoNow(date) {
    var d = date || new Date();
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

  function trimmed(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function idList(value) {
    return Array.isArray(value) ? value.slice() : [];
  }

  /**
   * @param {object} input
   * @param {string} input.boardId
   * @param {string} input.author
   * @param {string} input.userGoal
   * @param {string} input.intentPath
   * @param {string} [input.createdAt]
   * @param {Array<{id,text,type}>} [input.statements]
   * @param {Array<{id,text,sourceIds}>} [input.requirements]
   * @param {Array<{id,question,answer,kind,sourceIds}>} [input.questions]
   * @param {Array<{id,text,decision}>} [input.assumptions]  decision: confirmed|rejected
   * @param {Array<string>} [input.forbidden]
   */
  function buildDraft(input) {
    var data = input || {};

    // open_questions carries exactly id/question/answer/kind/source_ids.
    // dimension / options / source belong to the proposal layer and must not
    // reach the contract (the gate rejects unknown fields).
    var questions = (data.questions || []).map(function (q) {
      return {
        id: q.id,
        question: q.question,
        answer: typeof q.answer === "string" ? q.answer : "",
        kind: q.kind === "nonblocking" ? "nonblocking" : "blocking",
        source_ids: idList(q.sourceIds),
      };
    });

    // Only explicitly confirmed assumptions are recorded. A rejected one is
    // dropped, not annotated: an assumption that was never agreed to has no
    // business being embedded in a signed artifact.
    var assumptions = (data.assumptions || [])
      .filter(function (a) {
        return a.decision === "confirmed";
      })
      .map(function (a) {
        return { id: a.id, text: a.text, source_ids: [], status: "recorded" };
      });

    return {
      $schema: SCHEMA,
      schema_version: 1,
      board_id: trimmed(data.boardId),
      created_at: data.createdAt || isoNow(),
      author: trimmed(data.author),
      user_goal: trimmed(data.userGoal),
      source_statements: (data.statements || [])
        .filter(function (s) {
          return trimmed(s.text).length > 0;
        })
        .map(function (s) {
          return { id: s.id, text: s.text, type: s.type };
        }),
      resolved_requirements: (data.requirements || [])
        .filter(function (r) {
          return trimmed(r.text).length > 0;
        })
        .map(function (r) {
          return { id: r.id, text: r.text, source_ids: idList(r.sourceIds) };
        }),
      open_questions: questions,
      assumptions: assumptions,
      forbidden_assumptions: (data.forbidden || [])
        .map(trimmed)
        .filter(function (t) {
          return t.length > 0;
        }),
      // docs/api/requirements_api.md: intent_binding is ONE-directional
      // (lockfile pattern) - intent_path only, no intent_sha256. The intent
      // side holds {sha256, path} pointing back at the contract; a mutual hash
      // would be circular (see gates/requirements_contract.py C4).
      intent_binding: {
        intent_path: trimmed(data.intentPath),
      },
    };
  }

  return { buildDraft: buildDraft, isoNow: isoNow, SCHEMA: SCHEMA };
});
