#!/usr/bin/env node
/**
 * Final Motion §六 -- the two review URLs, on this machine's LAN address.
 *
 * `npm run review:lan` serves the same build on 0.0.0.0:5293. This prints the
 * addresses a phone on the same network types in. §六 accepts "QR code OR
 * plain text address"; this prints the text, because a QR code I cannot
 * verify scans is worse than an address that obviously does.
 *
 * The addresses are read off the machine's own interfaces. A host with several
 * gets several printed rather than one guessed at.
 *
 * A real-device PASS is not asserted by this tool and cannot be: it prints
 * addresses. What happens on the phone is for the product review to judge.
 */
import { networkInterfaces } from "node:os";

const PORT = Number(process.argv.find((a) => a.startsWith("--port="))?.slice(7)) || 5293;

const addrs = Object.entries(networkInterfaces())
  .flatMap(([name, list]) => (list ?? []).map((i) => ({ ...i, name })))
  .filter((i) => i.family === "IPv4" && !i.internal)
  .map((i) => ({ iface: i.name, address: i.address }));

if (!addrs.length) {
  console.log("No non-internal IPv4 interface found. Is this machine on a network?");
  process.exit(1);
}

console.log(`\nFinal Motion §六 -- LAN review addresses (port ${PORT})`);
console.log("\nServe with:  npm run review:lan\n");
for (const { iface, address } of addrs) {
  console.log(`  interface ${iface}`);
  console.log(`    Candidate  http://${address}:${PORT}/?review=target`);
  console.log(`    Current    http://${address}:${PORT}/?review=current`);
  console.log(`    Candidate + live status readout`);
  console.log(`               http://${address}:${PORT}/?review=target&status=1`);
  console.log("");
}
console.log("The status readout is a QA surface: it is off unless `status=1` is in the\n"
  + "query, it draws nothing into the page otherwise, and it must be OFF for any\n"
  + "capture or review pass. It reports FPS, quality level, device sample tier,\n"
  + "material-cache size and a running black-frame count.\n");
