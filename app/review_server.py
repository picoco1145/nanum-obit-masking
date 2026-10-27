"""검수 화면(오답 노트 표시). 이 PC 안에서만 열리는 작은 웹 화면이다.

  .venv/bin/python app/mask.py review [--out 결과폴더] [--port 8765]

- 127.0.0.1에만 열리고, 다른 컴퓨터에서는 접속할 수 없다. 외부 글꼴·스크립트를 불러오지 않는다.
- 놓침: 원문에서 글자를 끌어 선택한 뒤 [이름] [주민번호] [전화] [주소] 중 하나를 누른다.
- 잘못 가림: 색칠된 곳을 누른다(다시 누르면 취소).
- [저장]을 누르면 <out>/secure/learn/marks/<문서번호>.json에 저장된다. 진짜 값이 들어가므로 secure/ 밖으로 옮기지 않는다.
- [저장하고 승인]은 표시를 저장한 뒤, 놓침 표시를 사본 전체에 적용하고 masked/로 옮긴다(app/approve.py).
- [오답 노트 반영]은 learn.py ingest와 같다(자동 반영 → 회귀 시험 → 수정 요청 만들기).
- 승인 화면(/proposals)에서 이름처럼 보이는 낱말과 정규식 수정안을 승인하거나 거절한다.
"""
from __future__ import annotations

import html
import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))

import approve  # noqa: E402

KIND_KO = {"NAME": "이름", "RRN": "주민번호", "PHONE": "전화", "ADDR": "주소"}

CSS = """
:root{--ink:#1d2433;--muted:#5b6475;--line:#d9dee7;--bg:#f7f8fa;--card:#fff;--mask:#ffd58a;--over:#f3b0b0;--miss:#9fd3ff}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
font-size:18px;line-height:1.7;color:var(--ink);background:var(--bg)}
header{background:var(--card);border-bottom:1px solid var(--line);padding:14px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header a{color:var(--ink)}main{max-width:1100px;margin:0 auto;padding:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:16px}
pre{white-space:pre-wrap;word-break:break-all;font-family:inherit;margin:0}
mark{background:var(--mask);cursor:pointer;border-radius:3px}mark.over{background:var(--over);text-decoration:line-through}
span.miss{background:var(--miss);border-radius:3px}
button{font:inherit;font-size:17px;padding:8px 14px;border:1px solid var(--line);border-radius:8px;background:#fff;cursor:pointer}
button.main{background:#1d2433;color:#fff;border-color:#1d2433}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:8px;flex-wrap:wrap;z-index:2}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:top}
.muted{color:var(--muted)}#msg{white-space:pre-wrap}
"""


def page(title, body, token):
    return (f"<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body><header><strong>검수 화면</strong><a href='/'>문서 목록</a>"
            f"<a href='/proposals'>승인할 것</a></header><main>{body}</main>"
            f"<script>const TOKEN={json.dumps(token)};</script></body></html>")


