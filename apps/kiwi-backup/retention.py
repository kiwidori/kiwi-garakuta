import json
import re
from pathlib import Path

_HEX = re.compile(r"^[0-9a-f]{64}$")


def _norm_repo(repo):
    return str(Path(repo).resolve())


def _ids(rows, key="id"):
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("行リストが不正です")
    out = []
    for r in rows:
        if not isinstance(r, dict) or key not in r:
            raise ValueError("行の形式が不正です")
        v = r[key]
        if not isinstance(v, str) or not _HEX.match(v):
            raise ValueError("idが小文字16進64桁ではありません")
        out.append(v.lower())
    return out


def make_plan(repo, inventory_rows, forget_rows):
    repo = _norm_repo(repo)
    inv = _ids(inventory_rows)
    if len(set(inv)) != len(inv):
        raise ValueError("inventoryに重複idがあります")

    if not isinstance(forget_rows, list):
        raise ValueError("forget rowsがリストではありません")
    for g in forget_rows:
        if not isinstance(g, dict) :
            raise ValueError("groupの形式が不正です")

    rem = [r for g in forget_rows for r in (g.get("remove") or [])]
    rem = _ids(rem)
    if len(set(rem)) != len(rem):
        raise ValueError("removeに重複idがあります")
    if not set(rem).issubset(set(inv)):
        raise ValueError("removeがinventoryに含まれていません")

    for g in forget_rows:
        k = _ids(g.get("keep"))
        r = _ids(g.get("remove"))
        if len(set(k)) != len(k):
            raise ValueError("keepに重複idがあります")
        if not set(r).issubset(set(inv)):
            raise ValueError("group removeがinventoryに含まれていません")
        if not set(k).issubset(set(inv)) or (r and not k):
            raise ValueError("残す履歴を確認してください")
        if set(k) & set(r):
            raise ValueError("keepとremoveが交差しています")

    if rem and len(rem) == len(inv):
        raise ValueError("全削除プランは拒否します")

    return {"repo": repo, "inventory": sorted(inv), "remove": sorted(rem)}


def validate_plan(plan, repo, current_rows):
    if not isinstance(plan, dict):
        raise ValueError("planが不正です")
    for k in ("repo", "inventory", "remove"):
        if k not in plan:
            raise ValueError(f"missing {k}")

    cur_repo = _norm_repo(repo)
    if plan["repo"] != cur_repo:
        raise ValueError("repo不一致です")

    cur_inv = sorted(_ids(current_rows))
    if len(set(cur_inv)) != len(cur_inv):
        raise ValueError("履歴が重複しています")
    if plan["inventory"] != cur_inv:
        raise ValueError("stale inventoryです")

    rem = plan["remove"]
    if not isinstance(rem, list):
        raise ValueError("removeがリストではありません")
    for x in rem:
        if not isinstance(x, str) or not _HEX.match(x):
            raise ValueError("remove idが小文字16進64桁ではありません")

    if not rem or len(set(rem)) != len(rem) or not set(rem) < set(cur_inv):
        raise ValueError("削除予定が不正です。もう一度確認してください")
    return rem
