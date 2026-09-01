/* Minimal SHA-256 (FIPS 180-4), no dependencies.
 *
 * Why this exists: the requirements contract carries a self-hash
 * (contract_sha256) that the authoritative Python gate computes as
 *   sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
 *                     separators=(",", ":")).encode("utf-8"))
 * The browser has no equivalent one-liner, and crypto.subtle is not reliably
 * available on file:// origins. This file is the MOCK transport's only reason
 * to exist: it emulates the server-side finalize step so the closed loop can
 * be demoed offline.
 *
 * It is verified against the real gate, not trusted: `node web/verify-hash.js`
 * recomputes gates/requirements/requirements_contract_v1.json (a contract the
 * Python gate already PASSes) and compares against its declared hash.
 * If that check ever fails, treat the mock self-hash as BROKEN, not as a
 * "close enough" preview.
 */
(function (root, factory) {
  "use strict";
  var mod = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = mod;
  } else {
    (root.AEDL = root.AEDL || {}).sha256 = mod;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  var W = new Uint32Array(64);

  function rotr(x, n) {
    return (x >>> n) | (x << (32 - n));
  }

  function utf8Bytes(text) {
    if (typeof TextEncoder !== "undefined") {
      return new TextEncoder().encode(text);
    }
    // Node < 11 / very old browsers: manual UTF-8 encode.
    var out = [];
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i);
      if (c < 0x80) {
        out.push(c);
      } else if (c < 0x800) {
        out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
      } else if (c >= 0xd800 && c <= 0xdbff && i + 1 < text.length) {
        var lo = text.charCodeAt(i + 1);
        var cp = 0x10000 + ((c - 0xd800) << 10) + (lo - 0xdc00);
        i++;
        out.push(
          0xf0 | (cp >> 18),
          0x80 | ((cp >> 12) & 0x3f),
          0x80 | ((cp >> 6) & 0x3f),
          0x80 | (cp & 0x3f),
        );
      } else {
        out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
      }
    }
    return new Uint8Array(out);
  }

  /** SHA-256 over raw bytes. Returns a 32-byte Uint8Array. */
  function digestBytes(message) {
    var ml = message.length;
    var zeroPad = (56 - ((ml + 1) % 64) + 64) % 64;
    var total = ml + 1 + zeroPad + 8;

    var buf = new Uint8Array(total);
    buf.set(message, 0);
    buf[ml] = 0x80;

    var view = new DataView(buf.buffer);
    // 64-bit big-endian message length in bits.
    var bits = ml * 8;
    view.setUint32(total - 8, Math.floor(bits / 4294967296));
    view.setUint32(total - 4, bits >>> 0);

    var H = new Uint32Array([
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
      0x1f83d9ab, 0x5be0cd19,
    ]);

    for (var off = 0; off < total; off += 64) {
      var i;
      for (i = 0; i < 16; i++) W[i] = view.getUint32(off + i * 4);
      for (i = 16; i < 64; i++) {
        var p = W[i - 15],
          q = W[i - 2];
        var s0 = rotr(p, 7) ^ rotr(p, 18) ^ (p >>> 3);
        var s1 = rotr(q, 17) ^ rotr(q, 19) ^ (q >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      var a = H[0],
        b = H[1],
        c = H[2],
        d = H[3];
      var e = H[4],
        f = H[5],
        g = H[6],
        h = H[7];
      for (i = 0; i < 64; i++) {
        var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
        var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + t1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0;
      H[1] = (H[1] + b) >>> 0;
      H[2] = (H[2] + c) >>> 0;
      H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0;
      H[5] = (H[5] + f) >>> 0;
      H[6] = (H[6] + g) >>> 0;
      H[7] = (H[7] + h) >>> 0;
    }

    var out = new Uint8Array(32);
    for (var j = 0; j < 8; j++) {
      out[j * 4] = (H[j] >>> 24) & 0xff;
      out[j * 4 + 1] = (H[j] >>> 16) & 0xff;
      out[j * 4 + 2] = (H[j] >>> 8) & 0xff;
      out[j * 4 + 3] = H[j] & 0xff;
    }
    return out;
  }

  function toHex(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) {
      s += ("0" + bytes[i].toString(16)).slice(-2);
    }
    return s;
  }

  /** SHA-256 hex over a UTF-8 string. */
  function hex(text) {
    return toHex(digestBytes(utf8Bytes(text)));
  }

  /** SHA-256 hex over raw bytes (used for file hashing). */
  function hexBytes(bytes) {
    return toHex(digestBytes(bytes));
  }

  return {
    digestBytes: digestBytes,
    hex: hex,
    hexBytes: hexBytes,
    utf8Bytes: utf8Bytes,
  };
});
