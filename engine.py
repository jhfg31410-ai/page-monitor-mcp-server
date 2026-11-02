#!/usr/bin/env python3
"""Cat1 MCP Server 核心去雜訊與比對引擎。

優先複用自 ~/agy-loop/state/fund01-cat1-trial-rehearsal-20261101-snapshots/parse_and_diff.py，
並補齊通用單頁 HTML 去雜訊正規化、本地／遠端來源讀取與 SHA-256 計算介面。
"""

import difflib
import hashlib
import html
import os
import re
import urllib.parse
import urllib.request


# === 複用自 parse_and_diff.py 之核心語義擷取與格式化函式 ===

def extract_semantic(html_text):
    # Extract stories: id, rank, url, title, sitebit, plus noise stats for reporting what was stripped
    pattern = re.compile(
        r'<tr class=["\']athing submission["\'] id=["\'](\d+)["\']>.*?'
        r'<span class=["\']rank["\']>(\d+)\.</span>.*?'
        r'<span class=["\']titleline["\']><a href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
        r'(?:.*?<span class=["\']sitestr["\']>(.*?)</span>)?.*?'
        r'</tr>\s*<tr><td colspan=["\']2["\']></td><td class=["\']subtext["\']>(.*?)</td></tr>',
        re.S
    )
    stories = []
    for m in pattern.finditer(html_text):
        item_id, rank, url, raw_title, site, subtext = m.groups()
        title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
        site = html.unescape(site).strip() if site else ""
        # Extract noise from subtext (points, age, comments)
        score_m = re.search(r'<span class=["\']score["\'][^>]*>(.*?)</span>', subtext)
        age_m = re.search(r'<span class=["\']age["\'][^>]*><a[^>]*>(.*?)</a></span>', subtext)
        comm_m = re.findall(r'<a href=["\']item\?id=\d+["\']>([^<]*?(?:comment|discuss)[^<]*?)</a>', subtext)
        noise_str = " | ".join(filter(None, [
            score_m.group(1) if score_m else None,
            age_m.group(1) if age_m else None,
            comm_m[-1].strip().replace('\xa0', ' ') if comm_m else None
        ]))
        stories.append({
            "rank": int(rank),
            "id": item_id,
            "title": title,
            "url": url,
            "site": site,
            "noise_stripped": noise_str
        })
    return stories


def format_semantic_lines(stories):
    lines = []
    for s in stories:
        site_part = f" ({s['site']})" if s['site'] else ""
        lines.append(f"#{s['rank']:02d} | {s['title']}{site_part} | {s['url']}")
    return "\n".join(lines) + "\n"


def diff_story_lists(t0_stories, t1_stories):
    """複用自 parse_and_diff.py 之結構化故事列表變更分類邏輯。"""
    t0_by_id = {s["id"]: s for s in t0_stories}
    t1_by_id = {s["id"]: s for s in t1_stories}
    entered = [s for s in t1_stories if s["id"] not in t0_by_id]
    exited = [s for s in t0_stories if s["id"] not in t1_by_id]
    moved = []
    noise_only = []
    for s1 in t1_stories:
        if s1["id"] in t0_by_id:
            s0 = t0_by_id[s1["id"]]
            if s0["rank"] != s1["rank"] or s0["title"] != s1["title"] or s0["url"] != s1["url"]:
                moved.append({
                    "id": s1["id"],
                    "title": s1["title"],
                    "rank_before": s0["rank"],
                    "rank_after": s1["rank"],
                    "noise_before": s0["noise_stripped"],
                    "noise_after": s1["noise_stripped"],
                })
            elif s0["noise_stripped"] != s1["noise_stripped"]:
                noise_only.append({
                    "id": s1["id"],
                    "rank": s1["rank"],
                    "title": s1["title"],
                    "noise_before": s0["noise_stripped"],
                    "noise_after": s1["noise_stripped"],
                })
    return {
        "entered": entered,
        "exited": exited,
        "moved": moved,
        "noise_ignored": noise_only,
    }


# === 本次新寫：通用 HTML 去雜訊正規化、SHA-256 計算與來源載入 ===

def extract_generic_semantic(html_text):
    """針對非 HN 結構之一般 HTML 進行去雜訊正規化（剝除 script/style/nonce/動態計數與時間戳）。"""
    noise_stripped = []

    # 記錄並剝除常見動態雜訊標籤或屬性
    for m in re.finditer(r'(?:nonce|data-nonce|data-request-id|data-timestamp)=["\']([^"\']+)["\']', html_text, re.I):
        noise_stripped.append(f"attr:{m.group(0)}")

    for m in re.finditer(r'<[^>]+class=["\'][^"\']*(?:noise|timestamp|live-counter|nonce|session-id)[^"\']*["\'][^>]*>(.*?)</[^>]+>', html_text, re.I | re.S):
        inner = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        if inner:
            noise_stripped.append(inner)

    cleaned = re.sub(r'<!--.*?-->', '', html_text, flags=re.S)
    cleaned = re.sub(r'<(script|style|noscript)\b[^>]*>.*?</\1>', '', cleaned, flags=re.I | re.S)
    cleaned = re.sub(r'<[^>]+class=["\'][^"\']*(?:noise|timestamp|live-counter|nonce|session-id)[^"\']*["\'][^>]*>.*?</[^>]+>', '', cleaned, flags=re.I | re.S)
    cleaned = re.sub(r'<[^>]+>', '\n', cleaned)
    cleaned = html.unescape(cleaned)

    lines = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip()
        if line:
            lines.append(line)
    normalized_text = "\n".join(lines) + ("\n" if lines else "")
    return normalized_text, noise_stripped


