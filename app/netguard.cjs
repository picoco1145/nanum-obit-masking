// Node 프로세스 안의 외부 통신 시도를 기록하고 차단한다(시험용 감시 장치).
// 로그: $KORDOC_NETGUARD_LOG (없으면 기록 없이 차단만)
const fs = require("fs");
const LOG = process.env.KORDOC_NETGUARD_LOG;
function hit(kind, detail) {
  const line = `${new Date().toISOString()} pid=${process.pid} ${kind} ${detail}\n`;
  if (LOG) { try { fs.appendFileSync(LOG, line); } catch {} }
  throw new Error(`netguard: 외부 통신 차단 (${kind})`);
}
const net = require("net");
const origConnect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const o = args[0];
  // 유닉스 소켓(path)·IPC는 허용, TCP 호스트 연결만 차단
  if (o && typeof o === "object" && o.path) return origConnect.apply(this, args);
  if (typeof o === "string" && !/^\d+$/.test(o)) return origConnect.apply(this, args);
  hit("net.connect", JSON.stringify(typeof o === "object" ? { host: o.host, port: o.port } : args.slice(0, 2)));
};
const dns = require("dns");
for (const k of ["lookup", "resolve", "resolve4", "resolve6"]) {
  const orig = dns[k];
  dns[k] = function (h, ...rest) { hit(`dns.${k}`, String(h)); return orig.call(this, h, ...rest); };
}
if (dns.promises) for (const k of ["lookup", "resolve"]) {
  dns.promises[k] = async (h) => hit(`dns.promises.${k}`, String(h));
}
if (typeof globalThis.fetch === "function") {
  globalThis.fetch = async (u) => hit("fetch", String(u && u.url ? u.url : u).slice(0, 80));
}