class App:
    def __init__(self, out: Path):
        self.out = out
        self.token = secrets.token_urlsafe(16)

    def docs(self):
        res = []
        for mf in sorted((self.out / "secure/maps").glob("*.map.json")):
            mp = json.loads(mf.read_text(encoding="utf-8"))
            mk = self.out / "secure/learn/marks" / f"{mp['doc_id']}.json"
            n = len(json.loads(mk.read_text(encoding="utf-8"))["marks"]) if mk.exists() else 0
            res.append((mp["doc_id"], mp["original_filename"], len(mp["spans"]), n,
                        "승인함" if approve.is_approved(self.out, mp["doc_id"])
                        else ("누출 재검사 실패" if mp.get("recheck_leaks") else "검수 대기")))
        return res

    def index(self):
        rows = "".join(f"<tr><td><a href='/doc/{d}'>{d}</a></td><td>{html.escape(f)}</td><td>{s}</td><td>{n}</td>"
                       f"<td>{html.escape(stt)}</td></tr>"
                       for d, f, s, n, stt in self.docs())
        body = (f"<div class='card'><table><tr><th>문서번호</th><th>파일</th><th>가린 곳</th><th>남긴 표시</th><th>상태</th></tr>"
                f"{rows}</table></div><div class='card'><button class='main' onclick='learn()'>오답 노트 반영</button> "
                f"<span class='muted'>표시를 모아 낱말 목록을 고치고 회귀 시험을 돌립니다. 1~2분 걸릴 수 있습니다.</span>"
                f"<pre id='msg'></pre></div>"
                "<script>async function learn(){msg.textContent='반영하는 중입니다…';"
                "const r=await fetch('/api/learn',{method:'POST',headers:{'X-Token':TOKEN}});msg.textContent=await r.text();}</script>")
        return page("검수 화면", body, self.token)

    def doc(self, did):
        text = (self.out / "secure/work" / f"{did}.md").read_text(encoding="utf-8")
        mp = json.loads((self.out / "secure/maps" / f"{did}.map.json").read_text(encoding="utf-8"))
        mk = self.out / "secure/learn/marks" / f"{did}.json"
        marks = json.loads(mk.read_text(encoding="utf-8"))["marks"] if mk.exists() else []
        parts, pos = [], 0
        for r in mp["spans"]:
            if r["start"] > pos:
                parts.append(f"<span data-o='{pos}'>{html.escape(text[pos:r['start']])}</span>")
            parts.append(f"<mark data-o='{r['start']}' data-e='{r['end']}' data-k='{r['kind']}' title='{KIND_KO.get(r['kind'], r['kind'])}'>"
                         f"{html.escape(text[r['start']:r['end']])}</mark>")
            pos = r["end"]
        parts.append(f"<span data-o='{pos}'>{html.escape(text[pos:])}</span>")
        btns = "".join(f"<button onclick=\"miss('{k}')\">{v}</button>" for k, v in KIND_KO.items())
        body = (f"<h2>{did} {html.escape(mp['original_filename'])}</h2>"
                f"<div class='bar'><span class='muted'>놓친 글자를 끌어 선택한 뒤</span>{btns}"
                f"<button class='main' onclick='save()'>저장</button>"
                f"<button class='main' onclick='saveApprove()'>저장하고 승인</button><span id='msg' class='muted'></span></div>"
                f"<div class='card'><pre id='doc'>{''.join(parts)}</pre></div>"
                f"<div class='card'><strong>남긴 표시</strong><ul id='list'></ul></div>"
                "<script>"
                f"let marks={json.dumps(marks, ensure_ascii=False)};const DID={json.dumps(did)};"
                "const KO={NAME:'이름',RRN:'주민번호',PHONE:'전화',ADDR:'주소'};"
                "function cp(s){return Array.from(s).length}"
                "function off(node,o){const el=node.nodeType===3?node.parentElement:node;"
                " return +el.dataset.o+(node.nodeType===3?cp(node.data.slice(0,o)):0)}"
                "function miss(k){const s=getSelection();if(!s.rangeCount||s.isCollapsed){msg.textContent='먼저 글자를 선택하세요';return}"
                " const r=s.getRangeAt(0);let a=off(r.startContainer,r.startOffset),b=off(r.endContainer,r.endOffset);"
                " if(b<=a)return;if(marks.some(x=>x.type==='miss'&&x.start===a&&x.end===b)){s.removeAllRanges();return}marks.push({type:'miss',kind:k,start:a,end:b,text:s.toString()});s.removeAllRanges();draw()}"
                "doc.addEventListener('click',e=>{const m=e.target.closest('mark');if(!m||!getSelection().isCollapsed)return;"
                " const a=+m.dataset.o,b=+m.dataset.e;const i=marks.findIndex(x=>x.type==='over'&&x.start===a);"
                " if(i>=0)marks.splice(i,1);else marks.push({type:'over',kind:m.dataset.k,start:a,end:b,text:m.textContent});draw()});"
                "function draw(){document.querySelectorAll('mark').forEach(m=>m.classList.toggle('over',"
                " marks.some(x=>x.type==='over'&&x.start===+m.dataset.o)));"
                " list.innerHTML='';marks.forEach((x,i)=>{const li=document.createElement('li');"
                " li.textContent=(x.type==='miss'?'놓침 '+KO[x.kind]:'잘못 가림')+': '+x.text+' ';"
                " const b=document.createElement('button');b.textContent='지우기';b.onclick=()=>{marks.splice(i,1);draw()};"
                " li.appendChild(b);list.appendChild(li)})}"
                "async function save(){const r=await fetch('/api/marks/'+DID,{method:'POST',headers:{'X-Token':TOKEN,"
                " 'Content-Type':'application/json'},body:JSON.stringify({doc_id:DID,marks})});msg.textContent=await r.text()}"
                "async function saveApprove(){await save();"
                " if(!confirm('표시한 놓침을 모두 가린 뒤 승인합니다. 승인한 사본은 Claude가 읽는 폴더(masked)로 갑니다.'))return;"
                " const r=await fetch('/api/approve-doc/'+DID,{method:'POST',headers:{'X-Token':TOKEN}});msg.textContent=await r.text()}"
                "draw()</script>")
        return page(did, body, self.token)

    def proposals(self):
        import learn
        import learnstate
        ld = learnstate.learn_dir()
        ws = [w for w in learn.words(self.out) if w["status"] == "대기"]
        wrows = "".join(f"<tr><td>{w['n']}</td><td>{html.escape(w['word'])}</td><td>{w['doc_id']}</td><td>"
                        f"<button onclick=\"act('approve-word',{w['n']})\">이름 아님(예외로 추가)</button> "
                        f"<button onclick=\"act('reject-word',{w['n']})\">이름 맞음</button></td></tr>" for w in ws)
        stt = learn.load_status(ld)
        drows = ""
        for p in learn.drafts(ld):
            d = p.read_text(encoding="utf-8")
            s = stt.get(p.stem, {})
            drows += (f"<tr><td>{p.stem}</td><td><pre>{html.escape(d)}</pre></td><td>{s.get('state', '검사 전')}"
                      f"<br><span class='muted'>{html.escape('; '.join(s.get('reasons') or []))}</span></td><td>"
                      f"<button onclick=\"act('check','{p.stem}')\">회귀 시험</button> "
                      f"<button class='main' onclick=\"act('approve','{p.stem}')\">승인</button> "
                      f"<button onclick=\"act('reject','{p.stem}')\">거절</button></td></tr>")
        body = (f"<div class='card'><h3>이름처럼 보여 확인이 필요한 낱말</h3><table>{wrows or '<tr><td>없음</td></tr>'}</table></div>"
                f"<div class='card'><h3>정규식 수정안</h3><p class='muted'>승인을 누르면 회귀 시험을 다시 돌리고, "
                f"통과했을 때만 적용합니다.</p><table>{drows or '<tr><td>없음</td></tr>'}</table></div><pre id='msg'></pre>"
                "<script>async function act(a,id){msg.textContent='처리하는 중입니다…';const r=await fetch('/api/'+a+'/'+id,"
                "{method:'POST',headers:{'X-Token':TOKEN}});msg.textContent=await r.text();setTimeout(()=>location.reload(),1500)}</script>")
        return page("승인할 것", body, self.token)

    def post(self, path, data: bytes) -> str:
        import learn
        parts = path.strip("/").split("/")
        if parts[:2] == ["api", "marks"] and len(parts) == 3:
            did = parts[2]
            if not (self.out / "secure/work" / f"{did}.md").exists():
                return "없는 문서입니다."
            obj = json.loads(data.decode("utf-8"))
            marks = [{"type": m["type"], "kind": m["kind"], "start": int(m["start"]), "end": int(m["end"]),
                      "text": m.get("text", "")} for m in obj.get("marks", [])
                     if (m.get("type") == "miss" and m.get("kind") in KIND_KO)
                     or (m.get("type") == "over" and isinstance(m.get("kind"), str))]
            p = self.out / "secure/learn/marks" / f"{did}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"doc_id": did, "saved": learn.now(), "marks": marks}, ensure_ascii=False, indent=1),
                         encoding="utf-8")
            return f"저장했습니다(표시 {len(marks)}개)."
        if parts == ["api", "learn"]:
            lines = []
            s = learn.ingest(self.out, log=lambda x: None)
            lines.append(f"반영한 문서 {s['docs']}건: 놓침 {s['miss']}, 잘못 가림 {s['over']}")
            lines += ["자동 반영: " + a for a in s["auto"]]
            lines += [f"보류: {h['item']} ({'; '.join(h['why'])})" for h in s["held"]]
            lines.append(f"확인이 필요한 낱말 {s['pending_words']}개, 수정 요청 {len(s['requests'])}건, 회귀 사례 {len(s['cases'])}건")
            return "\n".join(lines)
        if len(parts) == 3 and parts[0] == "api":
            act, arg = parts[1], parts[2]
            if act == "approve-doc":
                return approve.approve_doc(self.out, arg)
            if act == "approve-word":
                return learn.decide_word(self.out, int(arg), True)
            if act == "reject-word":
                return learn.decide_word(self.out, int(arg), False)
            if act == "check":
                r = learn.check_draft(arg)
                return r["state"] + (": " + "; ".join(r["reasons"]) if r["reasons"] else "")
            if act == "approve":
                return learn.approve_draft(arg, who="검수 화면")
            if act == "reject":
                return learn.reject_draft(arg)
        return "알 수 없는 요청입니다."


def serve(out: Path, port: int = 8765):
    import netguard
    netguard.install(str(out / "logs/netguard.log"))
    app = App(out)
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(b)

        def _host_ok(self):
            return self.headers.get("Host") in allowed

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "forbidden")
            path = urlparse(self.path).path
            try:
                if path == "/":
                    return self._send(200, app.index())
                if path.startswith("/doc/"):
                    did = path[5:]
                    if not (out / "secure/work" / f"{did}.md").exists() or "/" in did:
                        return self._send(404, "없는 문서입니다.")
                    return self._send(200, app.doc(did))
                if path == "/proposals":
                    return self._send(200, app.proposals())
            except Exception as ex:  # noqa: BLE001
                return self._send(500, f"오류: {type(ex).__name__}")
            self._send(404, "없는 화면입니다.")

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-Token") != app.token:
                return self._send(403, "forbidden")
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n) if n else b""
            try:
                msg = app.post(urlparse(self.path).path, data)
            except Exception as ex:  # noqa: BLE001
                msg = f"오류: {type(ex).__name__}: {ex}"
            self._send(200, msg, "text/plain; charset=utf-8")

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"검수 화면: http://127.0.0.1:{port}/  (끝내려면 Ctrl+C)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
