/* Canonical JSON that byte-matches the authoritative Python serialization.
 *
 * The gate computes the contract self-hash over:
 *     json.dumps(payload, ensure_ascii=False, sort_keys=True,
 *                separators=(",", ":")).encode("utf-8")
 * A browser-side JSON.stringify() does NOT match that (key order is insertion
 * order, whitespace differs). This module reproduces Python's exact rules so
 * the MOCK transport can produce the same digest the real gate would.
 *
 * Scope note: only the value types the contract can actually contain are
 * handled precisely (str, int, bool, null, list, object). Floats are
 * serialized with Number#toString, which is NOT guaranteed to match Python's
 * repr for every value; the requirements contract schema is integer/string
 * only, so this is a documented limitation rather than a silent divergence.
 */
(function (root, factory) {
  "use strict";
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  } else {
    (root.AEDL = root.AEDL || {}).canonicalJson = mod;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /** Python's json string escaping with ensure_ascii=False. */
  function encodeString(value) {
    var out = '"';
    var chars = Array.from(value); // iterate by code point, not UTF-16 unit
    for (var i = 0; i < chars.length; i++) {
      var ch = chars[i];
      var code = ch.codePointAt(0);
      if (ch === '"') out += '\\"';
      else if (ch === "\\") out += "\\\\";
      else if (ch === "\n") out += "\\n";
      else if (ch === "\r") out += "\\r";
      else if (ch === "\t") out += "\\t";
      else if (ch === "\b") out += "\\b";
      else if (ch === "\f") out += "\\f";
      else if (code < 0x20)
        out += "\\u" + ("0000" + code.toString(16)).slice(-4);
      else out += ch; // ensure_ascii=False: non-ASCII stays literal
    }
    return out + '"';
  }

  /** Compare two keys by code point, matching Python's str ordering. */
  function compareKeys(a, b) {
    var ai = Array.from(a).map(function (c) {
      return c.codePointAt(0);
    });
    var bi = Array.from(b).map(function (c) {
      return c.codePointAt(0);
    });
    var n = Math.min(ai.length, bi.length);
    for (var i = 0; i < n; i++) {
      if (ai[i] !== bi[i]) return ai[i] - bi[i];
    }
    return ai.length - bi.length;
  }

  function encode(value) {
    if (value === null) return "null";
    if (value === true) return "true";
    if (value === false) return "false";

    var type = typeof value;
    if (type === "string") return encodeString(value);
    if (type === "number") {
      if (!isFinite(value))
        throw new TypeError("canonical JSON: non-finite number");
      return String(value);
    }
    if (Array.isArray(value)) {
      var items = value.map(encode);
      return "[" + items.join(",") + "]";
    }
    if (type === "object") {
      var keys = Object.keys(value).sort(compareKeys);
      var parts = keys.map(function (k) {
        return encodeString(k) + ":" + encode(value[k]);
      });
      return "{" + parts.join(",") + "}";
    }
    throw new TypeError("canonical JSON: unsupported value of type " + type);
  }

  /** Canonical JSON text of `value` (Python-compatible). */
  function stringify(value) {
    return encode(value);
  }

  /** Same as compute_contract_sha256 in gates/requirements_contract.py. */
  function contractHash(contract) {
    var AEDL =
      typeof module === "object" && module.exports
        ? require("./sha256.js")
        : typeof globalThis !== "undefined"
          ? globalThis.AEDL.sha256
          : null;
    var payload = {};
    Object.keys(contract).forEach(function (key) {
      if (key !== "contract_sha256") payload[key] = contract[key];
    });
    return AEDL.hex(stringify(payload));
  }

  return { stringify: stringify, contractHash: contractHash };
});
