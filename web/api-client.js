/* Transport layer for the Requirements Runtime API.
 *
 * Single source of truth: docs/api/requirements_api.md (P1, ZCode/GLM).
 * Every endpoint path, verb and response field below is taken verbatim from
 * that document. Nothing here invents a field.
 *
 * CONTRACT GAPS (recorded, NOT guessed around - see docs/COLLABORATION.md
 * TASK-P2 and web/README.md). The document specifies the *response* shapes but
 * leaves three request bodies and one response body undefined:
 *
 *   1. POST /api/propose  - "入参 NL 需求文本". Key name undefined.
 *      Sent as {"request": <text>} because P1's own
 *      gates/requirements_runtime.py::build_proposal_prompt names its
 *      parameter `request`. Still needs P1 to confirm.
 *   2. POST /api/finalize - "入参 用户最终确认". Shape undefined.
 *      Sent as {"contract": <draft>} (the draft is the human's confirmation).
 *   3. POST /api/validate - "入参 合同路径". Key name undefined, and a browser
 *      has no server-side filesystem path to name. Sent as {"path": <...>}.
 *   4. POST /api/answer   - response is "返回未答 blocking 数" with no type or
 *      envelope. The client therefore does NOT depend on it: the unanswered
 *      blocking count is recomputed locally from the authoritative question
 *      list, and the raw response is only surfaced in the debug panel.
 *   5. Error codes: the document defines none except HTTP 404 on
 *      GET /api/contract ("无则 404"). Everything else is surfaced raw.
 */
