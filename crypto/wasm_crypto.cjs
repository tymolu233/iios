/**
 * iios.me WASM crypto – CommonJS (vm sandbox, Node 24 safe)
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { webcrypto } = require("crypto");
const { TextEncoder, TextDecoder } = require("util");

const DIR = __dirname;
const WASM_PATH = path.join(DIR, "web_wasm_bg.534e8f19399f44e1496d.wasm");
const MAIN_JS = path.join(DIR, "main.19270de0.js");

/** 签名会绑定 navigator.userAgent，必须与 HTTP 请求 UA 一致 */
const DEFAULT_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) " +
  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7.5 " +
  "Mobile/15E148 Safari/604.1";

let ctx = null;
let inited = null;
let currentUa = DEFAULT_UA;
let currentHost = "www.iios.fun";

function buildContext(opts = {}) {
  class Window {}
  const host = opts.host || currentHost || "www.iios.fun";
  const nav = {
    userAgent: opts.userAgent || DEFAULT_UA,
    standalone: !!opts.standalone,
    maxTouchPoints: 5,
    serviceWorker: undefined,
    xr: undefined,
  };
  const loc = {
    host,
    hostname: host,
    href: `https://${host}/`,
    pathname: "/",
    protocol: "https:",
    origin: `https://${host}`,
  };
  const doc = { documentElement: { ontouchstart: null } };
  const windowObj = Object.assign(Object.create(Window.prototype), {
    crypto: webcrypto,
    navigator: nav,
    location: loc,
    document: doc,
    msCrypto: undefined,
    queueMicrotask: (fn) => queueMicrotask(fn),
  });

  function _0x506876() {
    return "static/media/web_wasm_bg.534e8f19399f44e1496d.wasm";
  }
  _0x506876.b = `https://${host}/`;
  _0x506876.d = () => {};
  _0x506876.n = (m) => () => m;

  const sandbox = {
    console,
    URL,
    URLSearchParams,
    // Request/Response may be missing on older Node
    WebAssembly,
    Promise,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Error,
    TypeError,
    Date,
    Math,
    JSON,
    Reflect,
    Uint8Array,
    Int32Array,
    Float64Array,
    ArrayBuffer,
    DataView,
    Map,
    Set,
    WeakMap,
    Symbol,
    Proxy,
    Function,
    parseInt,
    parseFloat,
    isNaN,
    Infinity,
    NaN,
    undefined,
    TextEncoder,
    TextDecoder,
    FinalizationRegistry: class {
      register() {}
      unregister() {}
    },
    Window,
    window: windowObj,
    self: windowObj,
    crypto: webcrypto,
    queueMicrotask,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    process,
    Buffer,
    _0x3d6069: TextDecoder,
    _0x35aa2f: TextEncoder,
    _0x415d9f: undefined,
    _0x506876,
    module: { require },
    require,
    fetch: async (url) => {
      const u = String(url);
      if (u.includes("wasm")) {
        const buf = fs.readFileSync(WASM_PATH);
        return {
          ok: true,
          type: "basic",
          headers: {
            get: (k) =>
              String(k).toLowerCase() === "content-type" ? "application/wasm" : null,
          },
          arrayBuffer: async () =>
            buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
        };
      }
      throw new Error("unexpected fetch " + u);
    },
  };
  sandbox.globalThis = sandbox;
  sandbox.global = sandbox;

  // Optional globals
  try {
    sandbox.Request = Request;
    sandbox.Response = Response;
  } catch (_) {}

  return vm.createContext(sandbox);
}

function loadGlue(context) {
  const mainSrc = fs.readFileSync(MAIN_JS, "utf8");
  const arrStart = mainSrc.indexOf("function a0_0x46e8()");
  let arrEnd = mainSrc.indexOf("return a0_0x46e8();") + "return a0_0x46e8();".length;
  while (/\s/.test(mainSrc[arrEnd])) arrEnd++;
  if (mainSrc[arrEnd] === "}") arrEnd++;
  const arrFn = mainSrc.slice(arrStart, arrEnd);

  const decStart = mainSrc.indexOf("function a0_0x4555(");
  let depth = 0;
  let decEnd = decStart;
  for (let i = decStart; i < decStart + 500; i++) {
    if (mainSrc[i] === "{") depth++;
    else if (mainSrc[i] === "}") {
      depth--;
      if (depth === 0) {
        decEnd = i + 1;
        break;
      }
    }
  }
  const decFn = mainSrc.slice(decStart, decEnd);
  const shufEnd =
    mainSrc.indexOf("}(a0_0x46e8,0x540d5));") + "}(a0_0x46e8,0x540d5));".length;
  const shuffle = mainSrc.slice(0, shufEnd);

  const rtStart = mainSrc.indexOf("function _0x29f39d");
  const rtEnd =
    mainSrc.indexOf("const _0x238d19=_0x124a89;") + "const _0x238d19=_0x124a89;".length;
  const runtime = mainSrc.slice(rtStart, rtEnd);

  vm.runInContext(arrFn + "\n" + decFn + "\n" + shuffle, context, {
    filename: "iios-strings.js",
  });
  vm.runInContext("var _0x436c67=a0_0x4555,_0x529d43=a0_0x4555;", context);
  vm.runInContext(runtime, context, { filename: "iios-runtime.js" });
}

/**
 * @param {{userAgent?: string, standalone?: boolean, host?: string}} [opts]
 */
