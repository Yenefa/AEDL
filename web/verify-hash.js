/* Cross-language verification of the browser-side self-hash emulation.
 *
 * The MOCK transport signs contracts with web/canonical-json.js + web/sha256.js.
 * Those are only trustworthy if they reproduce the authoritative Python gate's
 * digest. This script recomputes a contract that the Python gate already
 * PASSes and compares.
 *
 * Run:
 *     node web/verify-hash.js [path/to/contract.json]
 *
 * Default target: gates/requirements/requirements_contract_v1.json
 * (M2 retroactive contract, declared hash 82c136df...).
 *
 * Exit code 0 = digests agree. Non-zero = the mock self-hash is BROKEN;
 * do not ship, and do not "fix" it by trusting the frontend's number.
 */
"use strict";

var fs = require("fs");
var path = require("path");

var canonicalJson = require("./canonical-json.js");

function main() {
  var target = process.argv[2];
  if (!target) {
    target = path.join(
      __dirname,
      "..",
      "gates",
      "requirements",
      "requirements_contract_v1.json",
    );
  }
  var raw = fs.readFileSync(target, "utf8");
  if (raw.charCodeAt(0) === 0xfeff) raw = raw.slice(1); // strip UTF-8 BOM

  var contract = JSON.parse(raw);
  var declared = contract.contract_sha256;
  var computed = canonicalJson.contractHash(contract);

  console.log("target   : " + path.relative(process.cwd(), target));
  console.log("declared : " + declared);
  console.log("computed : " + computed);

  if (typeof declared !== "string" || !/^[0-9a-f]{64}$/.test(declared)) {
    console.error("FAIL: contract declares no well-formed contract_sha256");
    process.exit(2);
  }
  if (computed !== declared) {
    console.error("FAIL: JS canonical+sha256 disagrees with the declared hash");
    process.exit(1);
  }
  console.log(
    "OK: JS digest matches the Python gate's digest for this contract",
  );
}

main();