(function (root, factory) {
  "use strict";
  var mod = factory(
    typeof module === "object" && module.exports
      ? require("./mock-data.js")
      : root.AEDL.mockData,
    typeof module === "object" && module.exports
      ? require("./canonical-json.js")
      : root.AEDL.canonicalJson,
  );
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  } else {
    (root.AEDL = root.AEDL || {}).api = mod;
  }
})(
  typeof globalThis !== "undefined" ? globalThis : this,
  function (mockData, canonicalJson) {
    "use strict";

    var REQUIREMENTS_CONTRACT_SCHEMA =
      "https://aedl.local/schemas/requirements-contract.v1.json";

    /* ------------------------------------------------------------------ *
     * Errors
     * ------------------------------------------------------------------ */

    /** Transport/HTTP failure. `status` is null when the request never completed. */
    function ApiError(message, status, body) {
      this.name = "ApiError";
      this.message = message;
      this.status = status === undefined ? null : status;
      this.body = body === undefined ? null : body;
    }
    ApiError.prototype = Object.create(Error.prototype);
    ApiError.prototype.constructor = ApiError;

    /* ------------------------------------------------------------------ *
     * Mock transport - in-process, no network, no build step.
     * Exists so the closed loop can be demoed by double-clicking index.html.
     * ------------------------------------------------------------------ */

    function MockTransport() {
      this.proposal = null;
      this.answers = {};
      this.contract = null;
    }

    MockTransport.prototype.propose = function (request) {
      var self = this;
      this.proposal = mockData.buildProposal(request);
      this.answers = {};
      return Promise.resolve(clone(this.proposal));
    };

    MockTransport.prototype.getContract = function () {
      if (!this.contract) {
        // Contract: "GET /api/contract 出参 当前合同（无则 404）".
        var err = new ApiError("no contract yet (404)", 404, null);
        return Promise.reject(err);
      }
      return Promise.resolve(clone(this.contract));
    };

    MockTransport.prototype.answer = function (questionId, answer) {
      if (typeof answer !== "string") {
        return Promise.reject(
          new ApiError("answer must be a string", 400, null),
        );
      }
      this.answers[questionId] = answer;
      var answers = this.answers;
      var proposal = this.proposal || { questions: [] };
      var unanswered = proposal.questions.filter(function (q) {
        if (q.kind !== "blocking") return false;
        var value = answers[q.id];
        return typeof value !== "string" || !value.trim();
      }).length;
      // Return shape is UNDEFINED in the contract; the UI does not depend on it.
      return Promise.resolve({ unanswered_blocking: unanswered });
    };

    MockTransport.prototype.finalize = function (draft) {
      // The server owns the self-hash; the mock reproduces it with the same
      // canonicalization the Python gate uses (verified by web/verify-hash.js).
      var contract = clone(draft);
      contract.contract_sha256 = canonicalJson.contractHash(contract);
      this.contract = contract;
      return Promise.resolve(clone(contract));
    };

    /**
     * Local pre-check, NOT the real gate.
     *
     * gates/requirements_contract.py (C1-C7) is Python and cannot run here.
     * This only enforces what docs/api/requirements_api.md itself states, so the
     * mock never reports a fake "pass" on behalf of the real gate. The UI labels
     * the result accordingly.
     */
    MockTransport.prototype.validate = function (contractPath) {
      var contract = this.contract;
      if (!contract) {
        return Promise.resolve({
          status: "fail",
          errors: ["尚无已生成的合同：请先执行 /api/finalize"],
        });
      }
      var errors = mockData.precheckContract(contract, contractPath);
      return Promise.resolve({
        status: errors.length ? "fail" : "pass",
        errors: errors,
      });
    };

    /* ------------------------------------------------------------------ *
     * HTTP transport - the real thing, once P1 serves it.
     * ------------------------------------------------------------------ */

    function HttpTransport(baseUrl) {
      this.baseUrl = String(baseUrl || "").replace(/\/+$/, "");
    }

    HttpTransport.prototype.url = function (pathname) {
      return this.baseUrl + pathname;
    };

    HttpTransport.prototype.request = function (pathname, options) {
      var opts = options || {};
      var url = this.url(pathname);
      var init = {
        method: opts.method || "GET",
        headers: { Accept: "application/json" },
      };
      if (opts.body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }

      var allow404 = !!opts.allow404;

      return fetch(url, init)
        .then(function (response) {
          if (response.status === 404 && allow404) return null;
          var type = response.headers.get("Content-Type") || "";
          return response.text().then(function (text) {
            if (!response.ok) {
              throw new ApiError(
                "HTTP " +
                  response.status +
                  " " +
                  response.statusText +
                  " on " +
                  init.method +
                  " " +
                  pathname,
                response.status,
                text,
              );
            }
            if (!text) return null;
            if (type.indexOf("json") !== -1) {
              try {
                return JSON.parse(text);
              } catch (exc) {
                throw new ApiError(
                  "response from " + pathname + " is not valid JSON",
                  response.status,
                  text,
                );
              }
            }
            return text;
          });
        })
        .catch(function (exc) {
          if (exc instanceof ApiError) throw exc;
          // Network failure / CORS / server not running.
          throw new ApiError(
            "无法连接 " +
              url +
              "（" +
              (exc && exc.message ? exc.message : exc) +
              "）",
            null,
            null,
          );
        });
    };

    HttpTransport.prototype.propose = function (request) {
      return this.request("/api/propose", {
        method: "POST",
        body: { request: request },
      });
    };

    HttpTransport.prototype.getContract = function () {
      return this.request("/api/contract", { method: "GET", allow404: true });
    };

    HttpTransport.prototype.answer = function (questionId, answer) {
      return this.request("/api/answer", {
        method: "POST",
        body: { question_id: questionId, answer: answer },
      });
    };

    HttpTransport.prototype.finalize = function (draft) {
      return this.request("/api/finalize", {
        method: "POST",
        body: { contract: draft },
      });
    };

    HttpTransport.prototype.validate = function (contractPath) {
      return this.request("/api/validate", {
        method: "POST",
        body: { path: contractPath },
      });
    };

    /* ------------------------------------------------------------------ *
     * Facade
     * ------------------------------------------------------------------ */

    /**
     * One client over both transports. `label` is surfaced in the UI so a mock
     * verdict can never be mistaken for a real gate verdict.
     */
    function ApiClient(mode, baseUrl) {
      this.setMode(mode, baseUrl);
    }

    ApiClient.prototype.setMode = function (mode, baseUrl) {
      this.mode = mode === "http" ? "http" : "mock";
      this.transport =
        this.mode === "http" ? new HttpTransport(baseUrl) : new MockTransport();
    };

    ApiClient.prototype.isMock = function () {
      return this.mode === "mock";
    };

    ApiClient.prototype.propose = function (request) {
      var self = this;
      return this.transport
        .propose(request)
        .then(function (data) {
          return normalizeProposal(data);
        })
        .catch(function (exc) {
          throw wrap(exc, "/api/propose", self.mode);
        });
    };

    ApiClient.prototype.getContract = function () {
      var self = this;
      return this.transport.getContract().catch(function (exc) {
        throw wrap(exc, "/api/contract", self.mode);
      });
    };

    ApiClient.prototype.answer = function (questionId, answer) {
      var self = this;
      return this.transport.answer(questionId, answer).catch(function (exc) {
        throw wrap(exc, "/api/answer", self.mode);
      });
    };

    /** `draft` is the pre-hash contract; the response carries contract_sha256. */
    ApiClient.prototype.finalize = function (draft) {
      var self = this;
      return this.transport.finalize(draft).catch(function (exc) {
        throw wrap(exc, "/api/finalize", self.mode);
      });
    };

    ApiClient.prototype.validate = function (contractPath) {
      var self = this;
      return this.transport
        .validate(contractPath)
        .then(function (verdict) {
          return normalizeVerdict(verdict);
        })
        .catch(function (exc) {
          throw wrap(exc, "/api/validate", self.mode);
        });
    };

    /* ------------------------------------------------------------------ *
     * Response normalization - lenient about junk, strict about structure.
     * Mirrors the fail-closed philosophy of gates/requirements_runtime.py:
     * an unrecognized severity escalates, it never relaxes.
     * ------------------------------------------------------------------ */

    var KINDS = { blocking: "blocking", nonblocking: "nonblocking" };
    var DIMENSIONS = {
      power: "power",
      mcu: "mcu",
      sensor: "sensor",
      connectivity: "connectivity",
      display: "display",
      formfactor: "formfactor",
      other: "other",
    };

    function normalizeProposal(data) {
      var warnings = [];
      if (!data || typeof data !== "object") {
        return {
          questions: [],
          assumptions: [],
          warnings: ["/api/propose returned no JSON object; proposal ignored"],
        };
      }
      if (Array.isArray(data.warnings)) {
        warnings = data.warnings.filter(function (w) {
          return typeof w === "string";
        });
      }

      var questions = [];
      var seen = {};
      var rawQuestions = Array.isArray(data.questions) ? data.questions : [];
      rawQuestions.forEach(function (item, index) {
        if (!item || typeof item !== "object") {
          warnings.push("questions[" + index + "] 不是对象，已跳过");
          return;
        }
        if (typeof item.question !== "string" || !item.question.trim()) {
          warnings.push("questions[" + index + "] 缺少问题文本，已跳过");
          return;
        }
        var kind = KINDS[item.kind];
        if (!kind) {
          // Contract: unknown severity escalates to blocking, never down.
          kind = "blocking";
          warnings.push(
            "questions[" + index + "] 的 kind 无法识别，已升级为 blocking",
          );
        }
        var dimension = DIMENSIONS[item.dimension];
        if (!dimension) dimension = "other";

        var id =
          typeof item.id === "string" && item.id && !seen[item.id]
            ? item.id
            : nextId("Q", seen);
        seen[id] = true;

        questions.push({
          id: id,
          question: item.question.trim(),
          kind: kind,
          dimension: dimension,
          options: normalizeOptions(item.options),
          source: item.source === undefined ? "llm_proposal" : item.source,
          // Answers come from humans only. Never from the proposal.
          answer: null,
        });
      });

      var assumptions = [];
      var seenA = {};
      var rawAssumptions = Array.isArray(data.assumptions)
        ? data.assumptions
        : [];
      rawAssumptions.forEach(function (item, index) {
        if (!item || typeof item !== "object") {
          warnings.push("assumptions[" + index + "] 不是对象，已跳过");
          return;
        }
        if (typeof item.text !== "string" || !item.text.trim()) {
          warnings.push("assumptions[" + index + "] 缺少文本，已跳过");
          return;
        }
        var id =
          typeof item.id === "string" && item.id && !seenA[item.id]
            ? item.id
            : nextId("A", seenA);
        seenA[id] = true;
        assumptions.push({
          id: id,
          text: item.text.trim(),
          requires_human_confirmation: true,
        });
      });

      return {
        questions: questions,
        assumptions: assumptions,
        warnings: warnings,
      };
    }

    /**
     * GateVerdict is {status, errors} per contract. Only those two fields are
     * guaranteed; anything else the server adds is kept aside, never rendered as
     * if the contract defined it.
     */
    function normalizeVerdict(data) {
      if (!data || typeof data !== "object") {
        return {
          status: "fail",
          errors: ["/api/validate 没有返回可解析的校验结果"],
        };
      }
      var status = data.status === "pass" ? "pass" : "fail";
      var errors = Array.isArray(data.errors) ? data.errors.slice() : [];
      return { status: status, errors: errors };
    }

    function normalizeOptions(options) {
      if (!Array.isArray(options) || !options.length) return null;
      var cleaned = options
        .map(function (o) {
          return typeof o === "string" ? o.trim() : String(o);
        })
        .filter(function (o) {
          return o.length > 0;
        });
      return cleaned.length ? cleaned : null;
    }

    function nextId(prefix, seen) {
      var n = 1;
      while (seen[prefix + n]) n++;
      return prefix + n;
    }

    function clone(value) {
      return JSON.parse(JSON.stringify(value));
    }

    function wrap(exc, endpoint, mode) {
      if (exc instanceof ApiError) {
        exc.message = endpoint + " 失败（" + mode + " 模式）：" + exc.message;
        return exc;
      }
      return new ApiError(
        endpoint +
          " 失败（" +
          mode +
          " 模式）：" +
          (exc && exc.message ? exc.message : String(exc)),
        null,
        null,
      );
    }

    return {
      ApiClient: ApiClient,
      ApiError: ApiError,
      MockTransport: MockTransport,
      HttpTransport: HttpTransport,
      normalizeProposal: normalizeProposal,
      normalizeVerdict: normalizeVerdict,
      REQUIREMENTS_CONTRACT_SCHEMA: REQUIREMENTS_CONTRACT_SCHEMA,
    };
  },
);