def compute_sha256(text):
    """計算 UTF-8 字串之 SHA-256 十六進位雜湊值（與彩排 SHA256SUMS.txt 方法一致）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_source_content(source):
    """讀取目標內容：支援本地檔案路徑、file:// URI、http(s):// URL 或直接傳入 HTML 字串。"""
    source_str = source.strip()
    if source_str.startswith("<") and ">" in source_str:
        return source_str, "inline_html"

    parsed = urllib.parse.urlparse(source_str)
    if parsed.scheme in ("http", "https"):
        req = urllib.request.Request(
            source_str,
            headers={"User-Agent": "Cat1-PageMonitor-MCP/0.1 (+https://toplformater.click)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_bytes = resp.read()
            return raw_bytes.decode("utf-8", errors="replace"), source_str

    if parsed.scheme == "file":
        file_path = urllib.request.url2pathname(parsed.path)
    else:
        file_path = os.path.expanduser(source_str)

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read(), file_path


def normalize_html(html_text):
    """優先使用 parse_and_diff.py 的 HN 語義擷取器；若無匹配則使用通用 HTML 去雜訊正規化。"""
    stories = extract_semantic(html_text)
    if stories:
        sem_text = format_semantic_lines(stories)
        return {
            "mode": "hn_semantic",
            "normalized_text": sem_text,
            "sha256": compute_sha256(sem_text),
            "stories": stories,
            "noise_samples": [s["noise_stripped"] for s in stories if s.get("noise_stripped")],
        }
    sem_text, noise_list = extract_generic_semantic(html_text)
    return {
        "mode": "generic_semantic",
        "normalized_text": sem_text,
        "sha256": compute_sha256(sem_text),
        "stories": [],
        "noise_samples": noise_list,
    }


def compare_pages(target_source, baseline_source=None, baseline_sha256=None):
    """執行單頁去雜訊擷取與基線比對，回傳 SHA-256、變更摘要與 unified diff。"""
    target_html, target_label = load_source_content(target_source)
    t1_info = normalize_html(target_html)

    result = {
        "target": target_label,
        "mode": t1_info["mode"],
        "target_sha256": t1_info["sha256"],
        "target_normalized_bytes": len(t1_info["normalized_text"].encode("utf-8")),
        "target_normalized_lines": len(t1_info["normalized_text"].splitlines()),
    }

    if baseline_source is None and baseline_sha256 is None:
        result["changed"] = None
        result["summary"] = (
            f"已完成單頁去雜訊擷取（模式：{t1_info['mode']}），"
            f"正規化內容共 {result['target_normalized_lines']} 行、"
            f"SHA-256 為 {t1_info['sha256']}。未提供基線，僅輸出當前基線快照。"
        )
        result["normalized_preview"] = "\n".join(t1_info["normalized_text"].splitlines()[:15])
        return result

    if baseline_source is None and baseline_sha256 is not None:
        want = baseline_sha256.strip().lower()
        changed = (t1_info["sha256"] != want)
        result["baseline_sha256"] = want
        result["changed"] = changed
        result["summary"] = (
            f"SHA-256 比對結果：{'偵測到語義變更' if changed else '語義內容無變更（雜訊已濾除）'} "
            f"(baseline={want}, target={t1_info['sha256']})。"
        )
        return result

    base_html, base_label = load_source_content(baseline_source)
    t0_info = normalize_html(base_html)

    diff_lines = list(difflib.unified_diff(
        t0_info["normalized_text"].splitlines(keepends=True),
        t1_info["normalized_text"].splitlines(keepends=True),
        fromfile=f"baseline ({base_label})",
        tofile=f"target ({target_label})",
        n=2
    ))
    diff_text = "".join(diff_lines)
    changed = (t0_info["sha256"] != t1_info["sha256"])

    result["baseline"] = base_label
    result["baseline_sha256"] = t0_info["sha256"]
    result["changed"] = changed
    result["diff_line_count"] = len(diff_lines)
    result["diff_patch_sha256"] = compute_sha256(diff_text) if diff_text else None
    result["unified_diff"] = diff_text

    if t0_info["mode"] == "hn_semantic" and t1_info["mode"] == "hn_semantic":
        story_diff = diff_story_lists(t0_info["stories"], t1_info["stories"])
        result["structured_changes"] = {
            "entered_count": len(story_diff["entered"]),
            "exited_count": len(story_diff["exited"]),
            "moved_count": len(story_diff["moved"]),
            "noise_ignored_count": len(story_diff["noise_ignored"]),
            "entered": story_diff["entered"],
            "exited": story_diff["exited"],
            "moved": story_diff["moved"],
            "noise_ignored": story_diff["noise_ignored"],
        }
        result["summary"] = (
            f"去雜訊語義比對完成：{'有真實變更' if changed else '無真實變更'}。"
            f"新進 {len(story_diff['entered'])} 筆、跌出 {len(story_diff['exited'])} 筆、"
            f"排名或內容異動 {len(story_diff['moved'])} 筆、"
            f"已忽略純動態雜訊 {len(story_diff['noise_ignored'])} 筆。"
        )
    else:
        added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
        removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
        noise_count = len(t0_info["noise_samples"]) + len(t1_info["noise_samples"])
        result["structured_changes"] = {
            "added_lines": added,
            "removed_lines": removed,
            "noise_tokens_stripped": noise_count,
        }
        result["summary"] = (
            f"去雜訊語義比對完成：{'有真實變更' if changed else '無真實變更'}。"
            f"新增 {added} 行、移除 {removed} 行，已濾除動態雜訊標記 {noise_count} 處。"
        )

    return result
