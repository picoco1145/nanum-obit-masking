"""이미 읽어 둔 글(secure/work/*.md)로 가림 단계만 다시 돌린다.

OCR을 다시 하지 않으므로 빠르고, 학습 전후에 같은 글을 놓고 비교할 수 있다.
결과는 새 폴더에 run과 같은 구조(pending/, secure/maps, secure/work, logs/metrics.jsonl)로 쓴다.

  .venv/bin/python tests/replay.py SRC_OUT DST_OUT [--learn-dir DIR] [--only 001,002]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import yaml  # noqa: E402

import learnstate  # noqa: E402
import mask  # noqa: E402
import netguard  # noqa: E402


def replay(src: Path, dst: Path, state, only=None, quiet=False):
    import ner
    policy = yaml.safe_load((ROOT / "config/policy.yaml").read_text(encoding="utf-8"))
    ner_stop = ner.load_stopwords(ROOT / "config/ner_stopwords.txt")
    for sub in ("pending", "secure/maps", "secure/work", "logs"):
        (dst / sub).mkdir(parents=True, exist_ok=True)
    out = []
    for mf in sorted((src / "secure/maps").glob("*.map.json")):
        old = json.loads(mf.read_text(encoding="utf-8"))
        did = old["doc_id"]
        if only and not any(k in did or k in old["original_filename"] for k in only):
            continue
        text = (src / "secure/work" / f"{did}.md").read_text(encoding="utf-8")
        st = old["source_type"]
        c0 = time.process_time()
        masked, recs, cands, roles, leaks, t, entries = mask.process_text(
            text, old.get("profile", "fixed"), policy, old.get("ner", True), ner_stop,
            ocr=st in ("pdf-ocr", "fax"), state=state)
        mean_conf = (old.get("ocr") or {}).get("mean_conf")
        status = "failed" if leaks else "pending"
        (dst / "pending" / f"{did}.md").write_text(mask.front_matter(did, st, roles, status, mean_conf) + masked,
                                                   encoding="utf-8")
        (dst / "secure/work" / f"{did}.md").write_text(text, encoding="utf-8")
        mp = dict(old, spans=recs, ner_candidates=cands, recheck_leaks=leaks, replay_of=str(src),
                  learn_key=state.key())
        mp["map"] = {}
        for r in recs:
            if r["kind"] == "NAME":
                mp["map"][r["repl"]] = r["key"]
            else:
                mp["map"].setdefault(r["repl"], [])
                if r["orig"] not in mp["map"][r["repl"]]:
                    mp["map"][r["repl"]].append(r["orig"])
        (dst / "secure/maps" / f"{did}.map.json").write_text(json.dumps(mp, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
        cpu = round(time.process_time() - c0, 2)
        with open(dst / "logs/metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"doc_id": did, "source_type": st, "total_cpu_s": cpu, "total_wall_s": cpu,
                                "max_rss_mb": mask.rss_mb(), "spans": len(recs), "recheck_leaks": leaks,
                                "status": status, "replay": True}, ensure_ascii=False) + "\n")
        out.append((did, old["original_filename"], len(recs), leaks))
        if not quiet:
            print(f"{did} {old['original_filename']} 가림 {len(recs)}건 재검사 {leaks}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--learn-dir", default=None)
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    dst = Path(a.dst).resolve()
    if dst.exists() and any(dst.iterdir()):
        sys.exit(f"이미 있는 폴더라 덮어쓰지 않습니다: {dst}")
    dst.mkdir(parents=True, exist_ok=True)
    netguard.install(str(dst / "logs/netguard.log"))
    st = learnstate.load(Path(a.learn_dir).resolve() if a.learn_dir else None)
    print(f"학습 상태 {st.key()} (라벨 {sum(len(v) if isinstance(v, list) else sum(len(x) for x in v.values()) for v in st.labels.values())}, "
          f"예외 {len(st.exceptions)}, 오독 {len(st.confusions)}, 규칙 {len(st.rules)})")
    replay(Path(a.src).resolve(), dst, st, a.only.split(",") if a.only else None)


if __name__ == "__main__":
    main()