async function init(opts = {}) {
  // UA/host/standalone 变更时重建 sandbox（签名依赖这些环境字段）
  const nextUa = opts.userAgent || currentUa || DEFAULT_UA;
  const nextHost = opts.host || currentHost || "www.iios.fun";
  const needRebuild =
    !inited ||
    nextUa !== currentUa ||
    nextHost !== currentHost ||
    (opts.standalone !== undefined &&
      ctx &&
      ctx.window.navigator.standalone !== !!opts.standalone);

  if (needRebuild) {
    currentUa = nextUa;
    currentHost = nextHost;
    inited = null;
    ctx = null;
  }
  if (inited) return inited;
  inited = (async () => {
    ctx = buildContext({
      userAgent: currentUa,
      standalone: !!opts.standalone,
      host: currentHost,
    });
    loadGlue(ctx);
    // Pass raw bytes so glue skips broken fetch/Response path
    const buf = fs.readFileSync(WASM_PATH);
    ctx.__wasmBytes = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
    await vm.runInContext("_0x124a89(__wasmBytes)", ctx);
    return true;
  })();
  return inited;
}

function setEnv({ userAgent, standalone, host } = {}) {
  return init({ userAgent, standalone, host });
}

/**
 * @param {{method:string,url:string,baseURL?:string,data?:any,token?:string,timestamp?:number}} opts
 */
async function encryptRequest(opts) {
  await init({
    userAgent: opts.userAgent || currentUa,
    standalone: opts.standalone,
    host: opts.host || currentHost,
  });
  // 运行时可再改 UA / standalone / host
  if (opts.userAgent) {
    ctx.window.navigator.userAgent = opts.userAgent;
    currentUa = opts.userAgent;
  }
  if (opts.standalone !== undefined) {
    ctx.window.navigator.standalone = !!opts.standalone;
  }
  if (opts.host) {
    const h = opts.host;
    ctx.window.location.host = h;
    ctx.window.location.hostname = h;
    ctx.window.location.origin = `https://${h}`;
    ctx.window.location.href = `https://${h}/`;
    currentHost = h;
  }
  const payload = {
    method: (opts.method || "get").toLowerCase(),
    url: opts.url,
    baseURL: opts.baseURL || "/api",
    data: opts.data,
    token: opts.token || null,
    timestamp: opts.timestamp || Date.now(),
  };
  // pass via JSON to avoid context bridging issues
  ctx.__encIn = payload;
  const result = await vm.runInContext(
    `(async () => {
      const o = __encIn;
      const ts = o.timestamp;
      const headers = {
        Accept: "application/json, text/plain, */*",
        "Content-Type": "text/plain",
        "X-Timestamp": ts
      };
      if (o.token) headers.Authorization = "Basic " + o.token;
      let data = o.data;
      if (data != null && typeof data !== "string") data = JSON.stringify(data);
      const cfg = {
        method: o.method,
        url: o.url,
        baseURL: o.baseURL != null ? o.baseURL : "/api",
        headers,
        data: data === undefined ? undefined : data,
        timeout: 120000
      };
      const handle = _0x29f39d(cfg);
      let ret = _0x57dcf6(_0x415d9f.e(handle));
      if (ret && typeof ret.then === "function") ret = await ret;
      return { s: ret.s, d: ret.d, ts: ts, headers: Object.assign({}, headers, { "X-Signature": ret.s }) };
    })()`,
    ctx
  );
  return {
    signature: result.s,
    body: result.d,
    timestamp: result.ts,
    headers: result.headers,
    data: result.d,
  };
}

/**
 * @param {{data:string,status?:number,headers?:object,config?:object}} resp
 */
async function decryptResponse(resp) {
  await init();
  ctx.__decIn = {
    data: resp.data,
    status: resp.status || 200,
    headers: resp.headers || {},
    config: resp.config || {},
  };
  const plain = await vm.runInContext(
    `(async () => {
      const r = __decIn;
      const response = {
        data: r.data,
        status: r.status,
        statusText: "OK",
        headers: r.headers,
        config: r.config,
        request: {}
      };
      const handle = _0x29f39d(response);
      let ret = _0x57dcf6(_0x415d9f.d(handle));
      if (ret && typeof ret.then === "function") ret = await ret;
      return ret.d !== undefined ? ret.d : ret;
    })()`,
    ctx
  );
  return plain;
}

module.exports = {
  init,
  setEnv,
  encryptRequest,
  decryptResponse,
  DEFAULT_UA,
  getUserAgent: () => currentUa,
};

/**
 * CLI:
 *   node wasm_crypto.cjs encrypt '{"method":"post","url":"/user/login","data":{...}}'
 *   node wasm_crypto.cjs decrypt '{"data":"...","status":200,"headers":{}}'
 *   stdin:  node wasm_crypto.cjs encrypt < in.json
 */
if (require.main === module) {
  (async () => {
    const cmd = process.argv[2] || "selftest";
    if (cmd === "selftest") {
      console.log("init…");
      await init();
      const enc = await encryptRequest({
        method: "post",
        url: "/user/login",
        data: { email: "t@t.com", password: "x" },
      });
      console.log(
        JSON.stringify({
          ok: true,
          sigHead: enc.signature && enc.signature.slice(0, 40),
          bodyHead: enc.body && String(enc.body).slice(0, 40),
          ts: enc.timestamp,
        })
      );
      return;
    }

    let raw = process.argv[3];
    if (!raw || raw === "-") {
      raw = fs.readFileSync(0, "utf8");
    }
    const input = JSON.parse(raw);
    await init();
    if (cmd === "encrypt") {
      const enc = await encryptRequest(input);
      process.stdout.write(JSON.stringify(enc));
    } else if (cmd === "decrypt") {
      const plain = await decryptResponse(input);
      process.stdout.write(
        JSON.stringify({ plain: typeof plain === "string" ? plain : plain })
      );
    } else {
      console.error("unknown cmd", cmd);
      process.exit(2);
    }
  })().catch((e) => {
    console.error("FAIL", e && e.stack ? e.stack : e);
    process.exit(1);
  });
}
